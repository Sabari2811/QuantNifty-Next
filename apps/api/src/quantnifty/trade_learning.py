from __future__ import annotations

from typing import Any


def _f(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _directional_conflict(outcome: dict[str, Any]) -> bool:
    direction = str(outcome.get("direction") or "").upper()
    if direction not in {"BULLISH", "BEARISH"}:
        return False
    decision = outcome.get("entry_decision") if isinstance(outcome.get("entry_decision"), dict) else {}
    signal = decision.get("signal") if isinstance(decision.get("signal"), dict) else {}
    market = decision.get("market") if isinstance(decision.get("market"), dict) else {}
    bias = str(market.get("bias") or signal.get("market_bias") or "").upper()
    oi_flow = str(signal.get("oi_flow") or signal.get("oi_flow_bias") or "").upper()
    gamma = str(signal.get("gamma") or signal.get("gamma_regime") or "").upper()
    conflicts = 0
    if bias in {"BULLISH", "BEARISH"} and bias != direction:
        conflicts += 1
    if oi_flow in {"BULLISH", "BEARISH"} and oi_flow != direction:
        conflicts += 1
    if gamma == "POSITIVE_GAMMA":
        conflicts += 1
    return conflicts >= 2


def analyze_trade_lesson(outcome: dict[str, Any]) -> dict[str, Any]:
    direction = str(outcome.get("direction") or "").upper()
    entry_spot = _f(outcome.get("entry_spot"))
    exit_spot = _f(outcome.get("exit_spot"))
    entry_price = _f(outcome.get("entry_price"))
    exit_price = _f(outcome.get("exit_price"))
    entry_delta = abs(_f(outcome.get("entry_delta")))
    risk = outcome.get("entry_risk") if isinstance(outcome.get("entry_risk"), dict) else {}
    stop_spot = _f(risk.get("stop_spot"))
    target_spot = _f(risk.get("target_spot"))
    adverse_spot = 0.0
    if entry_spot > 0 and exit_spot > 0:
        adverse_spot = (exit_spot - entry_spot) if direction == "BEARISH" else (entry_spot - exit_spot)
    premium_change = exit_price - entry_price if entry_price > 0 and exit_price > 0 else 0.0
    premium_change_pct = premium_change / entry_price * 100.0 if entry_price > 0 else 0.0
    spot_stop_hit = stop_spot > 0 and ((exit_spot >= stop_spot) if direction == "BEARISH" else (exit_spot <= stop_spot))
    spot_target_hit = target_spot > 0 and ((exit_spot <= target_spot) if direction == "BEARISH" else (exit_spot >= target_spot))
    reason = str(outcome.get("exit_reason") or outcome.get("exit_reasons", {}).get("exit_reason") or "").upper()
    exit_delta_risk = outcome.get("delta_risk_at_exit") if isinstance(outcome.get("delta_risk_at_exit"), dict) else {}
    premium_stop_at_exit = _f(exit_delta_risk.get("premium_stop"))
    conflict = _directional_conflict(outcome)
    patterns: list[str] = []
    if conflict:
        patterns.append("DIRECTIONAL_CONTEXT_CONFLICT")
    if reason == "DELTA_PREMIUM_STOP" and not spot_stop_hit:
        patterns.append("PREMIUM_STOP_BEFORE_SPOT_INVALIDATION")
    if adverse_spot > 0:
        patterns.append("NO_FOLLOW_THROUGH")
    if direction in {"BULLISH", "BEARISH"} and entry_delta > 0:
        patterns.append("DIRECTIONAL_OPTION_DELTA_EXPOSURE")
    lessons = []
    if "DIRECTIONAL_CONTEXT_CONFLICT" in patterns:
        lessons.append("Require directional confirmation from at least two independent context signals before entering during gamma-transition/positive-gamma conditions.")
    if "PREMIUM_STOP_BEFORE_SPOT_INVALIDATION" in patterns:
        lessons.append("Keep the premium stop as a protection layer, but do not widen it from a single trade; compare at least three similar trades before changing the risk model.")
    if reason == "DELTA_PREMIUM_STOP" and premium_stop_at_exit > 0:
        lessons.append("Audit the stop using the live delta at exit: the runtime risk model recalculates the premium threshold from live delta, so the displayed entry-time premium SL can differ from the actual trigger level.")
    if "NO_FOLLOW_THROUGH" in patterns:
        lessons.append("A bearish thesis needs downside follow-through after entry; if spot remains above entry and the option premium deteriorates, invalidate the thesis rather than waiting for the spot stop.")
    return {
        "schema": "adaptive-trade-lesson-v1",
        "trade_id": outcome.get("trade_id"),
        "day": outcome.get("day"),
        "strategy": outcome.get("strategy"),
        "regime": (outcome.get("entry_reasons") or {}).get("adaptive_regime") if isinstance(outcome.get("entry_reasons"), dict) else None,
        "direction": direction,
        "entry_spot": entry_spot,
        "exit_spot": exit_spot,
        "adverse_spot_points": round(adverse_spot, 2),
        "entry_premium": entry_price,
        "exit_premium": exit_price,
        "premium_change": round(premium_change, 2),
        "premium_change_pct": round(premium_change_pct, 2),
        "entry_delta": round(entry_delta, 4) if entry_delta else None,
        "spot_stop_hit": spot_stop_hit,
        "spot_target_hit": spot_target_hit,
        "premium_stop_at_exit": premium_stop_at_exit if premium_stop_at_exit > 0 else None,
        "exit_reason": reason,
        "patterns": patterns,
        "lessons": lessons,
        "sample_policy": "ONE_TRADE_IS_OBSERVATION_ONLY; NO_AUTOMATIC_PARAMETER_PROMOTION",
    }


def summarize_trade_lessons(lessons: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for lesson in lessons:
        for pattern in lesson.get("patterns") or []:
            counts[pattern] = counts.get(pattern, 0) + 1
    return {
        "observations": len(lessons),
        "pattern_counts": counts,
        "promotion_rule": "Require >=3 comparable observations before changing a risk/entry parameter; strategy promotion remains subject to existing research validation.",
        "lessons": lessons,
    }
