from __future__ import annotations

import asyncio
import math
import os
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

BASE = "https://api.indstocks.com"
TOKEN = (os.getenv("INDSTOCKS_API_TOKEN") or os.getenv("INDSTOCKS_TOKEN") or "").strip()
NIFTY_ID = os.getenv("NIFTY_SECURITY_ID", "40000001")
EXPIRY = os.getenv("NIFTY_EXPIRY", "").strip()
POLL_SECONDS = max(5.0, float(os.getenv("POLL_SECONDS", "15")))

app = FastAPI(title="QuantNifty Next", version="1.2.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
cache: dict[str, Any] = {"snapshot": None, "updated_at": None}


async def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not TOKEN:
        raise RuntimeError("INDSTOCKS_API_TOKEN is not configured")
    headers = {"Authorization": TOKEN, "Accept": "application/json"}
    last = "provider request failed"
    for attempt in range(4):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(BASE + path, params=params, headers=headers)
            if response.status_code == 429 or response.status_code >= 500:
                last = f"HTTP {response.status_code}"
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            if response.status_code >= 400:
                try:
                    payload = response.json()
                except Exception:
                    payload = {}
                detail = payload.get("debug_info") or payload.get("message") or payload.get("error")
                raise RuntimeError(f"HTTP {response.status_code}: {detail or 'provider rejected request'}")
            return response.json()
        except RuntimeError:
            raise
        except Exception as exc:
            last = str(exc)
            await asyncio.sleep(0.5 * (2**attempt))
    raise RuntimeError(last)


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def norm_leg(leg: dict[str, Any], strike: float, side: str) -> dict[str, Any]:
    g = leg.get("greeks") or {}
    return {"strike": float(strike), "side": side, "last_price": num(leg.get("last_price")), "oi": num(leg.get("oi")), "previous_oi": num(leg.get("previous_oi")), "volume": num(leg.get("volume")), "bid": num(leg.get("top_bid_price", leg.get("bid"))), "ask": num(leg.get("top_ask_price", leg.get("ask"))), "iv": num(leg.get("iv")), "delta": num(g.get("delta", leg.get("delta"))), "gamma": num(g.get("gamma", leg.get("gamma"))), "vega": num(g.get("vega", leg.get("vega"))), "theta": num(g.get("theta", leg.get("theta")))}


def flatten_chain(data: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    root = data.get("data") or data
    strikes = root.get("strikes") or root.get("option_chain") or {}
    rows: list[dict[str, Any]] = []
    for key, value in (strikes.items() if isinstance(strikes, dict) else []):
        try: strike = float(key)
        except (TypeError, ValueError): continue
        if not isinstance(value, dict): continue
        ce = value.get("ce") or value.get("call") or value.get("CE") or {}
        pe = value.get("pe") or value.get("put") or value.get("PE") or {}
        if ce: rows.append(norm_leg(ce, strike, "CE"))
        if pe: rows.append(norm_leg(pe, strike, "PE"))
    return num(root.get("underlying_ltp", root.get("underlying_price"))), rows


def max_pain(rows: list[dict[str, Any]]) -> float | None:
    strikes = sorted({r["strike"] for r in rows})
    if not strikes: return None
    best, best_loss = None, float("inf")
    for expiry_price in strikes:
        loss = sum((max(0.0, expiry_price-r["strike"]) if r["side"] == "CE" else max(0.0, r["strike"]-expiry_price)) * r["oi"] for r in rows)
        if loss < best_loss: best, best_loss = expiry_price, loss
    return best


def expected_move(spot: float, atm_iv: float | None, expiry: str) -> dict[str, float] | None:
    if spot <= 0 or not atm_iv or atm_iv <= 0: return None
    try: days = max(1, (date.fromisoformat(expiry) - date.today()).days)
    except ValueError: days = 1
    move = spot * (atm_iv / 100.0) * math.sqrt(days / 365.0)
    return {"move": move, "lower": spot-move, "upper": spot+move, "days": float(days), "iv": atm_iv}


def analytics(spot: float, rows: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [r for r in rows if r["side"] == "CE"]; puts = [r for r in rows if r["side"] == "PE"]
    call_oi, put_oi = sum(r["oi"] for r in calls), sum(r["oi"] for r in puts)
    call_doi, put_doi = sum(r["oi"]-r["previous_oi"] for r in calls), sum(r["oi"]-r["previous_oi"] for r in puts)
    pcr = put_oi/call_oi if call_oi else None
    call_iv = [r["iv"] for r in calls if r["iv"] > 0]; put_iv = [r["iv"] for r in puts if r["iv"] > 0]
    avg_call_iv = sum(call_iv)/len(call_iv) if call_iv else None; avg_put_iv = sum(put_iv)/len(put_iv) if put_iv else None
    iv_skew = avg_put_iv-avg_call_iv if avg_put_iv is not None and avg_call_iv is not None else None
    atm_strike = min({r["strike"] for r in rows}, key=lambda s: abs(s-spot), default=None)
    atm_rows = [r for r in rows if r["strike"] == atm_strike and r["iv"] > 0] if atm_strike is not None else []
    atm_iv = sum(r["iv"] for r in atm_rows)/len(atm_rows) if atm_rows else None
    gex = sum(r["gamma"]*r["oi"]*spot*spot*0.01*(-1 if r["side"] == "CE" else 1) for r in rows)
    dex = sum(r["delta"]*r["oi"]*(-1 if r["side"] == "CE" else 1) for r in rows)
    vanna_proxy = sum(r["vega"]*r["oi"]*(-1 if r["side"] == "CE" else 1) for r in rows)

    by_strike: dict[float, float] = {}
    for r in rows: by_strike[r["strike"]] = by_strike.get(r["strike"], 0.0) + r["gamma"]*r["oi"]*spot*spot*0.01*(-1 if r["side"] == "CE" else 1)
    points = sorted(by_strike.items()); gamma_flip = None
    for (a, ea), (b, eb) in zip(points, points[1:]):
        if ea == 0: gamma_flip = a; break
        if ea*eb < 0: gamma_flip = a+(b-a)*(abs(ea)/(abs(ea)+abs(eb))); break
    if gamma_flip is None and points: gamma_flip = min(points, key=lambda p: abs(p[1]))[0]

    walls = []
    for side in ("CE", "PE"):
        side_rows = [r for r in rows if r["side"] == side]
        if side_rows:
            w = max(side_rows, key=lambda r: r["oi"]*abs(r["gamma"]))
            walls.append({"side": side, "strike": w["strike"], "exposure": w["oi"]*abs(w["gamma"])})
    call_wall = next((w["strike"] for w in walls if w["side"] == "CE"), None)
    put_wall = next((w["strike"] for w in walls if w["side"] == "PE"), None)
    support = put_wall if put_wall is not None and put_wall <= spot else max((s for s in by_strike if s <= spot), default=put_wall)
    resistance = call_wall if call_wall is not None and call_wall >= spot else min((s for s in by_strike if s >= spot), default=call_wall)

    spreads = [((r["ask"]-r["bid"])/r["last_price"]) for r in rows if r["last_price"] > 0 and r["ask"] >= r["bid"] > 0]
    spread_quality = 100.0*(1.0-min(1.0, (sum(spreads)/len(spreads) if spreads else 1.0)*5.0))
    activity = min(100.0, math.log10(max(1.0, sum(r["volume"] for r in rows)+call_oi+put_oi))*7.5)
    liquidity = max(0.0, round(spread_quality*0.6+activity*0.4, 1))
    dealer_flow = "PUT_SUPPORT" if put_doi > call_doi else "CALL_RESISTANCE" if call_doi > put_doi else "BALANCED"

    score = 50.0; reasons: list[str] = []
    if pcr is not None:
        if pcr > 1.15: score += 15; reasons.append("put OI dominance")
        elif pcr < 0.85: score -= 15; reasons.append("call OI dominance")
    if iv_skew is not None:
        if iv_skew < -2: score += 10; reasons.append("lower put IV")
        elif iv_skew > 2: score -= 10; reasons.append("higher put IV")
    if put_doi > call_doi: score += 10; reasons.append("positive put OI flow")
    elif call_doi > put_doi: score -= 10; reasons.append("positive call OI flow")
    if gamma_flip is not None:
        score += 5 if spot > gamma_flip else -5; reasons.append("above gamma flip" if spot > gamma_flip else "below gamma flip")
    if dex > 0: score += 3; reasons.append("positive delta exposure")
    elif dex < 0: score -= 3; reasons.append("negative delta exposure")
    score = max(0.0, min(100.0, score)); bias = "BULLISH" if score >= 60 else "BEARISH" if score <= 40 else "NEUTRAL"
    structure = "ABOVE_GAMMA_FLIP" if gamma_flip is not None and spot > gamma_flip else "BELOW_GAMMA_FLIP" if gamma_flip is not None else "RANGE"

    return {"spot": spot, "pcr": pcr, "call_oi": call_oi, "put_oi": put_oi, "call_oi_change": call_doi, "put_oi_change": put_doi, "gex": gex, "dex": dex, "vanna_proxy": vanna_proxy, "iv_skew": iv_skew, "atm_iv": atm_iv, "gamma_flip": gamma_flip, "gamma_walls": walls, "max_pain": max_pain(rows), "expected_move": expected_move(spot, atm_iv, cache.get("expiry", "")), "support": support, "resistance": resistance, "structure": structure, "dealer_flow": dealer_flow, "liquidity_score": liquidity, "bullish_score": round(score, 1), "bearish_score": round(100-score, 1), "bias": bias, "confidence": round(50.0 if bias == "NEUTRAL" else min(99.0, 50.0+abs(score-50.0)), 1), "rationale": reasons, "data_integrity": "LIVE_PROVIDER", "rows": len(rows), "timestamp": datetime.now(timezone.utc).isoformat()}


async def snapshot() -> dict[str, Any]:
    expiry = EXPIRY
    if not expiry:
        response = await api_get("/market/instruments/expiries", {"underlying": "NIFTY", "segment": "DERIVATIVE"})
        values = response.get("data") or []
        if not isinstance(values, list) or not values: raise RuntimeError("provider returned no upcoming NIFTY expiries")
        expiry = str(values[0].get("expiry") if isinstance(values[0], dict) else values[0])
    cache["expiry"] = expiry
    raw = await api_get("/market/option-chain", {"exchange": "NSE", "segment": "INDEX", "underlying-scrip": NIFTY_ID, "expiry": expiry, "strike_count": 20})
    spot, rows = flatten_chain(raw)
    if spot <= 0: raise RuntimeError("provider returned invalid NIFTY spot")
    if len(rows) < 2: raise RuntimeError("provider returned an empty or incomplete option chain")
    result = analytics(spot, rows); result["expiry"] = expiry; result["expected_move"] = expected_move(spot, result["atm_iv"], expiry)
    cache["snapshot"], cache["updated_at"] = result, time.time(); return result


@app.get("/")
def root():
    path = os.path.join(os.path.dirname(__file__), "web", "index.html")
    return FileResponse(path) if os.path.exists(path) else {"service": "QuantNifty Next", "status": "ok"}

@app.get("/health")
def health(): return {"status": "ok", "provider": "INDstocks", "provider_configured": bool(TOKEN), "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/api/v1/status")
def status(): return {"status": "ok", "provider": "INDstocks", "provider_configured": bool(TOKEN), "cached": cache["snapshot"] is not None, "trading": "DISABLED", "analytics": ["OI_FLOW", "PCR", "GEX", "DEX", "IV_SKEW", "GAMMA_FLIP", "GAMMA_WALLS", "MAX_PAIN", "EXPECTED_MOVE", "MARKET_STRUCTURE", "DEALER_FLOW", "LIQUIDITY", "DIRECTION_SCORE"]}

@app.get("/api/v1/market")
async def market():
    try: return await snapshot()
    except Exception as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc

@app.get("/api/v1/analytics")
async def analytics_api(): return await market()

@app.get("/api/v1/trading/status")
def trading_status(): return {"enabled": False, "mode": "READ_ONLY", "order_placement": False, "order_modification": False, "order_cancellation": False}

@app.post("/api/v1/trading/orders", status_code=503)
def trading_disabled(): raise HTTPException(503, "trading is disabled")

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try: await websocket.send_json(await snapshot())
            except Exception as exc: await websocket.send_json({"data_integrity": "UNAVAILABLE", "error": str(exc), "timestamp": datetime.now(timezone.utc).isoformat()})
            await asyncio.sleep(POLL_SECONDS)
    except WebSocketDisconnect: pass
