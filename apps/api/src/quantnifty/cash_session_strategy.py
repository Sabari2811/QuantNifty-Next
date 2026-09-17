from __future__ import annotations

from datetime import time
from typing import Any

CASH_SESSION_START = time(15, 15)
CASH_ENTRY_CUTOFF = time(15, 27)
CASH_FORCE_EXIT = time(15, 29)
MIN_SPOT_MOVE_POINTS = 8.0
MIN_SCORE = 70.0


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(current: float, previous: float) -> float:
    return (current - previous) / abs(previous) * 100.0 if previous else 0.0


def _oi_pressure(snapshot: dict[str, Any]) -> tuple[float, float]:
    bullish = bearish = 0.0
    for row in snapshot.get("option_chain") or []:
        if not isinstance(row, dict):
            continue
        doi = _f(row.get("oi")) - _f(row.get("previous_oi"))
        price_change = _f(row.get("last_price")) - _f(row.get("previous_close"))
        weight = abs(doi) * max(_f(row.get("last_price")), 1.0)
        if doi > 0 and price_change > 0:
            bullish += weight
        elif doi < 0 and price_change > 0:
            bullish += weight * 0.75
        elif doi > 0 and price_change < 0:
            bearish += weight
        elif doi < 0 and price_change < 0:
            bearish += weight * 0.75
    return bullish, bearish


def _option_momentum(snapshot: dict[str, Any]) -> tuple[float, float]:
    """Return aggregate positive/negative near-ATM premium momentum."""
    spot = _f(snapshot.get("spot"))
    bullish = bearish = 0.0
    for row in snapshot.get("option_chain") or []:
        if not isinstance(row, dict):
            continue
        strike = _f(row.get("strike")); side = str(row.get("side") or row.get("option_type") or "").upper()
        if side not in {"CE", "PE"} or strike <= 0 or spot <= 0 or abs(strike - spot) / spot > 0.02:
            continue
        price = _f(row.get("last_price")); previous_close = _f(row.get("previous_close")); change = price - previous_close
        weight = max(_f(row.get("volume")), 1.0)
        if side == "CE":
            bullish += change * weight
        else:
            bearish += change * weight
    return bullish, bearish


def evaluate_cash_strategy(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic late-session NIFTY options strategy using available observations only.

    This is a cash-market-influence window for NIFTY options, not a claim that
    the NIFTY index itself participates in the equity cash closing auction.
    The strategy requires directional movement plus participation/OI evidence.
    """
    previous = previous or {}
    spot = _f(snapshot.get("spot"))
    previous_spot = _f(previous.get("spot"))
    move_points = spot - previous_spot if spot and previous_spot else 0.0
    bullish_premium, bearish_premium = _option_momentum(snapshot)
    if move_points == 0.0:
        premium_bias = "BULLISH" if bullish_premium > bearish_premium else "BEARISH" if bearish_premium > bullish_premium else "NEUTRAL"
        recorded_bias = str(snapshot.get("bias") or "NEUTRAL").upper()
        if premium_bias == "NEUTRAL" and recorded_bias in {"BULLISH", "BEARISH"}:
            direction = recorded_bias
        else:
            direction = premium_bias
    else:
        direction = "BULLISH" if move_points > 0 else "BEARISH"

    volume = sum(_f(row.get("volume")) for row in snapshot.get("option_chain") or [] if isinstance(row, dict))
    previous_volume = sum(_f(row.get("volume")) for row in previous.get("option_chain") or [] if isinstance(row, dict))
    volume_change = _pct(volume, previous_volume) if previous_volume else 0.0
    bullish_oi, bearish_oi = _oi_pressure(snapshot)
    oi_bias = "BULLISH" if bullish_oi > bearish_oi * 1.15 else "BEARISH" if bearish_oi > bullish_oi * 1.15 else "NEUTRAL"
    iv_change = _pct(_f(snapshot.get("atm_iv")), _f(previous.get("atm_iv"))) if _f(previous.get("atm_iv")) else 0.0
    em = _f((snapshot.get("expected_move") or {}).get("move"))
    previous_em = _f((previous.get("expected_move") or {}).get("move"))
    expected_move_change = _pct(em, previous_em) if previous_em else 0.0
    liquidity = _f(snapshot.get("liquidity_score"))
    gex = _f(snapshot.get("gex"))

    alignment = oi_bias == direction and direction in {"BULLISH", "BEARISH"}
    score = 0.0
    score += 25.0 if abs(move_points) >= MIN_SPOT_MOVE_POINTS else 0.0
    score += 20.0 if volume_change >= 15.0 else 0.0
    score += 20.0 if alignment else 0.0
    score += 15.0 if max(iv_change, expected_move_change) >= 2.0 else 0.0
    score += 10.0 if gex < 0 else 0.0
    score += 10.0 if liquidity >= 60.0 else 0.0
    if direction in {"BULLISH", "BEARISH"} and oi_bias not in {"NEUTRAL", direction}:
        score -= 15.0

    valid = direction in {"BULLISH", "BEARISH"} and score >= MIN_SCORE and liquidity >= 50.0
    return {
        "strategy": "cash_session",
        "session": "CASH_INFLUENCE_15:15_15:30",
        "valid": valid,
        "direction": direction if valid else "NEUTRAL",
        "confidence": round(min(99.0, score), 1),
        "score": round(score, 1),
        "spot_move_points": round(move_points, 2),
        "option_premium_momentum": "BULLISH" if bullish_premium > bearish_premium else "BEARISH" if bearish_premium > bullish_premium else "NEUTRAL",
        "volume_change_pct": round(volume_change, 2),
        "oi_bias": oi_bias,
        "oi_bullish_pressure": round(bullish_oi, 2),
        "oi_bearish_pressure": round(bearish_oi, 2),
        "oi_alignment": alignment,
        "iv_change_pct": round(iv_change, 2),
        "expected_move_change_pct": round(expected_move_change, 2),
        "gamma_regime": "NEGATIVE" if gex < 0 else "POSITIVE" if gex > 0 else "NEUTRAL",
        "liquidity": round(liquidity, 1),
        "entry_cutoff": CASH_ENTRY_CUTOFF.strftime("%H:%M"),
        "force_exit": CASH_FORCE_EXIT.strftime("%H:%M"),
        "reason": "late-session momentum + participation + OI confirmation" if valid else "cash-session confirmation threshold not met",
        "research_only": False,
        "read_only_execution": True,
    }


__all__ = ["CASH_SESSION_START", "CASH_ENTRY_CUTOFF", "CASH_FORCE_EXIT", "evaluate_cash_strategy"]
