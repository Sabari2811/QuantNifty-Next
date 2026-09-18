from datetime import datetime
from zoneinfo import ZoneInfo

from quantnifty.paper_trade_tracker import session_close_required

IST = ZoneInfo("Asia/Kolkata")


def ts(hour: int, minute: int) -> str:
    return datetime(2026, 9, 17, hour, minute, tzinfo=IST).isoformat()


def open_event(strategy: str) -> list[dict]:
    return [{"outcome": {"trade_id": "paper-test", "status": "OPEN", "strategy": strategy, "entry_timestamp": ts(14, 0)}}]


def test_normal_position_is_forced_out_at_cash_session_start(monkeypatch):
    monkeypatch.setattr("quantnifty.learning_store.load_events", lambda kind, day=None: open_event("directional"))
    assert session_close_required(ts(15, 14)) is False
    assert session_close_required(ts(15, 15)) is True


def test_cash_position_can_hold_until_cash_force_exit(monkeypatch):
    monkeypatch.setattr("quantnifty.learning_store.load_events", lambda kind, day=None: open_event("cas_reentry"))
    assert session_close_required(ts(15, 15)) is False
    assert session_close_required(ts(15, 27)) is False
    assert session_close_required(ts(15, 28)) is False
    assert session_close_required(ts(15, 29)) is True
