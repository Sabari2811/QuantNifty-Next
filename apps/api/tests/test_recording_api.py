from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantnifty.recording_api import _replay_diagnostics, _validated_result, router


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
