from datetime import datetime
from zoneinfo import ZoneInfo

from quantnifty.market_session import is_live_market_session, market_session_state

IST = ZoneInfo("Asia/Kolkata")


def dt(hour: int, minute: int, *, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=IST)


def test_live_provider_window_is_open_from_0915_through_1529_weekdays():
    assert is_live_market_session(dt(9, 15))
    assert is_live_market_session(dt(12, 0))
    assert is_live_market_session(dt(15, 29))


def test_live_provider_window_is_closed_before_open_and_at_close():
    assert not is_live_market_session(dt(9, 14))
    assert not is_live_market_session(dt(15, 30))
    assert market_session_state(dt(15, 30))["reason"] == "after_15:30"


def test_live_provider_window_is_closed_on_weekend():
    saturday = datetime(2026, 9, 12, 12, 0, tzinfo=IST)
    state = market_session_state(saturday)
    assert state["open"] is False
    assert state["reason"] == "weekend"
