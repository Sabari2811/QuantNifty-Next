from __future__ import annotations

from quantnifty.after_market_scheduler import _training_already_completed


def test_scheduler_requires_completed_stored_day_training(monkeypatch):
    monkeypatch.setattr(
        "quantnifty.after_market_scheduler.latest_research",
        lambda day: [
            {"research": {"type": "after_market", "status": "COMPLETED", "training_source": "LIVE_PROVIDER"}},
            {"research": {"type": "after_market", "status": "COMPLETED", "training_source": "STORED_DAY"}},
        ],
    )
    assert _training_already_completed("2026-09-07") is True


def test_scheduler_does_not_accept_incomplete_or_missing_training(monkeypatch):
    monkeypatch.setattr(
        "quantnifty.after_market_scheduler.latest_research",
        lambda day: [
            {"research": {"type": "after_market", "status": "NO_DATA", "training_source": "STORED_DAY"}},
            {"research": {"type": "after_market", "status": "COMPLETED", "training_source": "LIVE_PROVIDER"}},
        ],
    )
    assert _training_already_completed("2026-09-07") is False
