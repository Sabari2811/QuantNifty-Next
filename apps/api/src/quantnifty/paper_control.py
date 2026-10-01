from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.learning_store import load_events, record_control

IST = ZoneInfo("Asia/Kolkata")


def current_day() -> str:
    return datetime.now(IST).date().isoformat()


def kill_switch_state(day: str | None = None) -> dict[str, Any]:
    selected_day = str(day or current_day())
    active = False
    activated_at: str | None = None
    reason: str | None = None
    for event in load_events("paper_controls", selected_day):
        action = str(event.get("action") or "").upper()
        if action == "KILL_SWITCH_ON":
            active = True
            activated_at = str(event.get("timestamp") or event.get("stored_at") or "") or activated_at
            reason = str(event.get("reason") or "MANUAL_KILL_SWITCH")
        elif action == "KILL_SWITCH_OFF":
            active = False
            activated_at = None
            reason = str(event.get("reason") or "MANUAL_KILL_SWITCH_RELEASED")
    return {
        "day": selected_day,
        "active": active,
        "activated_at": activated_at,
        "reason": reason,
        "scope": "CURRENT_IST_TRADING_DAY_ONLY",
        "new_entries_blocked": active,
        "open_positions_must_close": active,
    }


def activate_kill_switch(reason: str = "MANUAL_KILL_SWITCH") -> dict[str, Any]:
    day = current_day()
    existing = kill_switch_state(day)
    if existing["active"]:
        return existing
    timestamp = datetime.now(IST).isoformat()
    record_control({
        "timestamp": timestamp,
        "day": day,
        "action": "KILL_SWITCH_ON",
        "enabled": True,
        "reason": reason,
        "scope": "CURRENT_IST_TRADING_DAY_ONLY",
        "new_entries_blocked": True,
        "open_positions_must_close": True,
    })
    return kill_switch_state(day)


def deactivate_kill_switch(reason: str = "MANUAL_KILL_SWITCH_RELEASED") -> dict[str, Any]:
    day = current_day()
    existing = kill_switch_state(day)
    if not existing["active"]:
        return existing
    timestamp = datetime.now(IST).isoformat()
    record_control({
        "timestamp": timestamp,
        "day": day,
        "action": "KILL_SWITCH_OFF",
        "enabled": False,
        "reason": reason,
        "scope": "CURRENT_IST_TRADING_DAY_ONLY",
        "new_entries_blocked": False,
        "open_positions_must_close": False,
    })
    return kill_switch_state(day)
