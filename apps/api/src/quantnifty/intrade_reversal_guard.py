from __future__ import annotations

from typing import Any


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def opposite_direction(direction: str) -> str:
    value = str(direction or "").upper()
    return "BEARISH" if value == "BULLISH" else "BULLISH" if value == "BEARISH" else "NEUTRAL"


def evaluate_intrade_reversal(
    entry_direction: str,
    snapshot: dict[str, Any],
    decision: dict[str, Any],
    previous_snapshot: dict[str, Any] | None = None,
    opposite_confirmations: int = 0,
) -> dict[str, Any]:
    """Detect a genuine thesis reversal while a paper position is open.

    This is a hysteresis guard, not a one-tick signal flipper. A reversal normally
    needs an opposite directional signal plus at least two independent context
    confirmations. A large adverse price shock with opposite context can escalate
    immediately. The result is observational and contains no order/execution logic.
    """
    direction = str(entry_direction or "NEUTRAL").upper()
    expected = opposite_direction(direction)
    signal = decision.get("signal") if isinstance(decision, dict) else {}
    signal = signal if isinstance(signal, dict) else {}
    current = str(signal.get("direction") or "NEUTRAL").upper()
    confidence = _f(signal.get("confidence"))
    alignment = signal.get("context_alignment") if isinstance(signal.get("context_alignment"), dict) else {}
    aligned = int(alignment.get("aligned") or 0)
    conflicting = int(alignment.get("conflicting") or 0)
    transition = bool(alignment.get("transition_context"))
    market_state = str(
        ((decision.get("market") or {}).get("state"))
        or ((snapshot.get("intelligence") or {}).get("market_state") or {}).get("state")
        or ""
    ).upper()
    spot = _f(snapshot.get("spot"))
    previous_spot = _f((previous_snapshot or {}).get("spot"))
    move = spot - previous_spot if previous_spot else 0.0
    adverse_move = move > 0 if direction == "BEARISH" else move < 0 if direction == "BULLISH" else False
    entry_spot = _f((decision.get("paper_trade") or {}).get("entry_spot"))
    if not entry_spot:
        entry_spot = _f(snapshot.get("_active_trade_entry_spot"))
    cumulative_adverse_pct = 0.0
    if entry_spot > 0:
        cumulative_adverse_pct = (
            (spot - entry_spot) / entry_spot * 100.0
            if direction == "BEARISH"
            else (entry_spot - spot) / entry_spot * 100.0
        )
    volume = sum(_f(r.get("volume")) for r in snapshot.get("option_chain") or [] if isinstance(r, dict))
    previous_volume = sum(_f(r.get("volume")) for r in (previous_snapshot or {}).get("option_chain") or [] if isinstance(r, dict))
    volume_impulse_pct = ((volume - previous_volume) / previous_volume * 100.0) if previous_volume > 0 else 0.0
    gamma = str((signal.get("gamma") or {}).get("regime") or "").upper()
    gamma_flip = _f(snapshot.get("gamma_flip"))
    old_flip = _f((previous_snapshot or {}).get("gamma_flip"))
    crossed_gamma_flip = bool(previous_snapshot and gamma_flip and old_flip and
                               ((previous_spot - old_flip) * (spot - gamma_flip) < 0))
    shock_threshold = max(18.0, spot * 0.0012)
    price_shock = abs(move) >= shock_threshold and adverse_move
    opposite_context = current == expected and confidence >= 60 and aligned >= (2 if transition else 2)
    severe_reversal = opposite_context and (price_shock or crossed_gamma_flip or cumulative_adverse_pct >= 0.35)
    normal_reversal = opposite_context and opposite_confirmations >= 2
    warning = current == expected and confidence >= 55 and (aligned >= 1 or conflicting >= 2)
    action = "EXIT_REVERSAL" if severe_reversal or normal_reversal else "WARN_REVERSAL" if warning else "HOLD"
    return {
        "active_direction": direction,
        "opposite_direction": expected,
        "current_direction": current,
        "confidence": round(confidence, 2),
        "opposite_confirmations": opposite_confirmations,
        "context_aligned": aligned,
        "context_conflicting": conflicting,
        "transition_context": transition,
        "market_state": market_state,
        "spot_move_points": round(move, 2),
        "cumulative_adverse_pct": round(cumulative_adverse_pct, 4),
        "volume_impulse_pct": round(volume_impulse_pct, 2),
        "price_shock": price_shock,
        "crossed_gamma_flip": crossed_gamma_flip,
        "gamma_regime": gamma,
        "severe_reversal": severe_reversal,
        "normal_reversal": normal_reversal,
        "warning": warning,
        "action": action,
        "reason": (
            "opposite directional signal confirmed by independent context"
            if normal_reversal else
            "opposite signal plus adverse price shock/gamma-flip reversal"
            if severe_reversal else
            "opposite signal detected; waiting for confirmation"
            if warning else
            "active thesis remains valid"
        ),
    }
