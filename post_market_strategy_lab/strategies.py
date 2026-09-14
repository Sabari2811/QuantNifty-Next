from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class StrategySpec:
    name: str
    family: str
    description: str
    signal: Callable[[dict[str, Any], dict[str, Any] | None], str]


def _f(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _s(s: dict[str, Any], *keys: str) -> float:
    for k in keys:
        if k in s and s[k] is not None:
            return _f(s[k])
    return 0.0


def _technical(snapshot: dict[str, Any]) -> dict[str, float]:
    t = snapshot.get("technicals") or snapshot.get("indicators") or {}
    return {
        "spot": _s(snapshot, "spot", "nifty", "close"),
        "vwap": _s(t, "vwap") or _s(snapshot, "vwap"),
        "ema9": _s(t, "ema9", "ema_9") or _s(snapshot, "ema9"),
        "ema21": _s(t, "ema21", "ema_21") or _s(snapshot, "ema21"),
        "ema50": _s(t, "ema50", "ema_50") or _s(snapshot, "ema50"),
        "rsi": _s(t, "rsi", "RSI") or _s(snapshot, "rsi"),
        "bb_upper": _s(t, "bb_upper", "upper_band") or _s(snapshot, "bb_upper"),
        "bb_lower": _s(t, "bb_lower", "lower_band") or _s(snapshot, "bb_lower"),
        "volume_ratio": _s(t, "volume_ratio", "volume_ratio_20") or _s(snapshot, "volume_ratio"),
        "atr": _s(t, "atr", "ATR") or _s(snapshot, "atr"),
    }


def _pressure(snapshot: dict[str, Any]) -> dict[str, float | str]:
    return {
        "oi_bias": str(snapshot.get("oi_bias") or snapshot.get("pressure_bias") or "NEUTRAL").upper(),
        "gex": _s(snapshot, "gex"),
        "gamma_flip": _s(snapshot, "gamma_flip"),
        "atm_iv": _s(snapshot, "atm_iv"),
        "realized_vol": _s(snapshot, "realized_vol", "rv"),
        "expected_move": _s((snapshot.get("expected_move") or {}), "move"),
        "market_bias": str(snapshot.get("bias") or "NEUTRAL").upper(),
        "market_regime": str(snapshot.get("regime") or snapshot.get("structure") or "").upper(),
    }


def vwap_momentum(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    x = _technical(snapshot); p = _pressure(snapshot)
    if x["spot"] > x["vwap"] and x["rsi"] > 55 and x["volume_ratio"] >= 1.5 and p["market_bias"] != "BEARISH": return "BULLISH"
    if x["spot"] < x["vwap"] and x["rsi"] < 45 and x["volume_ratio"] >= 1.5 and p["market_bias"] != "BULLISH": return "BEARISH"
    return "NEUTRAL"


def vwap_ema(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    x = _technical(snapshot)
    if x["spot"] > x["vwap"] and x["ema9"] > x["ema21"]: return "BULLISH"
    if x["spot"] < x["vwap"] and x["ema9"] < x["ema21"]: return "BEARISH"
    return "NEUTRAL"


def ema_trend(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    x = _technical(snapshot)
    if x["ema9"] > x["ema21"] > x["ema50"] and x["spot"] > x["ema50"]: return "BULLISH"
    if x["ema9"] < x["ema21"] < x["ema50"] and x["spot"] < x["ema50"]: return "BEARISH"
    return "NEUTRAL"


def rsi_bollinger_vwap(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    x = _technical(snapshot)
    if x["rsi"] < 30 and x["bb_lower"] and x["spot"] <= x["bb_lower"] and x["vwap"] > x["spot"]: return "BULLISH"
    if x["rsi"] > 70 and x["bb_upper"] and x["spot"] >= x["bb_upper"] and x["vwap"] < x["spot"]: return "BEARISH"
    return "NEUTRAL"


def oi_flow(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    p = _pressure(snapshot)
    return p["oi_bias"] if p["oi_bias"] in {"BULLISH", "BEARISH"} else "NEUTRAL"


def oi_vwap(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    a = oi_flow(snapshot, previous); b = vwap_ema(snapshot, previous)
    return a if a == b else "NEUTRAL"


def gex_vwap(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    x = _technical(snapshot); p = _pressure(snapshot)
    if p["gex"] < 0 and x["spot"] > x["vwap"]: return "BULLISH"
    if p["gex"] < 0 and x["spot"] < x["vwap"]: return "BEARISH"
    return "NEUTRAL"


def gamma_flip_price_action(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    x = _technical(snapshot); p = _pressure(snapshot)
    flip = p["gamma_flip"]
    if flip and x["spot"] > flip and x["spot"] > x["vwap"]: return "BULLISH"
    if flip and x["spot"] < flip and x["spot"] < x["vwap"]: return "BEARISH"
    return "NEUTRAL"


def iv_rv_trend(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    x = _technical(snapshot); p = _pressure(snapshot)
    if not p["realized_vol"] or not p["atm_iv"]: return "NEUTRAL"
    if x["spot"] > x["vwap"] and x["ema9"] > x["ema21"] and p["atm_iv"] >= p["realized_vol"]: return "BULLISH"
    if x["spot"] < x["vwap"] and x["ema9"] < x["ema21"] and p["atm_iv"] >= p["realized_vol"]: return "BEARISH"
    return "NEUTRAL"


def market_structure_oi(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    p = _pressure(snapshot); structure = p["market_regime"]
    if p["oi_bias"] in {"BULLISH", "BEARISH"} and any(k in structure for k in ("TREND", "BREAKOUT", "BREAKDOWN")):
        return p["oi_bias"]
    return "NEUTRAL"


def vwap_oi_gex(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    a = oi_vwap(snapshot, previous); b = gex_vwap(snapshot, previous)
    return a if a == b else "NEUTRAL"


def opening_range(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    x = _technical(snapshot); o = snapshot.get("opening_range") or {}
    high = _s(o, "high"); low = _s(o, "low")
    if high and x["spot"] > high and x["volume_ratio"] >= 1.2: return "BULLISH"
    if low and x["spot"] < low and x["volume_ratio"] >= 1.2: return "BEARISH"
    return "NEUTRAL"


STRATEGIES = [
    StrategySpec("VWAP Momentum Breakout", "directional", "VWAP + RSI + volume confirmation", vwap_momentum),
    StrategySpec("VWAP + EMA 9/21", "directional", "VWAP and fast EMA alignment", vwap_ema),
    StrategySpec("EMA Trend", "directional", "EMA 9/21/50 trend alignment", ema_trend),
    StrategySpec("RSI + Bollinger + VWAP", "mean_reversion", "Oversold/overbought mean reversion", rsi_bollinger_vwap),
    StrategySpec("Opening Range Breakout", "directional", "Opening range + volume breakout", opening_range),
    StrategySpec("OI Flow", "flow", "Stored OI pressure bias", oi_flow),
    StrategySpec("OI + VWAP", "confluence", "OI direction agrees with VWAP/EMA", oi_vwap),
    StrategySpec("GEX + VWAP", "gamma", "Negative-gamma directional expansion + VWAP", gex_vwap),
    StrategySpec("Gamma Flip + Price Action", "gamma", "Price location relative to gamma flip", gamma_flip_price_action),
    StrategySpec("IV/RV + Trend", "volatility", "IV/RV relationship with trend", iv_rv_trend),
    StrategySpec("Market Structure + OI", "structure", "Market structure confirmed by OI", market_structure_oi),
    StrategySpec("VWAP + OI + GEX", "confluence", "Three-factor directional confluence", vwap_oi_gex),
]


def all_strategies() -> list[StrategySpec]:
    return list(STRATEGIES)
