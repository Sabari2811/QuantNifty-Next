from __future__ import annotations

from quantnifty import paper_control


def test_kill_switch_defaults_inactive(monkeypatch):
    monkeypatch.setattr(paper_control, "load_events", lambda kind, day=None: [])
    state = paper_control.kill_switch_state("2026-09-17")
    assert state["day"] == "2026-09-17"
    assert state["active"] is False
    assert state["new_entries_blocked"] is False


def test_kill_switch_reads_latest_activation(monkeypatch):
    events = [
        {"action": "KILL_SWITCH_ON", "timestamp": "2026-09-17T10:00:00+05:30", "reason": "MANUAL_KILL_SWITCH"}
    ]
    monkeypatch.setattr(paper_control, "load_events", lambda kind, day=None: events if kind == "paper_controls" else [])
    state = paper_control.kill_switch_state("2026-09-17")
    assert state["active"] is True
    assert state["activated_at"] == "2026-09-17T10:00:00+05:30"
    assert state["open_positions_must_close"] is True


def test_activation_is_idempotent(monkeypatch):
    events = []
    monkeypatch.setattr(paper_control, "load_events", lambda kind, day=None: events if kind == "paper_controls" else [])

    def record_control(control):
        events.append(control)
        return control

    monkeypatch.setattr(paper_control, "record_control", record_control)
    monkeypatch.setattr(paper_control, "current_day", lambda: "2026-09-17")
    first = paper_control.activate_kill_switch()
    second = paper_control.activate_kill_switch()
    assert first["active"] is True
    assert second["active"] is True
    assert len(events) == 1
