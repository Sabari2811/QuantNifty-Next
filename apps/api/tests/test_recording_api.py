from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantnifty.recording_api import _validated_result, router


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
    result = _validated_result([], "directional", object(), "UPLOADED_RECORDED_HISTORICAL", "ephemeral-upload")
    assert result["observations"] == 23
    assert result["approved"] == 7
    assert result["blocked"] == 16
    assert result["split"]["out_of_sample"]["net_pnl"] == 42.0
    assert result["empirical"] is True
