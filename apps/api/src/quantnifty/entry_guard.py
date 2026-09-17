from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


MIN_DISPLACEMENT_POINTS = 8.0
SUPPORT_PROXIMITY_POINTS = 35.0
BREAK_CONFIRMATION_POINTS = 5.0
FAILED_SIGNAL_COOLDOWN_MINUTES = 3


def _f(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def _timestamp(value: Any) -> datetime | None:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed
        return parsed
    except (TypeError, ValueError):
        return None


def _directional_displacement(data: dict[str, Any], direction: str) -> float | None:
    intelligence = data.get("intelligence") if isinstance(data.get("intelligence"), dict) else {}
    attribution = intelligence.get("move_attribution") if isinstance(intelligence.get("move_attribution"), dict) else {}
    points = _f(attribution.get("points"))
    if points is None:
        return None
    return points if direction == "BULLISH" else -points if direction == "BEARISH" else 0.0


def _structural_confirmation(data: dict[str, Any], direction: str) -> tuple[bool, list[str]]:
    intelligence = data.get("intelligence") if isinstance(data.get("intelligence"), dict) else {}
    state = str((intelligence.get("market_state") or {}).get("state") or "").upper()
    attribution = intelligence.get("move_attribution") if isinstance(intelligence.get("move_attribution"), dict) else {}
    directional_move = _directional_displacement(data, direction)
    events = intelligence.get("events") if isinstance(intelligence.get("events"), list) else []
    event_types = {str((event or {}).get("type") or "").upper() for event in events if isinstance(event, dict)}
    meaningful_event = bool(event_types & {"GAMMA_ACCELERATION", "EXPECTED_MOVE_EXPANSION", "GAMMA_FLIP_CROSS", "MARKET_STATE_CHANGE"})
    trend_state = state == ("TREND_UP" if direction == "BULLISH" else "TREND_DOWN")
    quality_high = str(attribution.get("quality") or "").upper() == "HIGH"
    reasons: list[str] = []
    if trend_state:
        reasons.append("TREND_STATE_ALIGNMENT")
    if quality_high:
        reasons.append("HIGH_MOVE_ATTRIBUTION_QUALITY")
    if meaningful_event:
        reasons.append("STRUCTURAL_EVENT")
    if directional_move is not None and directional_move >= 3.0:
        reasons.append("DIRECTIONAL_DISPLACEMENT_3PT")
    return bool(trend_state and (meaningful_event or quality_high or (directional_move is not None and directional_move >= 3.0))), reasons


def _support_gate(data: dict[str, Any], direction: str) -> tuple[bool, dict[str, Any]]:
    spot = _f(data.get("spot"))
    level_key = "support" if direction == "BEARISH" else "resistance"
    level = _f(data.get(level_key))
    if spot is None or level is None:
        return True, {"status": "UNAVAILABLE_PASS", "level": level, "spot": spot}
    distance = spot - level if direction == "BEARISH" else level - spot
    near = 0 <= distance <= SUPPORT_PROXIMITY_POINTS
    if not near:
        return True, {"status": "NOT_NEAR_LEVEL", "level": level, "spot": spot, "distance_points": round(distance, 2)}
    confirmed_break = distance <= -BREAK_CONFIRMATION_POINTS
    return confirmed_break, {
        "status": "CONFIRMED_BREAK" if confirmed_break else "NEAR_LEVEL_WITHOUT_BREAK",
        "level": level,
        "spot": spot,
        "distance_points": round(distance, 2),
        "proximity_points": SUPPORT_PROXIMITY_POINTS,
        "confirmation_points": BREAK_CONFIRMATION_POINTS,
    }


def _latest_failed_signal(direction: str, data: dict[str, Any]) -> dict[str, Any] | None:
    try:
        from quantnifty.learning_store import load_events
        from quantnifty.paper_trade_tracker import trading_day

        day = trading_day(data.get("timestamp"))
        events = load_events("outcomes", day)
    except Exception:
        return None
    latest: dict[str, Any] | None = None
    for event in events:
        outcome = event.get("outcome") if isinstance(event, dict) else None
        if not isinstance(outcome, dict) or str(outcome.get("status") or "").upper() != "CLOSED":
            continue
        if str(outcome.get("direction") or "").upper() != direction:
            continue
        pnl = _f(outcome.get("realized_pnl", outcome.get("gross_pnl_proxy")))
        if pnl is None or pnl >= 0:
            continue
        if latest is None or str(outcome.get("exit_timestamp") or "") > str(latest.get("exit_timestamp") or ""):
            latest = outcome
    return latest


def _cooldown_gate(data: dict[str, Any], direction: str) -> tuple[bool, dict[str, Any]]:
    failed = _latest_failed_signal(direction, data)
    if failed is None:
        return True, {"status": "NO_RECENT_FAILED_SIGNAL"}
    now = _timestamp(data.get("timestamp")); exit_time = _timestamp(failed.get("exit_timestamp"))
    if now is None or exit_time is None:
        return True, {"status": "TIMESTAMP_UNAVAILABLE_PASS", "trade_id": failed.get("trade_id")}
    elapsed = (now - exit_time).total_seconds()
    if elapsed < 0:
        return True, {"status": "NON_MONOTONIC_TIMESTAMP_PASS", "trade_id": failed.get("trade_id")}
    remaining = FAILED_SIGNAL_COOLDOWN_MINUTES * 60 - elapsed
    if remaining > 0:
        return False, {
            "status": "FAILED_SIGNAL_COOLDOWN",
            "trade_id": failed.get("trade_id"),
            "exit_timestamp": failed.get("exit_timestamp"),
            "elapsed_seconds": round(elapsed, 1),
            "remaining_seconds": round(remaining, 1),
            "cooldown_minutes": FAILED_SIGNAL_COOLDOWN_MINUTES,
        }
    return True, {"status": "COOLDOWN_EXPIRED", "trade_id": failed.get("trade_id"), "elapsed_seconds": round(elapsed, 1)}


def evaluate_entry_guards(data: dict[str, Any], result: dict[str, Any], mode: str = "LIVE") -> dict[str, Any]:
    """Apply live-only entry safeguards to an already-approved deterministic decision.

    Missing support/displacement evidence is reported as unavailable and does not invent a block.
    Historical/replay decisions are untouched so research remains counterfactual and independent.
    """
    risk = result.get("risk") if isinstance(result, dict) else None
    signal = result.get("signal") if isinstance(result, dict) else None
    if not isinstance(risk, dict) or not isinstance(signal, dict):
        return {"applied": False, "reason": "INVALID_DECISION_SHAPE"}
    if str(mode or "LIVE").upper() != "LIVE":
        return {"applied": False, "reason": "NON_LIVE_MODE"}
    if not bool(risk.get("approved")):
        return {"applied": False, "reason": "BASE_RISK_ALREADY_BLOCKED"}
    direction = str(signal.get("direction") or "NEUTRAL").upper()
    if direction not in {"BULLISH", "BEARISH"}:
        return {"applied": False, "reason": "NO_DIRECTIONAL_ENTRY"}

    displacement = _directional_displacement(data, direction)
    structural_ok, structural_reasons = _structural_confirmation(data, direction)
    if displacement is None:
        displacement_ok = True
        displacement_status = "UNAVAILABLE_PASS"
    else:
        displacement_ok = displacement >= MIN_DISPLACEMENT_POINTS or structural_ok
        displacement_status = "CONFIRMED" if displacement_ok else "INSUFFICIENT_DISPLACEMENT"

    support_ok, support_detail = _support_gate(data, direction)
    cooldown_ok, cooldown_detail = _cooldown_gate(data, direction)
    gates = {
        "minimum_displacement": displacement_ok,
        "support_breakdown_confirmation": support_ok,
        "failed_signal_cooldown": cooldown_ok,
    }
    reasons = [name for name, passed in gates.items() if not passed]
    if reasons:
        existing_gates = dict(risk.get("gates") or {})
        existing_gates.update(gates)
        existing_reasons = [str(item) for item in (risk.get("reasons") or [])]
        risk["gates"] = existing_gates
        risk["reasons"] = list(dict.fromkeys([*existing_reasons, *reasons]))
        risk["approved"] = False
        plan = result.get("execution_plan")
        if isinstance(plan, dict):
            plan["status"] = "BLOCKED"
            plan["entry"] = None
            plan["stop_points"] = None
            plan["target_points"] = None
            plan["risk_reward"] = None
    else:
        existing_gates = dict(risk.get("gates") or {})
        existing_gates.update(gates)
        risk["gates"] = existing_gates
        risk["reasons"] = [str(item) for item in (risk.get("reasons") or []) if str(item) not in gates]

    return {
        "applied": True,
        "version": "entry-guard-v1",
        "direction": direction,
        "blocked": bool(reasons),
        "reasons": reasons,
        "gates": gates,
        "displacement": {
            "directional_points": None if displacement is None else round(displacement, 2),
            "minimum_points": MIN_DISPLACEMENT_POINTS,
            "status": displacement_status,
            "structural_confirmation": structural_ok,
            "structural_reasons": structural_reasons,
        },
        "support": support_detail,
        "cooldown": cooldown_detail,
        "thresholds": {
            "support_proximity_points": SUPPORT_PROXIMITY_POINTS,
            "break_confirmation_points": BREAK_CONFIRMATION_POINTS,
            "failed_signal_cooldown_minutes": FAILED_SIGNAL_COOLDOWN_MINUTES,
        },
        "read_only": True,
        "broker_execution": "DISABLED",
    }


__all__ = [
    "evaluate_entry_guards",
    "MIN_DISPLACEMENT_POINTS",
    "SUPPORT_PROXIMITY_POINTS",
    "BREAK_CONFIRMATION_POINTS",
    "FAILED_SIGNAL_COOLDOWN_MINUTES",
]
