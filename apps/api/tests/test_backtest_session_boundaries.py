from __future__ import annotations

from quantnifty.backtest import _expiry_datetime, _is_market_session


def test_recorder_expiry_format_is_month_first():
    value = _expiry_datetime("08/04/2026 14:00")
    assert value is not None
    assert value.date().isoformat() == "2026-08-04"


def test_market_session_filter_excludes_outside_hours():
    assert _is_market_session({"timestamp": "2026-09-01T09:14:59+05:30"}) is False
    assert _is_market_session({"timestamp": "2026-09-01T09:15:00+05:30"}) is True
    assert _is_market_session({"timestamp": "2026-09-01T15:30:00+05:30"}) is True
    assert _is_market_session({"timestamp": "2026-09-01T15:30:01+05:30"}) is False
