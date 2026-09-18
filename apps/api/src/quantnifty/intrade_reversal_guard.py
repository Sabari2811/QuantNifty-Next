from __future__ import annotations

from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _opposite(direction: str) -> str:
    return "BEARISH" if direction == "BULLISH" else "BULLISH" if direction == "BEARISH" else "NEUTRAL"


def evaluate_intrade_reversal(
    entry_direction: str,
    snapshot: dict[str, Any],
    decision: dict[str, Any],
    previous_snapshot: dict[str, Any] | None = None,
    opposite_confirmations: int = 0,
) -> dict[str, Any]:
    entry_direction = str(entry_direction or "").upper()
    opposite = _opposite(entry_direction)
    signal = decision.get("signal") if isinstance(decision.get("signal"), dict) else {}
    current_direction = str(signal.get("direction") or "NEUTRAL").upper()
    confidence = _f(signal.get("confidence"))
    alignment = signal.get("context_alignment") if isinstance(signal.get("context_alignment"), dict) else {}
    aligned = int(_f(alignment.get("aligned")))
    market = decision.get("market") if isinstance(decision.get("market"), dict) else {}
    intelligence = snapshot.get("intelligence") if isinstance(snapshot.get("intelligence"), dict) else {}
    market_state = str(
        market.get("state")
        or ((intelligence.get("market_state") or {}).get("state") if isinstance(intelligence.get("market_state"), dict) else "")
        or ""
    ).upper()

    spot = _f(snapshot.get("spot"))
    prev_spot = _f((previous_snapshot or {}).get("spot"))
    spot_move = spot - prev_spot if prev_spot > 0 else 0.0
    shock_threshold = max(18.0, spot * 0.0012) if spot > 0 else 18.0
    adverse_move = (
        spot_move >= shock_threshold if entry_direction == "BEARISH"
        else spot_move <= -shock_threshold if entry_direction == "BULLISH"
        else False
    )

    entry_spot = _f(snapshot.get("_active_trade_entry_spot"))
    cumulative_adverse_pct = 0.0
    if entry_spot > 0:
        signed_move = (spot - entry_spot) / entry_spot * 100.0
        cumulative_adverse_pct = signed_move if entry_direction == "BEARISH" else -signed_move

    gamma = signal.get("gamma") if isinstance(signal.get("gamma"), dict) else {}
    current_flip = gamma.get("gamma_flip")
    previous_gamma = {}
    if isinstance(previous_snapshot, dict):
        previous_intel = previous_snapshot.get("intelligence")
        if isinstance(previous_intel, dict):
            previous_gamma = previous_intel.get("gamma") if isinstance(previous_intel.get("gamma"), dict) else {}
    previous_flip = previous_gamma.get("gamma_flip", previous_snapshot.get("gamma_flip") if isinstance(previous_snapshot, dict) else None)
    crossed_gamma_flip = False
    if current_flip is not None and previous_flip is not None and prev_spot > 0 and spot > 0:
        crossed_gamma_flip = (prev_spot - _f(previous_flip)) * (spot - _f(current_flip)) < 0

    opposite_context = current_direction == opposite and confidence >= 60.0 and aligned >= 2
    severe_reversal = opposite_context and (adverse_move or crossed_gamma_flip or cumulative_adverse_pct >= 0.35)
    normal_reversal = opposite_context and opposite_confirmations >= 2
    warning = current_direction == opposite and confidence >= 55.0 and (aligned >= 1 or market_state in {"GAMMA_TRANSITION", "POSITIVE_GAMMA_RANGE"})

    if severe_reversal:
        action = "EXIT_REVERSAL"
        reason = "opposite signal plus adverse price shock/gamma-flip reversal"
    elif normal_reversal:
        action = "EXIT_REVERSAL"
        reason = "opposite directional signal confirmed by independent context"
    elif warning:
        action = "WARN_REVERSAL"
        reason = "opposite signal detected; waiting for confirmation"
    else:
        action = "HOLD"
        reason = "active thesis remains valid"

    return {
        "action": action,
        "reason": reason,
        "entry_direction": entry_direction,
        "current_direction": current_direction,
        "opposite_direction": opposite,
        "confidence": round(confidence, 2),
        "opposite_confirmations": int(opposite_confirmations),
        "aligned_context": aligned,
        "market_state": market_state,
        "spot_move_points": round(spot_move, 2),
        "price_shock": bool(adverse_move),
        "shock_threshold_points": round(shock_threshold, 2),
        "cumulative_adverse_pct": round(cumulative_adverse_pct, 4),
        "gamma_flip_crossed": bool(crossed_gamma_flip),
        "normal_reversal": bool(normal_reversal),
        "severe_reversal": bool(severe_reversal),
        "warning": bool(warning),
        "guard": "INTRA_TRADE_REGIME_REVERSAL_V1",
    }
