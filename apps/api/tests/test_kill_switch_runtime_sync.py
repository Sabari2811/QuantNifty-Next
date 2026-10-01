from __future__ import annotations

from quantnifty import live_paper_manager


def _manager_with_state(active: bool):
    manager = object.__new__(live_paper_manager.LivePaperManager)
    manager.kill_switch_day = "2026-10-01"
    manager.kill_switch_active = active
    return manager


def test_refresh_kill_switch_reconciles_durable_release(monkeypatch):
    manager = _manager_with_state(True)
    monkeypatch.setattr(live_paper_manager, "current_day", lambda: "2026-10-01")
    monkeypatch.setattr(
        live_paper_manager,
        "kill_switch_state",
        lambda day: {"day": day, "active": False},
    )

    assert manager._refresh_kill_switch() is False
    assert manager.kill_switch_active is False
    assert manager.kill_switch_day == "2026-10-01"


def test_refresh_kill_switch_reconciles_durable_activation(monkeypatch):
    manager = _manager_with_state(False)
    monkeypatch.setattr(live_paper_manager, "current_day", lambda: "2026-10-01")
    monkeypatch.setattr(
        live_paper_manager,
        "kill_switch_state",
        lambda day: {"day": day, "active": True},
    )

    assert manager._refresh_kill_switch() is True
    assert manager.kill_switch_active is True
