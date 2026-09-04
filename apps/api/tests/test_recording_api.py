from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantnifty.recording_api import router


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
    assert response.json() == {
        "status": "NOT_CONFIGURED",
        "configured": False,
        "root": None,
        "bundles": 0,
    }
