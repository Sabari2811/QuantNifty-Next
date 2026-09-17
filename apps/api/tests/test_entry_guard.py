from __future__ import annotations

from datetime import datetime, timezone

from quantnifty import entry_guard
from quantnifty.decision_validation import validate_decision


def _data(*, spot=23212.0, support=23200.0, move=-1.5, timestamp="2026-09-17T05:40:00+00:00"):
    return {
        "timestamp": timestamp,
        "spot": spot,
        "support": support,
        "resistance": 23300,
        "data_integrity": "LIVE_PROVIDER",
        "option_chain": [],
        "intelligence": {
            "market_state": {"state": "TREND_DOWN"},
            "move_attribution": {"points": move, "quality": "LOW"},
            "events": [],
        },
    }


def _result(direction="BEARISH"):
    return {
        "signal": {"direction": direction, "confidence": 75, "scores": {direction: 80}, "evidence": ["OI_FLOW"]},
        "risk": {"approved": True, "gates": {"direction": True, "confidence": True, "liquidity": True}, "reasons": []},
        "execution_plan": {
            "status": "APPROVED_READ_ONLY",
            "execution_enabled": False,
            "order_action": "DISABLED",
            "instrument": {"side": "PE" if direction == "BEARISH" else "CE"},
            "stop_points": 50,
            "target_points": 100,
            "risk_reward": 2,
        },
    }


def test_support_area_without_break_is_blocked(monkeypatch):
    monkeypatch.setattr(entry_guard, "_latest_failed_signal", lambda direction, data: None)
    result = _result()
    audit = entry_guard.evaluate_entry_guards(_data(), result, "LIVE")
    assert audit["blocked"] is True
    assert "support_breakdown_confirmation" in audit["reasons"]
    assert result["risk"]["approved"] is False
    assert result["execution_plan"]["status"] == "BLOCKED"


def test_strong_bearish_displacement_away_from_support_is_allowed(monkeypatch):
    monkeypatch.setattr(entry_guard, "_latest_failed_signal", lambda direction, data: None)
    result = _result()
    audit = entry_guard.evaluate_entry_guards(_data(spot=23257.85, support=23200, move=-37.55), result, "LIVE")
    assert audit["blocked"] is False
    assert audit["displacement"]["directional_points"] == 37.55
    assert result["risk"]["approved"] is True


def test_confirmed_support_break_is_allowed(monkeypatch):
    monkeypatch.setattr(entry_guard, "_latest_failed_signal", lambda direction, data: None)
    result = _result()
    audit = entry_guard.evaluate_entry_guards(_data(spot=23194.0, support=23200.0, move=-6.0), result, "LIVE")
    assert audit["support"]["status"] == "CONFIRMED_BREAK"
    assert audit["gates"]["support_breakdown_confirmation"] is True
    assert result["risk"]["approved"] is True


def test_failed_signal_cooldown_blocks_immediate_same_direction_reentry(monkeypatch):
    failed = {
        "trade_id": "T-FAIL",
        "direction": "BEARISH",
        "status": "CLOSED",
        "realized_pnl": -104,
        "exit_timestamp": "2026-09-17T05:39:30+00:00",
    }
    monkeypatch.setattr(entry_guard, "_latest_failed_signal", lambda direction, data: failed)
    result = _result()
    audit = entry_guard.evaluate_entry_guards(_data(spot=23257.0, support=23200, move=-10.0), result, "LIVE")
    assert audit["cooldown"]["status"] == "FAILED_SIGNAL_COOLDOWN"
    assert audit["gates"]["failed_signal_cooldown"] is False
    assert result["risk"]["approved"] is False


def test_missing_support_does_not_invent_a_block(monkeypatch):
    monkeypatch.setattr(entry_guard, "_latest_failed_signal", lambda direction, data: None)
    result = _result()
    audit = entry_guard.evaluate_entry_guards(_data(spot=23257.0, support=None, move=-10.0), result, "LIVE")
    assert audit["support"]["status"] == "UNAVAILABLE_PASS"
    assert audit["gates"]["support_breakdown_confirmation"] is True
    assert result["risk"]["approved"] is True


def test_replay_mode_is_untouched(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("live guard must not inspect live outcomes in replay")

    monkeypatch.setattr(entry_guard, "_latest_failed_signal", fail_if_called)
    result = _result()
    audit = entry_guard.evaluate_entry_guards(_data(), result, "BACKTEST")
    assert audit == {"applied": False, "reason": "NON_LIVE_MODE"}
    assert result["risk"]["approved"] is True


def test_validation_surfaces_entry_guard_block(monkeypatch):
    monkeypatch.setattr(entry_guard, "_latest_failed_signal", lambda direction, data: None)
    result = _result()
    validation = validate_decision(_data(), result, "LIVE")
    assert validation["valid"] is False
    assert "entry_guard:support_breakdown_confirmation" in validation["errors"]
    assert result["risk"]["approved"] is False
