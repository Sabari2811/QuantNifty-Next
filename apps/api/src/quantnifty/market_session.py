from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
# Paid application runtime window. The live market-provider window is narrower.
RUNTIME_OPEN = time(9, 0)
RUNTIME_CLOSE = time(16, 0)
# NSE equity-derivatives regular session. CAS is a cash-segment session and does
# not change the NIFTY derivatives close.
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 40)


def application_runtime_state(now: datetime | None = None) -> dict[str, object]:
    """Return the intended weekday application runtime window in IST."""
    current = (now or datetime.now(IST)).astimezone(IST)
    if current.weekday() >= 5:
        return {"open": False, "phase": "CLOSED", "reason": "weekend", "local_time": current.isoformat()}
    if current.time() < RUNTIME_OPEN:
        return {"open": False, "phase": "PRE_RUNTIME", "reason": "before_09:00", "local_time": current.isoformat()}
    if current.time() >= RUNTIME_CLOSE:
        return {"open": False, "phase": "CLOSED", "reason": "after_16:00", "local_time": current.isoformat()}
    return {"open": True, "phase": "RUNTIME", "reason": "weekday_runtime_window", "local_time": current.isoformat()}


def is_application_runtime_window(now: datetime | None = None) -> bool:
    return bool(application_runtime_state(now)["open"])


def market_session_state(now: datetime | None = None) -> dict[str, object]:
    """Return the NSE NIFTY-equity-derivatives live-provider window in IST.

    NSE CAS (15:15-15:35) applies to the equity cash segment. NIFTY options
    remain equity derivatives and their regular market closes at 15:40 IST.
    """
    current = (now or datetime.now(IST)).astimezone(IST)
    if current.weekday() >= 5:
        return {"open": False, "phase": "CLOSED", "reason": "weekend", "local_time": current.isoformat()}
    if current.time() < MARKET_OPEN:
        return {"open": False, "phase": "PRE_OPEN", "reason": "before_09:15", "local_time": current.isoformat()}
    if current.time() >= MARKET_CLOSE:
        return {"open": False, "phase": "CLOSED", "reason": "after_15:40", "local_time": current.isoformat()}
    return {"open": True, "phase": "LIVE", "reason": "nse_equity_derivatives_session", "local_time": current.isoformat()}


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
    runtime = application_runtime_state(now)
    return {
        "data_integrity": "MARKET_CLOSED",
        "mode": "READ_ONLY",
        "provider": "INDstocks",
        "live_provider_connected": False,
        "application_runtime": runtime,
        "market_session": state,
        "message": "NSE NIFTY derivatives live market session is closed. Live provider polling is stopped.",
        "timestamp": datetime.now(IST).isoformat(),
    }
