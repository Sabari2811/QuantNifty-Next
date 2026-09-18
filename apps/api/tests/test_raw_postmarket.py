from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantnifty.research_api import router


def test_raw_post_market_backtest_endpoint_is_read_only(monkeypatch):
    monkeypatch.setattr(
        "quantnifty.research_api.run_after_market_lab",
        lambda day: {
            "status": "COMPLETED",
            "day": day,
            "training_source": "STORED_DAY",
            "input_dataset": "RAW_MARKET_SNAPSHOTS",
            "observations": 120,
            "raw_data_test": {
                "status": "ENABLED",
                "source": "LEARNING_STORE_SNAPSHOTS",
                "provenance": "LIVE_PROVIDER",
                "lookahead_free": True,
                "strategies": ["directional", "gamma_blast", "adaptive"],
                "observations": 120,
                "research_only": True,
                "orders_placed": 0,
            },
            "strategies": {},
            "strategy_coverage": {"tested": ["directional", "gamma_blast", "adaptive"]},
            "ranking_by_net_pnl": [],
            "trade_learning": {"observations": 1},
            "policy": {},
        },
    )
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post("/api/v1/research/raw-backtest?day=2026-09-18")
    assert response.status_code == 200
    body = response.json()
    assert body["input_dataset"] == "RAW_MARKET_SNAPSHOTS"
    assert body["raw_data_test"]["status"] == "ENABLED"
    assert body["raw_data_test"]["provenance"] == "LIVE_PROVIDER"
    assert body["raw_data_test"]["lookahead_free"] is True
    assert body["orders_placed"] == 0
    assert body["research_only"] is True


def test_raw_post_market_backtest_rejects_invalid_day():
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post("/api/v1/research/raw-backtest?day=18-09-2026")
    assert response.status_code == 400
