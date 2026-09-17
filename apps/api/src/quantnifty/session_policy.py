from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.cash_session_strategy import (
    CAS_MATCHING_END,
    CAS_START,
    CAS_STRATEGY_ENTRY_CUTOFF,
    CAS_STRATEGY_FORCE_EXIT,
    DERIVATIVES_CLOSE,
    evaluate_cash_strategy,
)

IST = ZoneInfo("Asia/Kolkata")
NORMAL_START = time(9, 20)
NORMAL_END = CAS_START


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
    if t < CAS_MATCHING_END:
        return {
            "phase": "CAS_REENTRY",
            "decision_enabled": True,
            "reason": "nse_closing_auction_influence_window",
            "local_time": local.isoformat(),
            "cas": {"start": CAS_START.strftime("%H:%M"), "matching_end": CAS_MATCHING_END.strftime("%H:%M"), "nifty_options_participate_in_cas": False},
        }
    if t < DERIVATIVES_CLOSE:
        return {
            "phase": "DERIVATIVES_CLOSE_ONLY",
            "decision_enabled": True,
            "reason": "cas_matching_complete_nifty_derivatives_still_open",
            "local_time": local.isoformat(),
            "new_entries": False,
            "force_exit": CAS_STRATEGY_FORCE_EXIT.strftime("%H:%M"),
            "derivatives_close": DERIVATIVES_CLOSE.strftime("%H:%M"),
        }
    return {"phase": "CLOSED", "decision_enabled": False, "reason": "after_15:40", "local_time": local.isoformat()}


def cas_signal(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce a CAS-aware NIFTY-options signal from current observations."""
    strategy = evaluate_cash_strategy(snapshot, previous)
    raw = _cas_payload(snapshot)
    raw_direction = str(raw.get("direction") or raw.get("bias") or "NEUTRAL").upper()
    raw_source = str(raw.get("source") or raw.get("method") or "PROVIDER_CAS") if raw else None
    return {
        "available": True,
        "valid": bool(strategy.get("valid")),
        "direction": strategy.get("direction", "NEUTRAL"),
        "confidence": strategy.get("confidence", 0.0),
        "source": "DETERMINISTIC_CAS_AWARE" if strategy.get("valid") else raw_source,
        "strategy": strategy,
        "provider_cas_evidence": {"available": bool(raw), "direction": raw_direction if raw_direction in {"BULLISH", "BEARISH"} else "NEUTRAL", "source": raw_source},
    }


def session_decision_policy(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    phase = session_phase(snapshot)
    cas = cas_signal(snapshot, previous) if phase["phase"] == "CAS_REENTRY" else {"available": False, "valid": False, "direction": "NEUTRAL", "confidence": 0.0, "source": None}
    if phase["phase"] == "CAS_REENTRY":
        timestamp = _timestamp(snapshot.get("timestamp"))
        allow_entry = bool(cas["valid"]) and timestamp is not None and timestamp.astimezone(IST).time() < CAS_STRATEGY_ENTRY_CUTOFF
        return {
            **phase,
            "cas": cas,
            "cas_strategy": cas.get("strategy"),
            "cash_strategy": cas.get("strategy"),
            "allow_normal_adaptive": False,
            "allow_new_trade": allow_entry,
            "selected_strategy": "cas_reentry" if allow_entry else "standby",
            "preferred_direction": cas["direction"] if allow_entry else "NEUTRAL",
            "reason": "deterministic CAS-aware strategy confirmed" if allow_entry else "waiting for CAS-aware confirmation or entry cutoff",
        }
    if phase["phase"] == "NORMAL_ADAPTIVE":
        return {**phase, "cas": cas, "cas_strategy": None, "cash_strategy": None, "allow_normal_adaptive": True, "allow_new_trade": True, "selected_strategy": None, "preferred_direction": "NEUTRAL"}
    return {**phase, "cas": cas, "cas_strategy": None, "cash_strategy": None, "allow_normal_adaptive": False, "allow_new_trade": False, "selected_strategy": "standby", "preferred_direction": "NEUTRAL"}
