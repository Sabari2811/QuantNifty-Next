from __future__ import annotations

from quantnifty.position_hold_backtest import _thesis_direction, _selected_strategy, _thesis_still_valid


def test_thesis_helpers_preserve_direction_and_strategy():
    decision = {
        "signal": {"direction": "BEARISH", "adaptive": {"selected_strategy": "early_accumulation"}},
        "risk": {"selected_strategy": "adaptive"},
    }
    assert _thesis_direction(decision) == "BEARISH"
    assert _selected_strategy(decision) == "early_accumulation"


def test_thesis_invalidates_when_direction_changes(monkeypatch):
    monkeypatch.setattr(
        "quantnifty.position_hold_backtest.final_decision",
        lambda *args, **kwargs: {"signal": {"direction": "BULLISH"}, "risk": {"approved": True}},
    )
    assert _thesis_still_valid({"timestamp": "2026-09-11T04:00:00+00:00"}, None, "BEARISH") is False


def test_thesis_remains_open_for_same_approved_direction(monkeypatch):
    monkeypatch.setattr(
        "quantnifty.position_hold_backtest.final_decision",
        lambda *args, **kwargs: {"signal": {"direction": "BEARISH"}, "risk": {"approved": True}},
    )
    assert _thesis_still_valid({"timestamp": "2026-09-11T04:00:00+00:00"}, None, "BEARISH") is True
