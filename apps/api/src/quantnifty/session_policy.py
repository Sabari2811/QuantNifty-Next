from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NORMAL_START = time(9, 20)
NORMAL_END = time(15, 15)
CAS_START = time(15, 15)
MARKET_CLOSE = time(15, 30)


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cas_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    for key in ("cas", "CAS", "cas_signal", "cas_data"):
        value = snapshot.get(key)
        if isinstance(value, dict):
            return value
    return {}


def session_phase(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Resolve the intraday decision window from the snapshot timestamp only."""
    dt = _timestamp(snapshot.get("timestamp"))
    if dt is None:
        return {"phase": "UNKNOWN", "decision_enabled": False, "reason": "missing_or_invalid_timestamp"}
    local = dt.astimezone(IST)
    if local.weekday() >= 5:
        return {"phase": "CLOSED", "decision_enabled": False, "reason": "weekend", "local_time": local.isoformat()}
    t = local.time()
    if t < NORMAL_START:
        return {"phase": "PRE_OPEN", "decision_enabled": False, "reason": "before_09:20", "local_time": local.isoformat()}
    if t < NORMAL_END:
        return {"phase": "NORMAL_ADAPTIVE", "decision_enabled": True, "reason": "adaptive_intraday_window", "local_time": local.isoformat()}
    if t < MARKET_CLOSE:
        return {"phase": "CAS_REENTRY", "decision_enabled": True, "reason": "cas_reentry_window", "local_time": local.isoformat()}
    return {"phase": "CLOSED", "decision_enabled": False, "reason": "after_15:30", "local_time": local.isoformat()}


def cas_signal(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Read an already-produced CAS signal; never synthesize CAS from future data."""
    raw = _cas_payload(snapshot)
    direction = str(raw.get("direction") or raw.get("bias") or "NEUTRAL").upper()
    confidence = raw.get("confidence")
    try:
        confidence_value = float(confidence or 0)
    except (TypeError, ValueError):
        confidence_value = 0.0
    valid = direction in {"BULLISH", "BEARISH"} and confidence_value >= 60
    return {
        "available": bool(raw),
        "valid": valid,
        "direction": direction if direction in {"BULLISH", "BEARISH"} else "NEUTRAL",
        "confidence": round(confidence_value, 1),
        "source": str(raw.get("source") or raw.get("method") or "CAS") if raw else None,
    }


def session_decision_policy(snapshot: dict[str, Any]) -> dict[str, Any]:
    phase = session_phase(snapshot)
    cas = cas_signal(snapshot)
    if phase["phase"] == "CAS_REENTRY":
        return {**phase, "cas": cas, "allow_normal_adaptive": False, "allow_new_trade": cas["valid"], "selected_strategy": "cas_reentry" if cas["valid"] else "standby", "preferred_direction": cas["direction"] if cas["valid"] else "NEUTRAL", "reason": "CAS confirmed re-entry" if cas["valid"] else "waiting for valid CAS signal"}
    if phase["phase"] == "NORMAL_ADAPTIVE":
        return {**phase, "cas": cas, "allow_normal_adaptive": True, "allow_new_trade": True, "selected_strategy": None, "preferred_direction": "NEUTRAL"}
    return {**phase, "cas": cas, "allow_normal_adaptive": False, "allow_new_trade": False, "selected_strategy": "standby", "preferred_direction": "NEUTRAL"}
