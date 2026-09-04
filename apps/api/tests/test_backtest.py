from __future__ import annotations

from quantnifty.backtest import BacktestConfig, run_backtest, validation_report


def snap(ts: str, spot: float, option: float) -> dict:
    return {
        "timestamp": ts,
        "spot": spot,
        "bias": "BULLISH",
        "confidence": 80,
        "liquidity_score": 90,
        "data_integrity": "LIVE_PROVIDER",
        "option_chain": [{
            "strike": 25000, "side": "CE", "security_id": "CE1", "trading_symbol": "NIFTYCE",
            "last_price": option, "bid": option - 0.5, "ask": option + 0.5,
        }],
        "strike_selection": [{"strike": 25000, "side": "CE", "security_id": "CE1"}],
        "expected_move": {"move": 100, "lower": spot - 100, "upper": spot + 100},
        "gamma_flip": 24900,
        "gex": -100,
        "dex": 100,
        "atm_iv": 10,
        "iv_skew": 0,
        "dealer_flow": "PUT_SUPPORT",
        "rows": 20,
        "expiry": "2026-09-10",
        "intelligence": {"market_state": {"state": "TREND"}},
    }


def fake_decision(data, previous=None, strategy="directional"):
    return {
        "signal": {"direction": "BULLISH", "confidence": 80},
        "risk": {"approved": True},
        "execution_plan": {"instrument": {"strike": 25000, "side": "CE", "security_id": "CE1"}},
    }


def test_backtest_is_lookahead_free(monkeypatch):
    monkeypatch.setattr("quantnifty.backtest.final_decision", fake_decision)
    snapshots = [snap("2026-09-01T09:15:00+00:00", 25000, 100), snap("2026-09-01T09:16:00+00:00", 25020, 110), snap("2026-09-01T09:17:00+00:00", 25060, 130)]
    result = run_backtest(snapshots, config=BacktestConfig(lot_size=1, fixed_cost=0, slippage_bps=0, target_pct=0.01, stop_pct=0.01))
    assert result["lookahead_free"] is True
    assert result["orders_placed"] == 0
    assert result["metrics"]["trades"] == 1
    assert result["metrics"]["net_pnl"] == 20.0


def test_costs_reduce_net_pnl(monkeypatch):
    monkeypatch.setattr("quantnifty.backtest.final_decision", fake_decision)
    snapshots = [snap("2026-09-01T09:15:00+00:00", 25000, 100), snap("2026-09-01T09:16:00+00:00", 25020, 110), snap("2026-09-01T09:17:00+00:00", 25020, 110)]
    result = run_backtest(snapshots, config=BacktestConfig(lot_size=1, fixed_cost=10, slippage_bps=0))
    assert result["metrics"]["costs"] > 0
    assert result["metrics"]["net_pnl"] < result["metrics"]["gross_pnl"]


def test_validation_report_exposes_oos_and_gate_counts(monkeypatch):
    monkeypatch.setattr("quantnifty.backtest.final_decision", fake_decision)
    snapshots = [snap(f"2026-09-01T09:{15+i:02d}:00+00:00", 25000 + i * 5, 100 + i) for i in range(10)]
    report = validation_report(snapshots)
    assert report["research_only"] is True
    assert report["orders_placed"] == 0
    assert "oos" in report
    assert "risk_gate" in report
