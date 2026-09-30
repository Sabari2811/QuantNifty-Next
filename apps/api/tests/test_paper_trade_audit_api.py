from __future__ import annotations

from quantnifty import paper_trade_audit_api


def test_paper_trade_audit_exposes_logic_trace(monkeypatch):
    outcome = {
        "outcome": {
            "trade_id": "T1",
            "status": "CLOSED",
            "direction": "BEARISH",
            "strategy": "adaptive",
            "entry_timestamp": "2026-09-30T04:00:00+00:00",
            "entry_spot": 23400.0,
            "entry_price": 120.0,
            "entry_delta": -0.48,
            "delta_risk_at_entry": 18.0,
            "instrument": {"strike": 23400, "side": "PE"},
            "entry_reasons": {"paper_entry_gate": "TAKE_TRADE"},
            "entry_decision": {
                "strategy": "adaptive",
                "decision_action": "TAKE_TRADE",
                "signal": {
                    "direction": "BEARISH",
                    "confidence": 82.0,
                    "evidence": ["gamma_flip"],
                    "rationale": ["negative gamma"],
                },
                "risk": {
                    "approved": True,
                    "gates": {"context_alignment": True},
                    "reasons": [],
                },
                "execution_plan": {"instrument": {"strike": 23400, "side": "PE"}},
            },
            "entry_risk": {"approved": True, "reasons": []},
            "exit_timestamp": "2026-09-30T04:05:00+00:00",
            "exit_spot": 23380.0,
            "exit_price": 130.0,
            "realized_pnl": 650.0,
            "read_only": True,
            "execution": "NONE",
        }
    }
    decision = {
        "kind": "decisions",
        "timestamp": "2026-09-30T04:00:01+00:00",
        "strategy": "adaptive",
        "decision": outcome["outcome"]["entry_decision"],
    }

    monkeypatch.setattr(
        paper_trade_audit_api,
        "load_events",
        lambda kind, day=None: [outcome] if kind == "outcomes" else [decision],
    )

    result = paper_trade_audit_api.paper_trade_audit("2026-09-30")

    assert result["day"] == "2026-09-30"
    assert result["summary"]["closed_trades"] == 1
    assert result["summary"]["total_realized_pnl"] == 650.0
    trade = result["trades"][0]
    assert trade["logic_trace"]["signal"]["direction"] == "BEARISH"
    assert trade["logic_trace"]["risk"]["approved"] is True
    assert trade["logic_trace"]["execution_plan"]["instrument"]["side"] == "PE"
    assert trade["persisted_decision_match"]["available"] is True


def test_paper_trade_audit_rejects_invalid_day():
    try:
        paper_trade_audit_api.paper_trade_audit("30-09-2026")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("invalid trading day should be rejected")
