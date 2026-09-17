from datetime import datetime
from zoneinfo import ZoneInfo

import quantnifty.paper_entry_gate as gate

IST = ZoneInfo("Asia/Kolkata")


def data(hour: int, minute: int, strategy: str) -> dict:
    return {
        "timestamp": datetime(2026, 9, 17, hour, minute, tzinfo=IST).isoformat(),
        "spot": 23400.0,
    }


def test_normal_entries_stop_before_cash_window(monkeypatch):
    monkeypatch.setattr(gate, "_lifecycle", lambda day: ({}, {}))
    result = gate.evaluate_paper_entry(data(15, 14, "directional"), "BULLISH", "LIVE", "directional")
    assert result["allowed"] is False
    assert result["reason"] == "NORMAL_ENTRY_CUTOFF"


def test_cash_strategy_only_enters_inside_cash_window(monkeypatch):
    monkeypatch.setattr(gate, "_lifecycle", lambda day: ({}, {}))
    before = gate.evaluate_paper_entry(data(15, 14, "cas_reentry"), "BULLISH", "LIVE", "cas_reentry")
    assert before["reason"] == "CASH_SESSION_NOT_STARTED"

    inside = gate.evaluate_paper_entry(data(15, 16, "cas_reentry"), "BULLISH", "LIVE", "cas_reentry")
    assert inside["allowed"] is True


def test_cash_entries_stop_at_1527(monkeypatch):
    monkeypatch.setattr(gate, "_lifecycle", lambda day: ({}, {}))
    result = gate.evaluate_paper_entry(data(15, 27, "cas_reentry"), "BULLISH", "LIVE", "cas_reentry")
    assert result["allowed"] is False
    assert result["reason"] == "CASH_ENTRY_CUTOFF"
