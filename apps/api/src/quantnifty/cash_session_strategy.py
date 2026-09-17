from __future__ import annotations

from datetime import time
from typing import Any

# CAS is a cash-segment auction. QuantNifty uses it only as an observable
# influence window for NIFTY derivatives and never claims NIFTY options are
# CAS instruments.
CAS_START = time(15, 15)
CAS_ORDER_ENTRY_START = time(15, 20)
CAS_ORDER_ENTRY_END = time(15, 30)
CAS_MATCHING_END = time(15, 35)
# Project strategy window: entries are permitted through 15:27 inclusive.
CAS_STRATEGY_ENTRY_END = time(15, 27)
CAS_STRATEGY_ENTRY_CUTOFF = time(15, 28)  # exclusive boundary for callers
CAS_STRATEGY_FORCE_EXIT = time(15, 29)
DERIVATIVES_CLOSE = time(15, 30)
MIN_SPOT_MOVE_POINTS = 8.0
MIN_SCORE = 70.0

# Backward-compatible aliases used by existing callers/tests.
CASH_SESSION_START = CAS_START
CASH_ENTRY_CUTOFF = CAS_STRATEGY_ENTRY_CUTOFF
CASH_FORCE_EXIT = CAS_STRATEGY_FORCE_EXIT


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
    """Deterministic late-session NIFTY-options strategy.

    The strategy is read-only and uses only observations available at the
    supplied timestamp. It does not consume a future auction result.
    """
    previous = previous or {}
    spot = _f(snapshot.get("spot"))
    previous_spot = _f(previous.get("spot"))
    move_points = spot - previous_spot if spot and previous_spot else 0.0
    bullish_premium, bearish_premium = _option_momentum(snapshot)
    if move_points == 0.0:
        premium_bias = "BULLISH" if bullish_premium > bearish_premium else "BEARISH" if bearish_premium > bullish_premium else "NEUTRAL"
        recorded_bias = str(snapshot.get("bias") or "NEUTRAL").upper()
        direction = recorded_bias if premium_bias == "NEUTRAL" and recorded_bias in {"BULLISH", "BEARISH"} else premium_bias
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
        "strategy": "cas_reentry",
        "session": "CASH_INFLUENCE_15:15_15:27",
        "cas": {
            "applies_to": "ELIGIBLE_CASH_SEGMENT_STOCKS",
            "nifty_options_participate_in_cas": False,
            "reference_vwap_window": "15:00-15:15 IST",
            "order_entry_window": "15:20-15:30 IST",
            "matching_window": "15:30-15:35 IST",
            "quantnifty_strategy_window": "15:15-15:27 IST",
        },
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
        "entry_cutoff": CAS_STRATEGY_ENTRY_END.strftime("%H:%M"),
        "force_exit": CAS_STRATEGY_FORCE_EXIT.strftime("%H:%M"),
        "derivatives_close": DERIVATIVES_CLOSE.strftime("%H:%M"),
        "reason": "cash-session momentum + participation + OI confirmation" if valid else "cash-session confirmation threshold not met",
        "research_only": False,
        "read_only_execution": True,
    }


__all__ = [
    "CAS_START", "CAS_ORDER_ENTRY_START", "CAS_ORDER_ENTRY_END", "CAS_MATCHING_END",
    "CAS_STRATEGY_ENTRY_END", "CAS_STRATEGY_ENTRY_CUTOFF", "CAS_STRATEGY_FORCE_EXIT",
    "DERIVATIVES_CLOSE", "CASH_SESSION_START", "CASH_ENTRY_CUTOFF", "CASH_FORCE_EXIT",
    "evaluate_cash_strategy",
]
