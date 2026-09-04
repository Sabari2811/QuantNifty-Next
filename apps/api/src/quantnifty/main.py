from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

BASE = "https://api.indstocks.com"
# Runtime secret only. Keep the legacy name as a backwards-compatible fallback.
TOKEN = (os.getenv("INDSTOCKS_API_TOKEN") or os.getenv("INDSTOCKS_TOKEN") or "").strip()
NIFTY_ID = os.getenv("NIFTY_SECURITY_ID", "40000001")
EXPIRY = os.getenv("NIFTY_EXPIRY", "").strip()

app = FastAPI(title="QuantNifty Next", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
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
                last = f"HTTP {response.status_code}: {detail or 'provider rejected request'}"
                raise RuntimeError(last)
            return response.json()
        except RuntimeError:
            raise
        except Exception as exc:
            last = str(exc)
            await asyncio.sleep(0.5 * (2**attempt))
    raise RuntimeError(last)


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def norm_leg(leg: dict[str, Any], strike: float, side: str) -> dict[str, Any]:
    greeks = leg.get("greeks") or {}
    return {
        "strike": float(strike),
        "side": side,
        "last_price": _num(leg.get("last_price")),
        "oi": _num(leg.get("oi")),
        "previous_oi": _num(leg.get("previous_oi")),
        "volume": _num(leg.get("volume")),
        "bid": _num(leg.get("top_bid_price", leg.get("bid"))),
        "ask": _num(leg.get("top_ask_price", leg.get("ask"))),
        "iv": _num(leg.get("iv")),
        "delta": _num(greeks.get("delta", leg.get("delta"))),
        "gamma": _num(greeks.get("gamma", leg.get("gamma"))),
        "vega": _num(greeks.get("vega", leg.get("vega"))),
    }


def flatten_chain(data: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    root = data.get("data") or data
    strikes = root.get("strikes") or root.get("option_chain") or {}
    rows: list[dict[str, Any]] = []
    if isinstance(strikes, dict):
        items = strikes.items()
    elif isinstance(strikes, list):
        items = ((x.get("strike_price") or x.get("strike"), x) for x in strikes)
    else:
        items = []
    for key, value in items:
        try:
            strike = float(key)
        except (TypeError, ValueError):
            continue
        ce = value.get("ce") or value.get("call") or value.get("CE") or value.get("call_option") or {}
        pe = value.get("pe") or value.get("put") or value.get("PE") or value.get("put_option") or {}
        if ce:
            rows.append(norm_leg(ce, strike, "CE"))
        if pe:
            rows.append(norm_leg(pe, strike, "PE"))
    spot = _num(root.get("underlying_ltp", root.get("underlying_price")))
    return spot, rows


def analytics(spot: float, rows: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [x for x in rows if x["side"] == "CE"]
    puts = [x for x in rows if x["side"] == "PE"]
    call_oi = sum(x["oi"] for x in calls)
    put_oi = sum(x["oi"] for x in puts)
    pcr = put_oi / call_oi if call_oi else 0.0
    call_change = sum(x["oi"] - x["previous_oi"] for x in calls)
    put_change = sum(x["oi"] - x["previous_oi"] for x in puts)
    gex = sum(x["gamma"] * x["oi"] * (spot**2) * 0.01 * (1 if x["side"] == "PE" else -1) for x in rows)
    dex = sum(x["delta"] * x["oi"] * (1 if x["side"] == "CE" else -1) for x in rows)
    call_iv = [x["iv"] for x in calls if x["iv"] > 0]
    put_iv = [x["iv"] for x in puts if x["iv"] > 0]
    skew = (sum(put_iv) / len(put_iv) - sum(call_iv) / len(call_iv)) if call_iv and put_iv else 0.0

    walls = []
    for side in ("CE", "PE"):
        side_rows = [x for x in rows if x["side"] == side]
        if side_rows:
            wall = max(side_rows, key=lambda x: x["oi"] * abs(x["gamma"]))
            walls.append({"side": side, "strike": wall["strike"], "exposure": wall["oi"] * abs(wall["gamma"])})

    by_strike: dict[float, list[dict[str, Any]]] = {}
    for row in rows:
        by_strike.setdefault(row["strike"], []).append(row)
    points = []
    for strike in sorted(by_strike):
        exposure = sum(
            y["gamma"] * y["oi"] * (spot**2) * 0.01 * (1 if y["side"] == "PE" else -1)
            for y in by_strike[strike]
        )
        points.append((strike, exposure))

    flip = None
    for (a, ea), (b, eb) in zip(points, points[1:]):
        if ea == 0:
            flip = a
            break
        if ea * eb < 0:
            flip = a + (b - a) * (abs(ea) / (abs(ea) + abs(eb)))
            break

    score = 50.0
    score += 15 if pcr > 1.15 else (-15 if pcr < 0.85 else 0)
    score += 10 if skew > 2 else (-10 if skew < -2 else 0)
    score += 10 if put_change > call_change else (-10 if call_change > put_change else 0)
    score += 5 if flip is not None and spot > flip else (-5 if flip is not None else 0)
    score = max(0, min(100, score))
    bias = "BULLISH" if score >= 60 else ("BEARISH" if score <= 40 else "NEUTRAL")
    confidence = round(abs(score - 50) * 2 + 50 if bias != "NEUTRAL" else 50, 1)
    structure = "ABOVE_GAMMA_FLIP" if flip is not None and spot > flip else ("BELOW_GAMMA_FLIP" if flip is not None else "UNAVAILABLE")

    return {
        "spot": spot,
        "pcr": round(pcr, 3),
        "call_oi": call_oi,
        "put_oi": put_oi,
        "call_oi_change": call_change,
        "put_oi_change": put_change,
        "gex": gex,
        "dex": dex,
        "iv_skew": skew,
        "gamma_flip": flip,
        "gamma_walls": walls,
        "bullish_score": round(score, 1),
        "bearish_score": round(100 - score, 1),
        "bias": bias,
        "confidence": confidence,
        "structure": structure,
        "data_integrity": "LIVE_PROVIDER",
        "rows": len(rows),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def snapshot() -> dict[str, Any]:
    expiry = EXPIRY
    if not expiry:
        response = await api_get("/market/instruments/expiries", {"underlying": "NIFTY", "segment": "DERIVATIVE"})
        values = response.get("data") or []
        if not isinstance(values, list) or not values:
            raise RuntimeError("provider returned no upcoming NIFTY expiries")
        expiry = str(values[0].get("expiry") if isinstance(values[0], dict) else values[0])
    raw = await api_get(
        "/market/option-chain",
        {
            "exchange": "NSE",
            "segment": "INDEX",
            "underlying-scrip": NIFTY_ID,
            "expiry": expiry,
            "strike_count": 20,
        },
    )
    spot, rows = flatten_chain(raw)
    if spot <= 0:
        raise RuntimeError("provider returned invalid NIFTY spot")
    if len(rows) < 2:
        raise RuntimeError("provider returned an empty or incomplete option chain")
    result = analytics(spot, rows)
    result["expiry"] = expiry
    cache["snapshot"] = result
    cache["updated_at"] = time.time()
    return result


@app.get("/")
def root():
    path = os.path.join(os.path.dirname(__file__), "web", "index.html")
    return FileResponse(path) if os.path.exists(path) else {"service": "QuantNifty Next", "status": "ok"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "provider": "INDstocks",
        "provider_configured": bool(TOKEN),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/status")
def status():
    return {
        "status": "ok",
        "provider": "INDstocks",
        "provider_configured": bool(TOKEN),
        "cached": cache["snapshot"] is not None,
        "live_market_validation": "available via /api/v1/market",
    }


@app.get("/api/v1/market")
async def market():
    try:
        return await snapshot()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/analytics")
async def analytics_api():
    return await market()


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                data = await snapshot()
                await websocket.send_json(data)
            except Exception as exc:
                await websocket.send_json({"data_integrity": "UNAVAILABLE", "error": str(exc)})
            await asyncio.sleep(float(os.getenv("POLL_SECONDS", "15")))
    except WebSocketDisconnect:
        pass
