from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantnifty.recording_api import _observation_diagnostics, _replay_diagnostics, _validated_result, router


def test_backtest_html_compatibility_route():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/backtest.html", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/backtest"


def test_recording_status_is_explicit_when_not_configured(monkeypatch):
    monkeypatch.delenv("QUANTNIFTY_RECORDING_ROOT", raising=False)
    monkeypatch.delenv("RECORDING_ROOT", raising=False)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/api/v1/recording/status")
    assert response.status_code == 200
    assert response.json() == {"status": "NOT_CONFIGURED", "configured": False, "root": None, "bundles": 0}


def test_replay_diagnostics_preserve_authoritative_gate_reasons(monkeypatch):
    decisions = [
        {"signal": {"direction": "NEUTRAL", "confidence": 50}, "risk": {"approved": False, "reasons": ["direction", "confidence"]}},
        {"signal": {"direction": "BULLISH", "confidence": 70}, "risk": {"approved": True, "reasons": []}},
    ]
    monkeypatch.setattr("quantnifty.recording_api.final_decision", lambda *args: decisions.pop(0))
    monkeypatch.setattr("quantnifty.recording_api._is_market_session", lambda snapshot: True)
    snapshots = [
        {"recorded_analytics": {"signal": {"signal": "BUY CALL"}}, "recorded_decision": {"signal": {"name": "WAIT"}, "validation": {"valid": False}}},
        {"recorded_analytics": {"signal": {"signal": "BUY PUT"}}, "recorded_decision": {"signal": {"name": "BUY PUT"}, "validation": {"valid": True}}},
        {"recorded_analytics": {"signal": {"signal": "WAIT"}}, "recorded_decision": {"signal": {"name": "WAIT"}, "validation": {"valid": False}}},
    ]
    result = _replay_diagnostics(snapshots, "directional")
    assert result["decision_observations"] == 2
    assert result["approved"] == 1
    assert result["blocked"] == 1
    assert result["blocked_by_reason"] == {"confidence": 1, "direction": 1}
    assert result["replay_signal_distribution"] == {"BULLISH": 1, "NEUTRAL": 1}
    assert result["recorded_signal_distribution"] == {"BEARISH": 1, "BULLISH": 1}
    assert result["recorded_decision_distribution"] == {"BUY PUT": 1, "WAIT": 1}
    assert result["recorded_validation_distribution"] == {"INVALID": 1, "VALID": 1}
    assert result["replay_confidence"] == {"min": 50.0, "max": 70.0, "avg": 60.0}


def test_observation_diagnostics_explain_each_authoritative_gate(monkeypatch):
    decisions = [
        {"signal": {"direction": "NEUTRAL", "confidence": 50, "scores": {"NEUTRAL": 10}, "evidence": ["mixed"]}, "risk": {"approved": False, "gates": {"direction": False, "confidence": False}, "reasons": ["direction", "confidence"]}, "execution_plan": {"status": "BLOCKED", "instrument": None, "execution_enabled": False}},
        {"signal": {"direction": "BULLISH", "confidence": 75, "scores": {"BULLISH": 55}, "evidence": ["probability"]}, "risk": {"approved": True, "gates": {"direction": True, "confidence": True}, "reasons": []}, "execution_plan": {"status": "APPROVED_READ_ONLY", "instrument": {"strike": 24500, "side": "CE"}, "execution_enabled": False}},
    ]
    monkeypatch.setattr("quantnifty.recording_api.final_decision", lambda *args: decisions.pop(0))
    monkeypatch.setattr("quantnifty.recording_api._is_market_session", lambda snapshot: True)
    snapshots = [
        {"timestamp": "2026-08-03T12:00:00+05:30", "spot": 24500, "recorded_analytics": {"signal": {"signal": "WAIT", "confidence": 10}}, "recorded_decision": {}},
        {"timestamp": "2026-08-03T12:05:00+05:30", "spot": 24510, "recorded_analytics": {"signal": {"signal": "BUY CALL", "confidence": 70}, "strike_selection": [{"strike": 24500, "side": "CE"}]}, "recorded_decision": {}},
        {"timestamp": "2026-08-03T12:10:00+05:30", "spot": 24520, "recorded_analytics": {}, "recorded_decision": {}},
    ]
    rows = _observation_diagnostics(snapshots, "directional")
    assert len(rows) == 2
    assert rows[0]["risk"]["approved"] is False
    assert rows[0]["risk"]["blocked_reasons"] == ["direction", "confidence"]
    assert rows[0]["execution"]["execution_enabled"] is False
    assert rows[1]["risk"]["approved"] is True
    assert rows[1]["execution"]["instrument"]["strike"] == 24500
    assert rows[1]["recorded"]["direction"] == "BULLISH"
    assert rows[1]["recorded"]["strike_selection"][0]["strike"] == 24500


def test_validated_result_does_not_call_zero_trade_run_performance_validated(monkeypatch):
    monkeypatch.setattr(
        "quantnifty.recording_api.validation_report",
        lambda snapshots, strategy, config: {
            "status": "OK",
            "strategy": strategy,
            "lookahead_free": True,
            "historical_data": {"status": "VALID_HISTORICAL"},
            "oos": {"observations": 3, "trades": 0, "net_pnl": 0.0, "win_rate_pct": 0.0},
            "overall": {"observations": 23, "trades": 0, "net_pnl": 0.0},
            "risk_gate": {"approved": 0, "blocked": 22},
            "signal_quality": {},
            "regimes": {},
            "session_filter": {"observations": 23},
            "research_only": True,
            "orders_placed": 0,
        },
    )
    monkeypatch.setattr("quantnifty.recording_api._replay_diagnostics", lambda snapshots, strategy: {"approved": 0, "blocked": 22})
    result = _validated_result([], "directional", object(), "UPLOADED_RECORDED_HISTORICAL", "ephemeral-upload")
    assert result["empirical"] is False
    assert result["tradeability"] == "NO_EXECUTABLE_TRADES"
    assert result["empirical_status"] == "NO_EXECUTABLE_TRADES"
    assert result["performance_status"] == "NOT_VALIDATED"


def test_validated_result_exposes_ui_compatibility_fields(monkeypatch):
    monkeypatch.setattr(
        "quantnifty.recording_api.validation_report",
        lambda snapshots, strategy, config: {
            "status": "OK",
            "strategy": strategy,
            "lookahead_free": True,
            "historical_data": {"status": "VALID_HISTORICAL"},
            "oos": {"observations": 3, "trades": 1, "net_pnl": 42.0, "win_rate_pct": 100.0},
            "overall": {"observations": 23, "trades": 5, "net_pnl": 100.0},
            "risk_gate": {"approved": 7, "blocked": 16},
            "signal_quality": {},
            "regimes": {},
            "session_filter": {"observations": 23},
            "research_only": True,
            "orders_placed": 0,
        },
    )
    monkeypatch.setattr("quantnifty.recording_api._replay_diagnostics", lambda snapshots, strategy: {"approved": 7, "blocked": 16})
    result = _validated_result([], "directional", object(), "UPLOADED_RECORDED_HISTORICAL", "ephemeral-upload")
    assert result["observations"] == 23
    assert result["approved"] == 7
    assert result["blocked"] == 16
    assert result["split"]["out_of_sample"]["net_pnl"] == 42.0
    assert result["empirical"] is True
    assert result["tradeability"] == "TRADEABLE_SAMPLE"
    assert result["empirical_status"] == "EMPIRICAL_TRADES"
    assert result["performance_status"] == "PERFORMANCE_VALIDATED"
