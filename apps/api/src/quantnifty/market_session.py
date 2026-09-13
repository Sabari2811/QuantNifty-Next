from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def market_session_state(now: datetime | None = None) -> dict[str, object]:
    """Return the NSE live-provider window in IST."""
    current = (now or datetime.now(IST)).astimezone(IST)
    if current.weekday() >= 5:
        return {"open": False, "phase": "CLOSED", "reason": "weekend", "local_time": current.isoformat()}
    if current.time() < MARKET_OPEN:
        return {"open": False, "phase": "PRE_OPEN", "reason": "before_09:15", "local_time": current.isoformat()}
    if current.time() >= MARKET_CLOSE:
        return {"open": False, "phase": "CLOSED", "reason": "after_15:30", "local_time": current.isoformat()}
    return {"open": True, "phase": "LIVE", "reason": "nse_live_session", "local_time": current.isoformat()}


def is_live_market_session(now: datetime | None = None) -> bool:
    return bool(market_session_state(now)["open"])


def seconds_until_next_open(now: datetime | None = None) -> float:
    """Return seconds until the next weekday 09:15 IST."""
    current = (now or datetime.now(IST)).astimezone(IST)
    if current.weekday() < 5 and current.time() < MARKET_OPEN:
        candidate = current.replace(hour=9, minute=15, second=0, microsecond=0)
    else:
        candidate = (current + timedelta(days=1)).replace(hour=9, minute=15, second=0, microsecond=0)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
    return max(1.0, (candidate - current).total_seconds())


def closed_payload(now: datetime | None = None) -> dict[str, object]:
    state = market_session_state(now)
    return {
        "data_integrity": "MARKET_CLOSED",
        "mode": "READ_ONLY",
        "provider": "INDstocks",
        "live_provider_connected": False,
        "market_session": state,
        "message": "NSE live market session is closed. Live provider polling is stopped.",
        "timestamp": datetime.now(IST).isoformat(),
    }
