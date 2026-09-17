from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NORMAL_ENTRY_CUTOFF_HOUR = 15
NORMAL_ENTRY_CUTOFF_MINUTE = 14
CAS_SESSION_START_HOUR = 15
CAS_SESSION_START_MINUTE = 15
CAS_FORCE_EXIT_HOUR = 15
CAS_FORCE_EXIT_MINUTE = 39
DERIVATIVES_CLOSE_HOUR = 15
DERIVATIVES_CLOSE_MINUTE = 40
# Backward-compatible names.
CASH_SESSION_START_HOUR = CAS_SESSION_START_HOUR
CASH_SESSION_START_MINUTE = CAS_SESSION_START_MINUTE
CASH_FORCE_EXIT_HOUR = CAS_FORCE_EXIT_HOUR
CASH_FORCE_EXIT_MINUTE = CAS_FORCE_EXIT_MINUTE


@dataclass
class PaperTrade:
    trade_id: str
    strategy: str
    direction: str
    entry_timestamp: str
    entry_spot: float
    peak_favorable_pct: float = 0.0
    worst_adverse_pct: float = 0.0
    exit_timestamp: str | None = None
    exit_spot: float | None = None
    exit_reason: str | None = None
    status: str = "OPEN"

    def update(self, timestamp: str, spot: float) -> dict[str, Any]:
        favorable = ((spot - self.entry_spot) / self.entry_spot * 100.0) if self.direction == "BULLISH" else ((self.entry_spot - spot) / self.entry_spot * 100.0)
        self.peak_favorable_pct = max(self.peak_favorable_pct, favorable)
        self.worst_adverse_pct = min(self.worst_adverse_pct, favorable)
        return {"trade_id": self.trade_id, "timestamp": timestamp, "favorable_pct": round(favorable, 4), "mfe_pct": round(self.peak_favorable_pct, 4), "mae_pct": round(self.worst_adverse_pct, 4)}

    def close(self, timestamp: str, spot: float, reason: str) -> dict[str, Any]:
        self.update(timestamp, spot)
        self.exit_timestamp = timestamp
        self.exit_spot = float(spot)
        self.exit_reason = reason
        self.status = "CLOSED"
        realized_proxy = ((spot - self.entry_spot) if self.direction == "BULLISH" else (self.entry_spot - spot))
        return {**asdict(self), "spot_move_proxy": round(realized_proxy, 4), "read_only": True, "execution": "NONE"}


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(IST)
    except ValueError:
        return None


def trading_day(timestamp: str | None) -> str | None:
    dt = _timestamp(timestamp)
    return dt.date().isoformat() if dt else None


def _active_strategy_for_day(day: str | None) -> str | None:
    if not day:
        return None
    try:
        from quantnifty.learning_store import load_events
        active: dict[str, dict[str, Any]] = {}
        for event in load_events("outcomes", day):
            outcome = event.get("outcome") if isinstance(event, dict) else None
            if not isinstance(outcome, dict):
                continue
            trade_id = str(outcome.get("trade_id") or "")
            if not trade_id:
                continue
            status = str(outcome.get("status") or outcome.get("lifecycle") or "").upper()
            if status == "OPEN":
                active[trade_id] = outcome
            elif status == "CLOSED":
                active.pop(trade_id, None)
        if not active:
            return None
        latest = max(active.values(), key=lambda row: str(row.get("entry_timestamp") or row.get("timestamp") or ""))
        return str(latest.get("strategy") or "").strip().lower() or None
    except Exception:
        return None


def session_close_required(timestamp: str | None) -> bool:
    """Return whether the current active paper position must be closed.

    Normal NIFTY-option positions are closed before the NSE CAS begins at
    15:15. A CAS-aware NIFTY-derivatives position may remain through the CAS
    matching period, but is forcibly closed at 15:39, one minute before the
    NSE equity-derivatives regular-session close at 15:40.
    """
    dt = _timestamp(timestamp)
    if not dt:
        return False
    local = dt.astimezone(IST)
    t = local.time()
    minute = (t.hour, t.minute)
    if minute >= (CAS_FORCE_EXIT_HOUR, CAS_FORCE_EXIT_MINUTE):
        return True
    if minute < (CAS_SESSION_START_HOUR, CAS_SESSION_START_MINUTE):
        return False
    strategy = _active_strategy_for_day(local.date().isoformat())
    return strategy != "cas_reentry"


def same_trading_day(entry_timestamp: str | None, timestamp: str | None) -> bool:
    entry_day = trading_day(entry_timestamp)
    current_day = trading_day(timestamp)
    return bool(entry_day and current_day and entry_day == current_day)


def make_trade_id(timestamp: str, sequence: int) -> str:
    return f"paper-{timestamp.replace(':', '').replace('-', '').replace('+', '')}-{sequence:04d}"
