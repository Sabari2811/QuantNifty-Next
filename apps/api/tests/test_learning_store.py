from __future__ import annotations

import json

from quantnifty.learning_store import learning_status, load_events, load_snapshots, record_decision, record_snapshot


def test_learning_store_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTNIFTY_LEARNING_ROOT", str(tmp_path))
    snapshot = {"timestamp": "2026-09-07T04:00:00+00:00", "spot": 25000, "data_integrity": "LIVE_PROVIDER"}
    decision = {"strategy": "adaptive", "status": "NO_TRADE", "risk": {"approved": False}}
    record_snapshot(snapshot)
    record_decision(snapshot, decision)
    assert load_snapshots() == [snapshot]
    assert load_events("decisions")[0]["decision"] == decision
    status = learning_status()
    assert status["snapshots"] == 1
    assert status["decisions"] == 1
    assert status["outcomes"] == 0


def test_learning_store_events_are_json_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTNIFTY_LEARNING_ROOT", str(tmp_path))
    record_snapshot({"timestamp": "2026-09-07T04:00:01+00:00", "spot": 25001})
    rows = (tmp_path / "snapshots.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    event = json.loads(rows[0])
    assert event["schema_version"] == "adaptive-learning-event-v1"
    assert event["kind"] == "snapshots"
