from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from quantnifty.learning_store import load_events, trading_day

REENTRY_COOLDOWN_MINUTES = 5
MIN_REENTRY_DISPLACEMENT_POINTS = 8.0


def _f(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def _ts(value: Any) -> datetime | None:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _latest_lifecycle(day: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in load_events("outcomes", day):
        outcome = event.get("outcome") if isinstance(event, dict) else None
        if not isinstance(outcome, dict):
            continue
        trade_id = str(outcome.get("trade_id") or "")
        if not trade_id:
            continue
        status = str(outcome.get("status") or outcome.get("lifecycle") or "").upper()
        if status == "OPEN":
            latest[trade_id] = outcome
        elif status == "CLOSED":
            latest.pop(trade_id, None)
    closed: dict[str, dict[str, Any]] = {}
    for event in load_events("outcomes", day):
        outcome = event.get("outcome") if isinstance(event, dict) else None
        if not isinstance(outcome, dict):
            continue
        trade_id = str(outcome.get("trade_id") or "")
        if not trade_id:
            continue
        status = str(outcome.get("status") or outcome.get("lifecycle") or "").upper()
        if status == "CLOSED":
            previous = closed.get(trade_id)
            stamp = str(outcome.get("exit_timestamp") or outcome.get("timestamp") or "")
            previous_stamp = str((previous or {}).get("exit_timestamp") or (previous or {}).get("timestamp") or "")
            if previous is None or stamp >= previous_stamp:
                closed[trade_id] = outcome
    return list(latest.values()), closed


def evaluate_paper_entry(data: dict[str, Any], direction: str, mode: str = "LIVE") -> dict[str, Any]:
    """Return a durable, deterministic TAKE/WAIT/NO-TRADE lifecycle decision.

    This gate is live-paper only. It never reads research/replay data and never
    creates or mutates a trade lifecycle by itself.
    """
    if str(mode or "LIVE").upper() != "LIVE":
        return {"applied": False, "action": "PASS", "allowed": True, "reason": "NON_LIVE_MODE"}

    direction = str(direction or "NEUTRAL").upper()
    if direction not in {"BULLISH", "BEARISH"}:
        return {"applied": True, "action": "NO_TRADE", "allowed": False, "reason": "NO_DIRECTIONAL_SIGNAL"}

    timestamp = _ts(data.get("timestamp"))
    day = trading_day(data.get("timestamp"))
    if timestamp is None or not day:
        return {"applied": True, "action": "NO_TRADE", "allowed": False, "reason": "TIMESTAMP_REQUIRED_FOR_PAPER_ENTRY"}

    active, closed = _latest_lifecycle(day)
    if active:
        newest = max(active, key=lambda row: str(row.get("entry_timestamp") or row.get("timestamp") or ""))
        return {
            "applied": True,
            "action": "HOLD_ACTIVE_TRADE",
            "allowed": False,
            "reason": "ACTIVE_TRADE_LOCK",
            "active_trade_id": newest.get("trade_id"),
            "active_direction": newest.get("direction"),
            "active_entry_timestamp": newest.get("entry_timestamp"),
            "active_trade_count": len(active),
        }

    if not closed:
        return {"applied": True, "action": "TAKE_TRADE", "allowed": True, "reason": "NO_PRIOR_TRADE_TODAY"}

    latest = max(closed.values(), key=lambda row: str(row.get("exit_timestamp") or row.get("timestamp") or ""))
    exit_ts = _ts(latest.get("exit_timestamp") or latest.get("timestamp"))
    if exit_ts is None:
        return {"applied": True, "action": "NO_TRADE", "allowed": False, "reason": "LAST_EXIT_TIMESTAMP_REQUIRED"}

    elapsed_seconds = max(0.0, (timestamp - exit_ts).total_seconds())
    cooldown_seconds = REENTRY_COOLDOWN_MINUTES * 60.0
    if elapsed_seconds < cooldown_seconds:
        return {
            "applied": True,
            "action": "WAIT_CONFIRMATION",
            "allowed": False,
            "reason": "REENTRY_COOLDOWN",
            "last_trade_id": latest.get("trade_id"),
            "last_direction": latest.get("direction"),
            "elapsed_seconds": round(elapsed_seconds, 1),
            "remaining_seconds": round(cooldown_seconds - elapsed_seconds, 1),
            "cooldown_minutes": REENTRY_COOLDOWN_MINUTES,
        }

    last_direction = str(latest.get("direction") or "NEUTRAL").upper()
    if direction != last_direction:
        return {
            "applied": True,
            "action": "TAKE_TRADE",
            "allowed": True,
            "reason": "DIRECTION_CHANGE_AFTER_COOLDOWN",
            "last_trade_id": latest.get("trade_id"),
        }

    exit_spot = _f(latest.get("exit_spot"))
    spot = _f(data.get("spot"))
    directional_displacement = None
    if exit_spot is not None and spot is not None:
        directional_displacement = spot - exit_spot if direction == "BULLISH" else exit_spot - spot

    intelligence = data.get("intelligence") if isinstance(data.get("intelligence"), dict) else {}
    market_state = (intelligence.get("market_state") or {}) if isinstance(intelligence.get("market_state"), dict) else {}
    state = str(market_state.get("state") or "").upper()
    trend_state = state == ("TREND_UP" if direction == "BULLISH" else "TREND_DOWN")
    events = intelligence.get("events") if isinstance(intelligence.get("events"), list) else []
    event_types = {str((event or {}).get("type") or "").upper() for event in events if isinstance(event, dict)}
    structural_event = bool(event_types & {"GAMMA_ACCELERATION", "EXPECTED_MOVE_EXPANSION", "GAMMA_FLIP_CROSS", "MARKET_STATE_CHANGE", "BREAKOUT_CONFIRMED"})
    displacement_ok = directional_displacement is not None and directional_displacement >= MIN_REENTRY_DISPLACEMENT_POINTS
    structural_ok = trend_state and structural_event

    if displacement_ok or structural_ok:
        return {
            "applied": True,
            "action": "TAKE_TRADE",
            "allowed": True,
            "reason": "NEW_STRUCTURAL_EVIDENCE",
            "last_trade_id": latest.get("trade_id"),
            "directional_displacement_points": round(directional_displacement, 2) if directional_displacement is not None else None,
            "structural_confirmation": structural_ok,
        }

    return {
        "applied": True,
        "action": "WAIT_CONFIRMATION",
        "allowed": False,
        "reason": "REENTRY_STRUCTURE_REQUIRED",
        "last_trade_id": latest.get("trade_id"),
        "last_direction": last_direction,
        "directional_displacement_points": round(directional_displacement, 2) if directional_displacement is not None else None,
        "minimum_displacement_points": MIN_REENTRY_DISPLACEMENT_POINTS,
        "trend_state": trend_state,
        "structural_event": structural_event,
    }


__all__ = ["evaluate_paper_entry", "REENTRY_COOLDOWN_MINUTES", "MIN_REENTRY_DISPLACEMENT_POINTS"]
