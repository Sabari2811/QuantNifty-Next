from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


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


def session_close_required(timestamp: str | None) -> bool:
    dt = _timestamp(timestamp)
    return bool(dt and (dt.time().hour, dt.time().minute) >= (15, 30))


def same_trading_day(entry_timestamp: str | None, timestamp: str | None) -> bool:
    entry_day = trading_day(entry_timestamp)
    current_day = trading_day(timestamp)
    return bool(entry_day and current_day and entry_day == current_day)


def make_trade_id(timestamp: str, sequence: int) -> str:
    return f"paper-{timestamp.replace(':', '').replace('-', '').replace('+', '')}-{sequence:04d}"
