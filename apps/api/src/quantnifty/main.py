from __future__ import annotations

import asyncio
import math
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from quantnifty.market_brain import decision_intelligence
from quantnifty.replay import normalize_candles, replay, summary, to_dict
from quantnifty.strike_selector import select_strikes
from quantnifty.institutional_engine import final_decision, replay_signal_stack

BASE = "https://api.indstocks.com"
TOKEN = (os.getenv("INDSTOCKS_API_TOKEN") or os.getenv("INDSTOCKS_TOKEN") or "").strip()
NIFTY_ID = os.getenv("NIFTY_SECURITY_ID", "40000001")
NIFTY_SCRIP_CODE = os.getenv("NIFTY_SCRIP_CODE", "NSE_40000001")
EXPIRY = os.getenv("NIFTY_EXPIRY", "").strip()
POLL_SECONDS = max(5.0, float(os.getenv("POLL_SECONDS", "15")))

app = FastAPI(title="QuantNifty Next", version="1.8.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
cache: dict[str, Any] = {"snapshot": None, "previous_snapshot": None, "updated_at": None}

async def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not TOKEN: raise RuntimeError("INDSTOCKS_API_TOKEN is not configured")
    headers = {"Authorization": TOKEN, "Accept": "application/json"}
    last = "provider request failed"
    for attempt in range(4):
        try:
            async with httpx.AsyncClient(timeout=15) as client: response = await client.get(BASE + path, params=params, headers=headers)
            if response.status_code == 429 or response.status_code >= 500:
                last = f"HTTP {response.status_code}"; await asyncio.sleep(0.5 * (2**attempt)); continue
            if response.status_code >= 400:
                try: payload = response.json()
                except Exception: payload = {}
                detail = payload.get("debug_info") or payload.get("message") or payload.get("error")
                raise RuntimeError(f"HTTP {response.status_code}: {detail or 'provider rejected request'}")
            return response.json()
        except RuntimeError: raise
        except Exception as exc: last = str(exc); await asyncio.sleep(0.5 * (2**attempt))
    raise RuntimeError(last)

def num(value: Any) -> float:
    try: return float(value or 0)
    except (TypeError, ValueError): return 0.0

def norm_leg(leg: dict[str, Any], strike: float, side: str) -> dict[str, Any]:
    g = leg.get("greeks") or {}
    return {"strike":float(strike),"side":side,"security_id":str(leg.get("security_id") or ""),"trading_symbol":str(leg.get("trading_symbol") or ""),"last_price":num(leg.get("last_price")),"previous_close":num(leg.get("previous_close_price",leg.get("previous_close"))),"oi":num(leg.get("oi")),"previous_oi":num(leg.get("previous_oi")),"volume":num(leg.get("volume")),"bid":num(leg.get("top_bid_price",leg.get("bid"))),"bid_qty":num(leg.get("top_bid_quantity",leg.get("bid_qty"))),"ask":num(leg.get("top_ask_price",leg.get("ask"))),"ask_qty":num(leg.get("top_ask_quantity",leg.get("ask_qty"))),"iv":num(leg.get("iv")),"delta":num(g.get("delta",leg.get("delta"))),"gamma":num(g.get("gamma",leg.get("gamma"))),"theta":num(g.get("theta",leg.get("theta"))),"vega":num(g.get("vega",leg.get("vega")))}

def flatten_chain(data: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    root=data.get("data") or data; strikes=root.get("strikes") or root.get("option_chain") or {}; items=strikes.items() if isinstance(strikes,dict) else []; rows=[]
    for key,value in items:
        try: strike=float(key)
        except (TypeError,ValueError): continue
        if not isinstance(value,dict): continue
        for leg,side in ((value.get("ce") or value.get("call") or value.get("CE") or {},"CE"),(value.get("pe") or value.get("put") or value.get("PE") or {},"PE")):
            if leg: rows.append(norm_leg(leg,strike,side))
    spot=num(root.get("underlying_ltp",root.get("underlying_price"))); rows.sort(key=lambda r:(r["strike"],0 if r["side"]=="CE" else 1)); return spot,rows

def max_pain(rows: list[dict[str, Any]]) -> float | None:
    strikes=sorted({r["strike"] for r in rows})
    if not strikes: return None
    best,loss_best=None,float("inf")
    for expiry_price in strikes:
        loss=sum((max(0.0,expiry_price-r["strike"]) if r["side"]=="CE" else max(0.0,r["strike"]-expiry_price))*r["oi"] for r in rows)
        if loss<loss_best: best,loss_best=expiry_price,loss
    return best

def expected_move_value(spot: float, atm_iv: float | None, expiry: str | None = None, now: datetime | None = None) -> float | None:
    if spot<=0 or atm_iv is None or atm_iv<=0: return None
    current=now or datetime.now(timezone.utc); days=1.0
    if expiry:
        try: days=max(1.0,(datetime.strptime(str(expiry)[:10],"%Y-%m-%d").replace(tzinfo=timezone.utc)-current).total_seconds()/86400.0)
        except ValueError: pass
    return spot*(atm_iv/100.0)*math.sqrt(days/365.0)

def analytics(spot: float, rows: list[dict[str, Any]], expiry: str | None = None) -> dict[str, Any]:
    calls=[r for r in rows if r["side"]=="CE"]; puts=[r for r in rows if r["side"]=="PE"]; call_oi=sum(r["oi"] for r in calls); put_oi=sum(r["oi"] for r in puts)
    call_doi=sum(r["oi"]-r["previous_oi"] for r in calls); put_doi=sum(r["oi"]-r["previous_oi"] for r in puts); pcr=put_oi/call_oi if call_oi else None
    call_iv=[r["iv"] for r in calls if r["iv"]>0]; put_iv=[r["iv"] for r in puts if r["iv"]>0]; avg_call_iv=sum(call_iv)/len(call_iv) if call_iv else None; avg_put_iv=sum(put_iv)/len(put_iv) if put_iv else None; iv_skew=avg_put_iv-avg_call_iv if avg_put_iv is not None and avg_call_iv is not None else None
    atm=min((r for r in rows if r["iv"]>0),key=lambda r:abs(r["strike"]-spot),default=None); atm_iv=atm["iv"] if atm else None
    gex=sum(r["gamma"]*r["oi"]*spot*spot*0.01*(-1 if r["side"]=="CE" else 1) for r in rows); dex=sum(r["delta"]*r["oi"]*(-1 if r["side"]=="CE" else 1) for r in rows); vanna_proxy=sum(r["vega"]*r["oi"]*(-1 if r["side"]=="CE" else 1) for r in rows)
    volume=sum(r["volume"] for r in rows); spread_cost=sum(max(0.0,r["ask"]-r["bid"]) for r in rows if r["ask"]>0 and r["bid"]>0); liquidity=max(0.0,100.0*(1.0-min(1.0,spread_cost/max(1.0,volume))))
    by_strike={}
    for r in rows: by_strike[r["strike"]]=by_strike.get(r["strike"],0.0)+r["gamma"]*r["oi"]*spot*spot*0.01*(-1 if r["side"]=="CE" else 1)
    points=sorted(by_strike.items()); gamma_flip=None
    for (a,ea),(b,eb) in zip(points,points[1:]):
        if ea==0: gamma_flip=a; break
        if ea*eb<0: gamma_flip=a+(b-a)*(abs(ea)/(abs(ea)+abs(eb))); break
    if gamma_flip is None and points: gamma_flip=min(points,key=lambda p:abs(p[1]))[0]
    walls=[]
    for side in ("CE","PE"):
        side_rows=[r for r in rows if r["side"]==side]
        if side_rows:
            w=max(side_rows,key=lambda r:r["oi"]*abs(r["gamma"])); walls.append({"side":side,"strike":w["strike"],"exposure":w["oi"]*abs(w["gamma"])})
    strikes=sorted(by_strike); support=max((s for s in strikes if s<=spot),default=None); resistance=min((s for s in strikes if s>=spot),default=None); structure="ABOVE_GAMMA_FLIP" if gamma_flip is not None and spot>gamma_flip else "BELOW_GAMMA_FLIP" if gamma_flip is not None else "UNAVAILABLE"; dealer_flow="PUT_SUPPORT" if put_doi>call_doi else "CALL_RESISTANCE" if call_doi>put_doi else "BALANCED"
    score=50.0; reasons=[]
    if pcr is not None:
        if pcr>1.15: score+=15; reasons.append("put OI dominance")
        elif pcr<0.85: score-=15; reasons.append("call OI dominance")
    if iv_skew is not None:
        if iv_skew<-2: score+=10; reasons.append("lower put IV")
        elif iv_skew>2: score-=10; reasons.append("higher put IV")
    if put_doi>call_doi: score+=10; reasons.append("positive put OI flow")
    elif call_doi>put_doi: score-=10; reasons.append("positive call OI flow")
    if gamma_flip is not None: score+=5 if spot>gamma_flip else -5
    score=max(0.0,min(100.0,score)); bias="BULLISH" if score>=60 else "BEARISH" if score<=40 else "NEUTRAL"; confidence=50.0 if bias=="NEUTRAL" else min(99.0,50.0+abs(score-50.0)); expected_move=expected_move_value(spot,atm_iv,expiry)
    return {"spot":spot,"pcr":pcr,"call_oi":call_oi,"put_oi":put_oi,"call_oi_change":call_doi,"put_oi_change":put_doi,"gex":gex,"dex":dex,"vanna_proxy":vanna_proxy,"iv_skew":iv_skew,"atm_iv":atm_iv,"gamma_flip":gamma_flip,"gamma_walls":walls,"max_pain":max_pain(rows),"expected_move":{"move":expected_move,"lower":spot-expected_move,"upper":spot+expected_move} if expected_move else None,"support":support,"resistance":resistance,"structure":structure,"dealer_flow":dealer_flow,"liquidity_score":round(liquidity,1),"bullish_score":round(score,1),"bearish_score":round(100-score,1),"bias":bias,"confidence":round(confidence,1),"rationale":reasons,"strike_selection":select_strikes(spot,rows,bias,expected_move=expected_move),"data_integrity":"LIVE_PROVIDER","rows":len(rows),"option_chain":rows,"timestamp":datetime.now(timezone.utc).isoformat()}

async def snapshot() -> dict[str, Any]:
    expiry=EXPIRY
    if not expiry:
        response=await api_get("/market/instruments/expiries",{"underlying":"NIFTY","segment":"DERIVATIVE"}); values=response.get("data") or []
        if not isinstance(values,list) or not values: raise RuntimeError("provider returned no upcoming NIFTY expiries")
        expiry=str(values[0].get("expiry") if isinstance(values[0],dict) else values[0])
    raw=await api_get("/market/option-chain",{"exchange":"NSE","segment":"INDEX","underlying-scrip":NIFTY_ID,"expiry":expiry,"strike_count":20}); spot,rows=flatten_chain(raw)
    if spot<=0: raise RuntimeError("provider returned invalid NIFTY spot")
    if len(rows)<2: raise RuntimeError("provider returned an empty or incomplete option chain")
    result=analytics(spot,rows,expiry); result["expiry"]=expiry
    if cache.get("snapshot") is not None: cache["previous_snapshot"]=cache["snapshot"]
    cache["snapshot"],cache["updated_at"]=result,time.time(); result["intelligence"]=decision_intelligence(result,cache.get("previous_snapshot")); return result

async def continuous_market_refresh():
    while True:
        try: await snapshot()
        except Exception: pass
        await asyncio.sleep(POLL_SECONDS)

@app.on_event("startup")
async def start_background_refresh(): app.state.market_refresh_task=asyncio.create_task(continuous_market_refresh())

@app.on_event("shutdown")
async def stop_background_refresh():
    task=getattr(app.state,"market_refresh_task",None)
    if task:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

@app.get("/")
def root():
    path=os.path.join(os.path.dirname(__file__),"web","index.html"); return FileResponse(path) if os.path.exists(path) else {"service":"QuantNifty Next","status":"ok"}

@app.get("/intelligence")
def intelligence_page():
    path=os.path.join(os.path.dirname(__file__),"web","intelligence.html"); return FileResponse(path)

@app.get("/health")
def health(): return {"status":"ok","provider":"INDstocks","provider_configured":bool(TOKEN),"timestamp":datetime.now(timezone.utc).isoformat()}
@app.get("/api/v1/health")
def api_health(): return health()

@app.get("/api/v1/status")
def status():
    return {"status":"ok","provider":"INDstocks","provider_configured":bool(TOKEN),"cached":cache["snapshot"] is not None,"updated_at":cache["updated_at"],"refresh_interval_seconds":POLL_SECONDS,"trading":"DISABLED","analytics":["OI_FLOW","PCR","GEX","DEX","VANNA_PROXY","IV_SKEW","GAMMA_FLIP","GAMMA_WALLS","MAX_PAIN","EXPECTED_MOVE","MARKET_STRUCTURE","DEALER_FLOW","LIQUIDITY","DIRECTION_SCORE","STRIKE_SELECTION","MARKET_STATE","EVENT_DETECTION","MOVE_ATTRIBUTION","SIGNAL_DNA","PRESSURE_MAP","NO_TRADE_INTELLIGENCE","INSTITUTIONAL_SIGNAL","RISK_ENGINE","FINAL_DECISION","EXECUTION_PLAN"],"replay":"AVAILABLE"}

@app.get("/api/v1/market")
async def market():
    try: return await snapshot()
    except Exception as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc

@app.get("/api/v1/analytics")
async def analytics_api(): return await market()

@app.get("/api/v1/intelligence")
async def intelligence_api():
    try:
        data=await snapshot(); return {"timestamp":data["timestamp"],"spot":data["spot"],"expiry":data.get("expiry"),"intelligence":data["intelligence"]}
    except Exception as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc

@app.get("/api/v1/decision")
async def decision(strategy: str="directional"):
    try: data=await snapshot()
    except Exception as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
    mode=strategy.strip().lower()
    if mode not in {"directional","gamma_blast"}: raise HTTPException(400,"strategy must be directional or gamma_blast")
    em=(data.get("expected_move") or {}).get("move"); bias=data["bias"]; directional_ok=bias in {"BULLISH","BEARISH"}; confidence_ok=data["confidence"]>=60.0; liquidity_ok=data["liquidity_score"]>=50.0; gf=data.get("gamma_flip"); gamma_position_ok=gf is not None and ((bias=="BULLISH" and data["spot"]>gf) or (bias=="BEARISH" and data["spot"]<gf)); dealer_ok=(bias=="BULLISH" and data["dealer_flow"]=="PUT_SUPPORT") or (bias=="BEARISH" and data["dealer_flow"]=="CALL_RESISTANCE")
    previous=cache.get("previous_snapshot") or {}; pg,cg=previous.get("gex"),data.get("gex"); gamma_acceleration=pg is not None and cg is not None and abs(cg)>abs(pg)*1.10; old_em=(previous.get("expected_move") or {}).get("move") if isinstance(previous.get("expected_move"),dict) else None; move_expansion=em is not None and (old_em is None or em>old_em*1.05); volume_ok=data.get("rows",0)>=20 and sum(r.get("volume",0) for r in data.get("option_chain",[]))>0; gamma_blast_qualified=all([directional_ok,confidence_ok,liquidity_ok,gamma_position_ok,dealer_ok,gamma_acceleration,move_expansion,volume_ok]); selection=select_strikes(data["spot"],data["option_chain"],bias,gamma_blast=(mode=="gamma_blast"),expected_move=em,gamma_blast_qualified=gamma_blast_qualified); trade_allowed=directional_ok and confidence_ok and liquidity_ok and selection["eligible"]
    return {"mode":"READ_ONLY","execution":"DISABLED","strategy":"GAMMA_BLAST" if mode=="gamma_blast" else "DIRECTIONAL","bias":bias,"confidence":data["confidence"],"risk_gate":{"directional_signal":directional_ok,"confidence":confidence_ok,"liquidity":liquidity_ok,"gamma_position":gamma_position_ok,"dealer_flow":dealer_ok,"gamma_acceleration":gamma_acceleration,"expected_move_expansion":move_expansion,"volume":volume_ok,"trade_allowed":trade_allowed},"strike_selection":selection,"intelligence":data.get("intelligence")}

@app.get("/api/v1/final-decision")
async def final_decision_api(strategy: str="directional"):
    mode=strategy.strip().lower()
    if mode not in {"directional","gamma_blast"}: raise HTTPException(400,"strategy must be directional or gamma_blast")
    try: data=await snapshot()
    except Exception as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
    result=final_decision(data,cache.get("previous_snapshot"),mode)
    return {"mode":"READ_ONLY","strategy":mode,"timestamp":data["timestamp"],"spot":data["spot"],"decision":result}

@app.post("/api/v1/replay/decisions")
async def replay_decisions_api(payload: dict[str,Any]):
    snapshots=payload.get("snapshots")
    if not isinstance(snapshots,list) or not snapshots: raise HTTPException(400,"snapshots must be a non-empty list")
    clean=[x for x in snapshots if isinstance(x,dict)]
    if len(clean)!=len(snapshots): raise HTTPException(400,"every snapshot must be an object")
    return {"mode":"READ_ONLY_REPLAY","decision_stack":replay_signal_stack(clean)}

@app.get("/api/v1/historical")
async def historical(interval: str="5minute",start_time: int|None=None,end_time: int|None=None,scrip_codes: str|None=None):
    if not start_time or not end_time: raise HTTPException(400,"start_time and end_time are required as epoch milliseconds")
    if start_time>end_time: raise HTTPException(400,"start_time must not be after end_time")
    allowed={"1minute","2minute","3minute","4minute","5minute","10minute","15minute","30minute","60minute","120minute","180minute","240minute","1day","1week","1month"}
    if interval not in allowed: raise HTTPException(400,"unsupported historical interval")
    codes=scrip_codes or NIFTY_SCRIP_CODE
    if len([x for x in codes.split(",") if x.strip()])>5: raise HTTPException(400,"maximum 5 scrip codes per request")
    try: return {"interval":interval,"scrip_codes":codes,"data":await api_get(f"/market/historical/{interval}",{"scrip-codes":codes,"start_time":start_time,"end_time":end_time})}
    except Exception as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc

@app.post("/api/v1/replay")
async def replay_api(payload: dict[str,Any]):
    if isinstance(payload.get("snapshots"),list):
        snapshots=payload.get("snapshots")
        if not snapshots: raise HTTPException(400,"snapshots must be a non-empty list")
        return {"mode":"READ_ONLY_REPLAY","decision_stack":replay_signal_stack([x for x in snapshots if isinstance(x,dict)])}
    points=replay(normalize_candles(payload,payload.get("scrip_code"))); return {"mode":"READ_ONLY_REPLAY","summary":summary(points),"points":to_dict(points)}

@app.get("/api/v1/trading/status")
def trading_status(): return {"enabled":False,"mode":"READ_ONLY","order_placement":False,"order_modification":False,"order_cancellation":False}
@app.post("/api/v1/trading/orders",status_code=503)
def trading_disabled(): raise HTTPException(503,"trading is disabled")

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try: payload=cache.get("snapshot") or await snapshot()
            except Exception as exc: payload={"data_integrity":"UNAVAILABLE","error":str(exc),"timestamp":datetime.now(timezone.utc).isoformat()}
            try: await websocket.send_json(payload)
            except (WebSocketDisconnect,RuntimeError): break
            await asyncio.sleep(POLL_SECONDS)
    except WebSocketDisconnect: pass
    finally:
        try: await websocket.close()
        except Exception: pass
