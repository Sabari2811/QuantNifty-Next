from __future__ import annotations

from quantnifty import paper_entry_gate


def _data(timestamp="2026-09-17T05:40:00+00:00", spot=23220.0, state="TREND_DOWN", events=None):
    return {"timestamp": timestamp, "spot": spot, "data_integrity": "LIVE_PROVIDER", "option_chain": [], "intelligence": {"market_state": {"state": state}, "events": events or []}}


def _closed(*, trade_id="T1", direction="BEARISH", exit_timestamp="2026-09-17T05:30:00+00:00", exit_spot=23220.0, strategy="directional", pnl=10.0):
    return {"outcome": {"trade_id": trade_id, "status": "CLOSED", "direction": direction, "exit_timestamp": exit_timestamp, "exit_spot": exit_spot, "strategy": strategy, "realized_pnl": pnl}}


def _open(*, trade_id="T1", direction="BEARISH"):
    return {"outcome": {"trade_id": trade_id, "status": "OPEN", "direction": direction, "entry_timestamp": "2026-09-17T05:35:00+00:00"}}


def test_no_prior_trade_allows_candidate(monkeypatch):
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: [])
    gate = paper_entry_gate.evaluate_paper_entry(_data(), "BEARISH")
    assert gate["action"] == "TAKE_TRADE" and gate["allowed"] is True


def test_active_trade_is_hard_lock(monkeypatch):
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: [_open()])
    gate = paper_entry_gate.evaluate_paper_entry(_data(), "BEARISH")
    assert gate["action"] == "HOLD_ACTIVE_TRADE" and gate["allowed"] is False and gate["reason"] == "ACTIVE_TRADE_LOCK"


def test_any_recent_close_blocks_reentry_for_five_minutes(monkeypatch):
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: [_closed(direction="BULLISH")])
    gate = paper_entry_gate.evaluate_paper_entry(_data(timestamp="2026-09-17T05:34:00+00:00", spot=23230), "BEARISH")
    assert gate["action"] == "WAIT_CONFIRMATION" and gate["reason"] == "REENTRY_COOLDOWN"


def _both_slots_then_bearish(*, spot=23221.0):
    return [
        _closed(trade_id="T1", direction="BULLISH", exit_timestamp="2026-09-17T05:00:00+00:00", exit_spot=23220),
        _closed(trade_id="T2", direction="BEARISH", exit_timestamp="2026-09-17T05:10:00+00:00", exit_spot=23220),
    ]


def test_same_direction_after_both_slots_requires_new_structure(monkeypatch):
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: _both_slots_then_bearish())
    gate = paper_entry_gate.evaluate_paper_entry(_data(timestamp="2026-09-17T05:40:00+00:00", spot=23221), "BEARISH", strategy="gamma_transition")
    assert gate["action"] == "WAIT_CONFIRMATION" and gate["reason"] == "REENTRY_STRUCTURE_REQUIRED"


def test_third_same_direction_with_eight_point_displacement_allows_reentry(monkeypatch):
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: _both_slots_then_bearish())
    gate = paper_entry_gate.evaluate_paper_entry(_data(timestamp="2026-09-17T05:40:00+00:00", spot=23211), "BEARISH", strategy="gamma_transition")
    assert gate["action"] == "TAKE_TRADE" and gate["reason"] == "NEW_STRUCTURAL_EVIDENCE" and gate["directional_displacement_points"] == 9.0 and gate["third_trade"] is True


def test_direction_change_after_cooldown_allows_second_direction_slot(monkeypatch):
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: [_closed(direction="BEARISH")])
    gate = paper_entry_gate.evaluate_paper_entry(_data(timestamp="2026-09-17T05:40:00+00:00", spot=23220), "BULLISH")
    assert gate["action"] == "TAKE_TRADE" and gate["reason"] == "DIRECTION_CHANGE_AFTER_COOLDOWN"


def test_daily_limit_blocks_fourth_trade(monkeypatch):
    rows = [_closed(trade_id="T1", direction="BEARISH", exit_timestamp="2026-09-17T05:00:00+00:00"), _closed(trade_id="T2", direction="BULLISH", exit_timestamp="2026-09-17T05:10:00+00:00"), _closed(trade_id="T3", direction="BEARISH", exit_timestamp="2026-09-17T05:20:00+00:00", strategy="gamma_transition")]
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: rows)
    gate = paper_entry_gate.evaluate_paper_entry(_data(timestamp="2026-09-17T05:40:00+00:00", spot=23200), "BULLISH")
    assert gate["action"] == "NO_TRADE" and gate["reason"] == "DAILY_TRADE_LIMIT" and gate["max_daily_trades"] == 3


def test_one_bearish_momentum_slot_per_day(monkeypatch):
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: [_closed(trade_id="T1", direction="BEARISH", strategy="directional", exit_timestamp="2026-09-17T05:00:00+00:00")])
    gate = paper_entry_gate.evaluate_paper_entry(_data(timestamp="2026-09-17T05:40:00+00:00", spot=23200), "BEARISH", strategy="adaptive")
    assert gate["action"] == "NO_TRADE" and gate["reason"] == "BEARISH_MOMENTUM_TRADE_LIMIT"


def test_one_bullish_momentum_slot_per_day(monkeypatch):
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: [_closed(trade_id="T1", direction="BULLISH", strategy="adaptive", exit_timestamp="2026-09-17T05:00:00+00:00")])
    gate = paper_entry_gate.evaluate_paper_entry(_data(timestamp="2026-09-17T05:40:00+00:00", state="TREND_UP", spot=23230), "BULLISH", strategy="directional")
    assert gate["action"] == "NO_TRADE" and gate["reason"] == "BULLISH_MOMENTUM_TRADE_LIMIT"


def test_third_trade_is_available_only_after_both_direction_slots(monkeypatch):
    rows = [_closed(trade_id="T1", direction="BEARISH", exit_timestamp="2026-09-17T05:00:00+00:00")]
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: rows)
    gate = paper_entry_gate.evaluate_paper_entry(_data(timestamp="2026-09-17T05:40:00+00:00", state="TREND_DOWN", spot=23190), "BEARISH", strategy="gamma_transition")
    assert gate["allowed"] is False and gate["reason"] == "BEARISH_MOMENTUM_TRADE_LIMIT"


def test_three_trade_cycle_allows_final_reversal_slot(monkeypatch):
    rows = [_closed(trade_id="T1", direction="BULLISH", exit_timestamp="2026-09-17T05:00:00+00:00"), _closed(trade_id="T2", direction="BEARISH", exit_timestamp="2026-09-17T05:10:00+00:00")]
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: rows)
    gate = paper_entry_gate.evaluate_paper_entry(_data(timestamp="2026-09-17T05:40:00+00:00", state="TREND_DOWN", spot=23200), "BEARISH", strategy="gamma_transition")
    assert gate["allowed"] is True and gate["third_trade"] is True


def test_no_new_entry_after_normal_session_cutoff(monkeypatch):
    monkeypatch.setattr(paper_entry_gate, "load_events", lambda *args, **kwargs: [])
    gate = paper_entry_gate.evaluate_paper_entry(_data(timestamp="2026-09-17T09:59:30+00:00"), "BEARISH")
    assert gate["action"] == "NO_TRADE" and gate["reason"] == "NORMAL_SESSION_CLOSED_FOR_CASH_SESSION"


def test_replay_never_reads_live_outcomes(monkeypatch):
    def fail(*args, **kwargs): raise AssertionError("replay must not inspect live paper outcomes")
    monkeypatch.setattr(paper_entry_gate, "load_events", fail)
    gate = paper_entry_gate.evaluate_paper_entry(_data(), "BEARISH", "BACKTEST")
    assert gate["applied"] is False and gate["allowed"] is True
