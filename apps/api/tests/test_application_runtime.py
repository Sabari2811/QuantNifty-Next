from datetime import datetime
from zoneinfo import ZoneInfo

from quantnifty.market_session import application_runtime_state

IST = ZoneInfo("Asia/Kolkata")


def test_runtime_opens_at_0900_weekday():
    state = application_runtime_state(datetime(2026, 9, 17, 9, 0, tzinfo=IST))
    assert state["open"] is True
    assert state["phase"] == "RUNTIME"


def test_runtime_includes_post_market_until_1600():
    state = application_runtime_state(datetime(2026, 9, 17, 15, 59, 59, tzinfo=IST))
    assert state["open"] is True


def test_runtime_closes_at_1600():
    state = application_runtime_state(datetime(2026, 9, 17, 16, 0, tzinfo=IST))
    assert state["open"] is False
    assert state["phase"] == "CLOSED"


def test_runtime_closed_weekend():
    state = application_runtime_state(datetime(2026, 9, 19, 10, 0, tzinfo=IST))
    assert state["open"] is False
    assert state["reason"] == "weekend"
