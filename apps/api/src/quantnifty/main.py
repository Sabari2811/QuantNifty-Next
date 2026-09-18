from __future__ import annotations

import asyncio
import math
import os
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from quantnifty.market_brain import decision_intelligence
from quantnifty.replay import normalize_candles, replay, summary, to_dict
from quantnifty.strike_selector import select_strikes
from quantnifty.institutional_engine import final_decision, replay_signal_stack
from quantnifty.backtest import BacktestConfig, run_backtest, validation_report
from quantnifty.recording_api import router as recording_router
from quantnifty.research_api import router as research_router
from quantnifty.paper_ledger_api import router as paper_ledger_router
from quantnifty.decision_validation import validate_snapshot
from quantnifty.learning_store import learning_status, record_decision, record_snapshot
from quantnifty.after_market_scheduler import after_market_loop
from quantnifty.live_paper_manager import LivePaperManager
from quantnifty.policy_runtime import load_future_policy
from quantnifty.market_session import closed_payload, is_live_market_session, market_session_state, seconds_until_next_open

BASE = "https://api.indstocks.com"
TOKEN = (os.getenv("INDSTOCKS_API_TOKEN") or os.getenv("INDSTOCKS_TOKEN") or "").strip()
NIFTY_ID = os.getenv("NIFTY_SECURITY_ID", "40000001")
NIFTY_SCRIP_CODE = os.getenv("NIFTY_SCRIP_CODE", "NSE_40000001")
EXPIRY = os.getenv("NIFTY_EXPIRY", "").strip()
POLL_SECONDS = max(2.0, float(os.getenv("POLL_SECONDS", "2")))
IST = ZoneInfo("Asia/Kolkata")

app = FastAPI(title="QuantNifty Next", version="1.9.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
cache: dict[str, Any] = {"snapshot": None, "previous_snapshot": None, "updated_at": None}
app.include_router(recording_router)
app.include_router(research_router)
app.include_router(paper_ledger_router)
live_paper = LivePaperManager()
active_policy: dict[str, Any] | None = None

async def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not TOKEN: raise RuntimeError("INDSTOCKS_API_TOKEN is not configured")
    headers = {"Authorization": TOKEN, "Accept": "application/json"}
    last = "provider request failed"
    for attempt in range(4):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(BASE + path, params=params, headers=headers)
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

def norm_leg(leg: dict[str, Any], strike: float, side: str, expiry: str | None = None) -> dict[str, Any]:
    g = leg.get("greeks") or {}
    return {"strike":float(strike),"side":side,"expiry":str(leg.get("expiry") or expiry or ""),"security_id":str(leg.get("security_id") or ""),"trading_symbol":str(leg.get("trading_symbol") or ""),"last_price":num(leg.get("last_price")),"previous_close":num(leg.get("previous_close_price",leg.get("previous_close"))),"oi":num(leg.get("oi")),"previous_oi":num(leg.get("previous_oi")),"volume":num(leg.get("volume")),"bid":num(leg.get("top_bid_price",leg.get("bid"))),"bid_qty":num(leg.get("top_bid_quantity",leg.get("bid_qty"))),"ask":num(leg.get("top_ask_price",leg.get("ask"))),"ask_qty":num(leg.get("top_ask_quantity",leg.get("ask_qty"))),"iv":num(leg.get("iv")),"delta":num(g.get("delta",leg.get("delta"))),"gamma":num(g.get("gamma",leg.get("gamma"))),"theta":num(g.get("theta",leg.get("theta"))),"vega":num(g.get("vega",leg.get("vega")))}

def flatten_chain(data: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    root=data.get("data") or data; strikes=root.get("strikes") or root.get("option_chain") or {}; items=strikes.items() if isinstance(strikes,dict) else []; rows=[]
    for key,value in items:
        try: strike=float(key)
        except (TypeError, ValueError): continue
        if not isinstance(value,dict): continue
        for leg,side in ((value.get("ce") or value.get("call") or value.get("CE") or {},"CE"),(value.get("pe") or value.get("put") or value.get("PE") or {},"PE")):
            if leg: rows.append(norm_leg(leg,strike,side,str(root.get("expiry") or "")))
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
    if not is_live_market_session():
        raise RuntimeError("NSE live market session is closed; live provider access is disabled")
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
    global active_policy
    while True:
        if not is_live_market_session():
            await asyncio.sleep(min(POLL_SECONDS, seconds_until_next_open()))
            continue
        try:
            data = await snapshot()
            if str(data.get("data_integrity")) == "LIVE_PROVIDER":
                try:
                    decision_input = dict(data)
                    if active_policy is not None:
                        decision_input["_adaptive_policy"] = active_policy
                        decision_input["policy_target_day"] = datetime.now(IST).date().isoformat()
                    decision = final_decision(decision_input, cache.get("previous_snapshot"), "adaptive", "LIVE")
                    record_snapshot(data)
                    record_decision(data, decision)
                    live_paper.process(data, decision)
                except Exception:
                    record_snapshot(data)
        except Exception:
            pass
        await asyncio.sleep(POLL_SECONDS)

@app.on_event("startup")
async def start_background_refresh():
    global active_policy
    active_policy = load_future_policy()
    app.state.market_refresh_task=asyncio.create_task(continuous_market_refresh())
    app.state.after_market_task=asyncio.create_task(after_market_loop())

@app.on_event("shutdown")
async def stop_background_refresh():
    for task_name in ("market_refresh_task", "after_market_task"):
        task=getattr(app.state,task_name,None)
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

@app.get("/backtest")
def backtest_page():
    path=os.path.join(os.path.dirname(__file__),"web","backtest.html"); return FileResponse(path)

@app.get("/health")
def health():
    state=market_session_state()
    return {"status":"ok","provider":"INDstocks","provider_configured":bool(TOKEN),"market_session":state,"live_provider_connected":False,"timestamp":datetime.now(timezone.utc).isoformat()}
@app.get("/api/v1/health")
def api_health(): return health()
@app.get("/api/v1/status")
def status():
    state=market_session_state()
    return {"status":"ok","provider":"INDstocks","provider_configured":bool(TOKEN),"cached":cache["snapshot"] is not None and bool(state["open"]),"updated_at":cache["updated_at"],"refresh_interval_seconds":POLL_SECONDS,"market_session":state,"live_provider_connected":False,"trading":"DISABLED","learning":learning_status(),"active_future_policy":(active_policy or {}).get("policy"),"live_paper_status":("OPEN" if live_paper.active is not None else "IDLE"),"analytics":["OI_FLOW","PCR","GEX","DEX","VANNA_PROXY","IV_SKEW","GAMMA_FLIP","GAMMA_WALLS","MAX_PAIN","EXPECTED_MOVE","MARKET_STRUCTURE","DEALER_FLOW","LIQUIDITY","DIRECTION_SCORE","STRIKE_SELECTION","MARKET_STATE","EVENT_DETECTION","MOVE_ATTRIBUTION","SIGNAL_DNA","PRESSURE_MAP","NO_TRADE_INTELLIGENCE","INSTITUTIONAL_SIGNAL","RISK_ENGINE","FINAL_DECISION","EXECUTION_PLAN","BACKTEST_ENGINE","OOS_VALIDATION","COST_MODEL","REGIME_VALIDATION","LIVE_LEARNING_RECORDER","PAPER_OUTCOME_TRACKER","AFTER_MARKET_LAB","ADAPTIVE_POLICY"],"replay":"AVAILABLE","backtest":"AVAILABLE"}

@app.get("/api/v1/learning/status")
def learning_status_api(): return learning_status()

@app.get("/api/v1/market")
async def market():
    if not is_live_market_session():
        return closed_payload()
    cached = cache.get("snapshot")
    if cached is not None:
        return cached
    try:
        return await snapshot()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
@app.get("/api/v1/analytics")
async def analytics_api(): return await market()
@app.get("/api/v1/intelligence")
async def intelligence_api():
    if not is_live_market_session():
        return closed_payload()
    try:
        data=await snapshot(); return {"timestamp":data["timestamp"],"spot":data["spot"],"expiry":data.get("expiry"),"intelligence":data["intelligence"]}
    except Exception as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc

@app.get("/api/v1/decision")
async def decision(strategy: str="directional"):
    mode=strategy.strip().lower()
    if mode not in {"directional","gamma_blast","adaptive"}: raise HTTPException(400,"strategy must be directional, gamma_blast, or adaptive")
    if not is_live_market_session(): return closed_payload()
    try: data=await snapshot()
    except Exception as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
    result=final_decision(data,cache.get("previous_snapshot"),mode)
    return {"mode":"READ_ONLY","strategy":mode,"timestamp":data["timestamp"],"spot":data["spot"],"decision":result,"validation":validate_snapshot(data,"LIVE")}

@app.get("/api/v1/final-decision")
async def final_decision_api(strategy: str="directional"):
    mode=strategy.strip().lower()
    if mode not in {"directional","gamma_blast","adaptive"}: raise HTTPException(400,"strategy must be directional, gamma_blast, or adaptive")
    if not is_live_market_session(): return closed_payload()
    try: data=await snapshot()
    except Exception as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
    result=final_decision(data,cache.get("previous_snapshot"),mode)
    return {"mode":"READ_ONLY","strategy":mode,"timestamp":data["timestamp"],"spot":data["spot"],"decision":result,"validation":validate_snapshot(data,"LIVE")}

def _quote_depth(item: dict[str, Any]) -> tuple[float | None, float | None]:
    depth = item.get("market_depth") if isinstance(item, dict) else {}
    levels = depth.get("depth") if isinstance(depth, dict) else []
    if not isinstance(levels, list) or not levels:
        return None, None
    first = levels[0] if isinstance(levels[0], dict) else {}
    buy = first.get("buy") if isinstance(first.get("buy"), dict) else {}
    sell = first.get("sell") if isinstance(first.get("sell"), dict) else {}
    bid = num(buy.get("price")) if buy else None
    ask = num(sell.get("price")) if sell else None
    return (bid if bid and bid > 0 else None), (ask if ask and ask > 0 else None)


def _live_quote_item(payload: dict[str, Any], code: str) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    item = data.get(code) if isinstance(data, dict) else None
    return item if isinstance(item, dict) else {}


@app.get("/api/v1/paper/live-monitor")
async def paper_live_monitor():
    """Return the active paper trade marked from a fresh provider quote."""
    if not is_live_market_session():
        return {"mode": "READ_ONLY_PAPER", "status": "MARKET_CLOSED", "trade": None}
    instrument = live_paper.instrument if isinstance(live_paper.instrument, dict) else None
    snapshot_now = cache.get("snapshot") or {}
    intelligence_now = snapshot_now.get("intelligence") if isinstance(snapshot_now.get("intelligence"), dict) else {}
    execution_now = intelligence_now.get("execution_plan") if isinstance(intelligence_now.get("execution_plan"), dict) else {}
    plan_instrument = execution_now.get("instrument") if isinstance(execution_now.get("instrument"), dict) else None
    codes = [NIFTY_SCRIP_CODE]
    option_code = ""
    plan_option_code = ""
    if instrument:
        security_id = str(instrument.get("security_id") or "").strip()
        if security_id:
            option_code = f"NFO_{security_id}"
            codes.append(option_code)
    if plan_instrument:
        plan_security_id = str(plan_instrument.get("security_id") or "").strip()
        if plan_security_id and plan_security_id != str((instrument or {}).get("security_id") or "").strip():
            plan_option_code = f"NFO_{plan_security_id}"
            codes.append(plan_option_code)
    try:
        quotes = await api_get("/market/quotes/full", {"scrip-codes": ",".join(codes)})
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"live quote unavailable: {exc}") from exc
    spot_item = _live_quote_item(quotes, NIFTY_SCRIP_CODE)
    spot = num(spot_item.get("live_price"))
    if spot <= 0:
        raise HTTPException(status_code=503, detail="live NIFTY quote unavailable")
    if not instrument:
        return {"mode": "READ_ONLY_PAPER", "status": "NO_ACTIVE_TRADE", "spot": round(spot, 4), "timestamp": datetime.now(timezone.utc).isoformat(), "provider_timestamp": quotes.get("timestamp"), "quote_source": "INDstocks /market/quotes/full"}
    option_item = _live_quote_item(quotes, option_code)
    ltp = num(option_item.get("live_price"))
    bid, ask = _quote_depth(option_item)
    plan_item = _live_quote_item(quotes, plan_option_code) if plan_option_code else {}
    plan_ltp = num(plan_item.get("live_price"))
    trade = dict(live_paper._trade_view(cache.get("snapshot") or {}))
    # Front-end display is option-native: current price is the provider LTP for the exact
    # active contract.  Executable exit/P&L remain BID-marked, but are kept separate so
    # a wide option spread can never make the UI look like it is showing another price.
    current_ltp = round(ltp, 6) if ltp > 0 else None
    executable_exit = round(bid, 6) if bid is not None else current_ltp
    trade["current_spot"] = round(spot, 4)
    trade["current_ltp"] = current_ltp
    trade["current_bid"] = round(bid, 6) if bid is not None else None
    trade["current_ask"] = round(ask, 6) if ask is not None else None
    trade["current_spread"] = round(ask - bid, 6) if bid is not None and ask is not None and ask >= bid else None
    trade["current_price"] = current_ltp
    trade["mark_price"] = current_ltp
    trade["exit_price"] = executable_exit
    trade["exit_price_source"] = "BID" if bid is not None else "LTP"
    trade["mark_source"] = "LTP"
    trade["pnl_mark_price"] = executable_exit
    trade["pnl_mark_source"] = trade["exit_price_source"]
    trade["pnl"] = round((executable_exit - trade["entry_price"]) * trade["quantity"], 4) if executable_exit is not None else None
    trade["unrealized_pnl"] = trade["pnl"]
    trade["pnl_pct"] = round((executable_exit - trade["entry_price"]) / trade["entry_price"] * 100.0, 4) if executable_exit is not None and trade["entry_price"] else None
    trade["unrealized_pnl_pct"] = trade["pnl_pct"]
    trade["movement"] = "UP" if current_ltp is not None and current_ltp > trade["entry_price"] else "DOWN" if current_ltp is not None and current_ltp < trade["entry_price"] else "FLAT"
    # Keep the decision engine's risk budget, but expose the SL/target as option-premium
    # values using the entry delta. They are no longer recalculated from the cached spot quote.
    entry_risk = trade.get("entry_risk") if isinstance(trade.get("entry_risk"), dict) else {}
    entry_delta = trade.get("entry_delta")
    native_levels = _delta_premium_levels(trade["entry_price"], entry_delta, entry_risk)
    trade["premium_sl"] = native_levels.get("premium_stop")
    trade["premium_target"] = native_levels.get("premium_target")
    trade["premium_sl_distance"] = native_levels.get("premium_stop_distance")
    trade["premium_target_distance"] = native_levels.get("premium_target_distance")
    trade["delta_risk_method"] = "ENTRY_PREMIUM_PLUS_ENTRY_DELTA_X_NIFTY_POINTS"
    trade["option_price_source"] = "INDstocks /market/quotes/full live_price"
    trade["mark_timestamp"] = datetime.now(timezone.utc).isoformat()
    trade["quote_source"] = "INDstocks /market/quotes/full"
    trade["quote_quality"] = "OK" if ltp > 0 and (bid is None or ask is None or bid <= ask) else "INVALID_BOOK"
    trade["instrument"] = {**instrument, "expiry": instrument.get("expiry") or snapshot_now.get("expiry")}
    if plan_instrument:
        trade["brain_plan_instrument"] = {**plan_instrument, "expiry": plan_instrument.get("expiry") or snapshot_now.get("expiry")}
        trade["brain_plan_ltp"] = round(plan_ltp, 6) if plan_ltp > 0 else None
        trade["brain_plan_is_active_contract"] = str(plan_instrument.get("security_id") or "") == str(instrument.get("security_id") or "")
    return {"mode": "READ_ONLY_PAPER", "status": "OPEN", "spot": round(spot, 4), "timestamp": trade["mark_timestamp"], "provider_timestamp": quotes.get("timestamp"), "quote_source": trade["quote_source"], "trade": trade}

@app.post("/api/v1/replay/decisions")
async def replay_decisions_api(payload: dict[str,Any]):
    snapshots=payload.get("snapshots")
    if not isinstance(snapshots,list) or not snapshots: raise HTTPException(400,"snapshots must be a non-empty list")
    if any(not isinstance(x,dict) for x in snapshots): raise HTTPException(400,"every snapshot must be an object")
    strategy=str(payload.get("strategy") or "directional").strip().lower()
    if strategy not in {"directional","gamma_blast","adaptive"}: raise HTTPException(400,"strategy must be directional, gamma_blast, or adaptive")
    stack=replay_signal_stack(snapshots,strategy) if strategy else replay_signal_stack(snapshots)
    return {"mode":"READ_ONLY_REPLAY","strategy":strategy,"decision_stack":stack}

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
        if any(not isinstance(x,dict) for x in snapshots): raise HTTPException(400,"every snapshot must be an object")
        strategy=str(payload.get("strategy") or "directional").strip().lower()
        if strategy not in {"directional","gamma_blast","adaptive"}: raise HTTPException(400,"strategy must be directional, gamma_blast, or adaptive")
        return {"mode":"READ_ONLY_REPLAY","strategy":strategy,"decision_stack":replay_signal_stack(snapshots,strategy)}
    points=replay(normalize_candles(payload,payload.get("scrip_code"))); return {"mode":"READ_ONLY_REPLAY","summary":summary(points),"points":to_dict(points)}

@app.post("/api/v1/backtest")
async def backtest_api(payload: dict[str,Any]):
    snapshots=payload.get("snapshots")
    if not isinstance(snapshots,list) or len(snapshots)<2: raise HTTPException(400,"snapshots must contain at least 2 snapshot objects")
    if any(not isinstance(x,dict) for x in snapshots): raise HTTPException(400,"every snapshot must be an object")
    mode=str(payload.get("strategy") or "directional").strip().lower()
    if mode not in {"directional","gamma_blast","adaptive"}: raise HTTPException(400,"strategy must be directional, gamma_blast, or adaptive")
    raw=payload.get("config") or {}
    try:
        cfg=BacktestConfig(**{k:raw[k] for k in raw if k in BacktestConfig.__dataclass_fields__})
        return run_backtest(snapshots,mode,cfg)
    except (TypeError,ValueError) as exc: raise HTTPException(400,f"invalid backtest configuration: {exc}") from exc

@app.post("/api/v1/validation")
async def validation_api(payload: dict[str,Any]):
    snapshots=payload.get("snapshots")
    if not isinstance(snapshots,list) or len(snapshots)<2: raise HTTPException(400,"snapshots must contain at least 2 snapshot objects")
    if any(not isinstance(x,dict) for x in snapshots): raise HTTPException(400,"every snapshot must be an object")
    mode=str(payload.get("strategy") or "directional").strip().lower()
    if mode not in {"directional","gamma_blast","adaptive"}: raise HTTPException(400,"strategy must be directional, gamma_blast, or adaptive")
    raw=payload.get("config") or {}
    try:
        cfg=BacktestConfig(**{k:raw[k] for k in raw if k in BacktestConfig.__dataclass_fields__})
        result=validation_report(snapshots,mode,cfg)
        result["decision_validation"]=[validate_snapshot(s,"BACKTEST") for s in snapshots]
        return result
    except (TypeError,ValueError) as exc: raise HTTPException(400,f"invalid validation configuration: {exc}") from exc

@app.websocket("/ws")
@app.websocket("/ws/market")
async def websocket_market(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            if not is_live_market_session():
                try:
                    await ws.send_json(closed_payload())
                except WebSocketDisconnect:
                    return
                await asyncio.sleep(min(POLL_SECONDS, seconds_until_next_open()))
                continue
            try:
                data = cache.get("snapshot")
                if data is None:
                    data = await snapshot()
                await ws.send_json(data)
            except WebSocketDisconnect:
                return
            except Exception as exc:
                try:
                    await ws.send_json({"error": str(exc), "mode": "READ_ONLY", "data_integrity": "UNAVAILABLE"})
                except Exception:
                    return
            await asyncio.sleep(POLL_SECONDS)
    except WebSocketDisconnect:
        return
