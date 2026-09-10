from __future__ import annotations

from quantnifty import live_paper_manager as manager_module
from quantnifty import paper_ledger_api as ledger_module
from quantnifty.live_paper_manager import LivePaperManager
from quantnifty.paper_trade_tracker import session_close_required, trading_day


def _decision(approved=True):
    return {
        "strategy": "adaptive",
        "signal": {"direction": "BULLISH", "confidence": 82, "evidence": ["market structure BULLISH", "OI flow BULLISH"], "rationale": ["gamma support"], "adaptive": {"regime": "TREND", "selected_strategy": "directional", "preferred_direction": "BULLISH", "readiness_pct": 82, "reason": "aligned evidence"}},
        "risk": {"approved": approved, "gates": {"direction": True, "confidence": True}, "reasons": [] if approved else ["confidence"]},
        "execution_plan": {"instrument": {"security_id": "123", "trading_symbol": "NIFTY-23500-CE", "strike": 23500, "side": "CE", "lot_size": 65}, "quantity": 65},
    }


def _snapshot(ts="2026-09-10T04:00:00+00:00", spot=23500, bid=110, ask=112):
    return {"timestamp": ts, "spot": spot, "option_chain": [{"security_id": "123", "trading_symbol": "NIFTY-23500-CE", "strike": 23500, "side": "CE", "bid": bid, "ask": ask, "last_price": 111}]}


def test_trading_day_and_session_close():
    assert trading_day("2026-09-10T04:00:00+00:00") == "2026-09-10"
    assert not session_close_required("2026-09-10T09:59:59+00:00")
    assert session_close_required("2026-09-10T10:00:00+00:00")


def test_open_close_persists_complete_trade_evidence(monkeypatch):
    recorded = []
    monkeypatch.setattr(manager_module, "record_outcome", recorded.append)
    monkeypatch.setattr(manager_module.LivePaperManager, "_recover", lambda self: None)
    manager = LivePaperManager()
    manager.process(_snapshot(), _decision())
    assert recorded[0]["day"] == "2026-09-10"
    assert recorded[0]["entry_price"] == 112
    assert recorded[0]["quantity"] == 65
    assert recorded[0]["entry_reasons"]["signal_evidence"]
    close = manager.process(_snapshot(ts="2026-09-10T10:00:00+00:00", spot=23520, bid=125, ask=127), _decision())
    assert close["status"] == "CLOSED"
    assert recorded[1]["exit_reason"] == "SESSION_CLOSE"
    assert recorded[1]["exit_reasons"]["exit_reason"] == "SESSION_CLOSE"
    assert recorded[1]["realized_pnl"] == (125 - 112) * 65


def test_ledger_marks_open_position_dynamically(monkeypatch):
    open_row = {"trade_id": "paper-test", "status": "OPEN", "strategy": "directional", "direction": "BULLISH", "entry_timestamp": "2026-09-10T04:00:00+00:00", "entry_spot": 23500, "entry_price": 100, "quantity": 65, "instrument": {"security_id": "123", "trading_symbol": "NIFTY-23500-CE", "strike": 23500, "side": "CE"}}
    monkeypatch.setattr(ledger_module, "load_events", lambda kind, day=None: [{"timestamp": open_row["entry_timestamp"], "outcome": open_row}] if kind == "outcomes" else [])
    monkeypatch.setattr(ledger_module, "load_snapshots", lambda day=None: [_snapshot(bid=120, ask=122)])
    payload = ledger_module.paper_ledger("2026-09-10")
    assert payload["summary"]["open_positions"] == 1
    assert payload["summary"]["unrealized_pnl"] == 1300
    assert payload["open_positions"][0]["mark_price"] == 120
    assert payload["open_positions"][0]["unrealized_pnl"] == 1300


def test_ledger_recovers_legacy_same_day_rows_without_day_field(monkeypatch):
    closed = {"trade_id": "paper-legacy", "status": "CLOSED", "direction": "BULLISH", "entry_timestamp": "2026-09-10T04:00:00+00:00", "exit_timestamp": "2026-09-10T04:10:00+00:00", "entry_price": 100, "exit_price": 108, "quantity": 65, "gross_pnl_proxy": 520}
    monkeypatch.setattr(ledger_module, "load_events", lambda kind, day=None: [{"timestamp": closed["exit_timestamp"], "outcome": closed}] if kind == "outcomes" else [])
    monkeypatch.setattr(ledger_module, "load_snapshots", lambda day=None: [])
    payload = ledger_module.paper_ledger("2026-09-10")
    assert payload["summary"]["closed_trades"] == 1
    assert payload["summary"]["realized_pnl"] == 520
