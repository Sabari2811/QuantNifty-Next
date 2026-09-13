from __future__ import annotations

from pathlib import Path

from quantnifty.backtest import BacktestConfig
from quantnifty.external_options_loader import load_option_csv
from quantnifty.position_hold_backtest import run_position_hold_backtest
from quantnifty.research_analytics import cost_sensitivity, robustness_gate, trade_diagnostics, walk_forward_splits
from quantnifty.research_optimizer import optimize_candidates, parameter_grid, rank_candidates

FIXTURE = Path(__file__).parent / "fixtures_external_options_v3.csv"


def test_external_options_fixture_is_canonical_and_expiry_safe():
    snapshots = load_option_csv(FIXTURE)
    assert len(snapshots) == 3
    assert all(snapshot["data_integrity"] == "RECORDED_HISTORICAL" for snapshot in snapshots)
    assert all(snapshot["expiry"] == "2026-08-04" for snapshot in snapshots)
    assert all(snapshot["spot"] > 0 for snapshot in snapshots)
    assert all(len(snapshot["option_chain"]) == 2 for snapshot in snapshots)


def test_v3_thesis_hold_lifecycle_produces_real_option_pnl(monkeypatch):
    def approved_decision(snapshot, previous=None, strategy="directional", mode="BACKTEST"):
        return {
            "status": "TRADE",
            "authoritative": True,
            "trading": False,
            "signal": {"direction": "BULLISH", "confidence": 85, "adaptive": {"selected_strategy": "directional"}},
            "risk": {"approved": True},
            "execution_plan": {"instrument": {"security_id": "HIST:CE", "strike": 24500, "side": "CE"}},
        }

    monkeypatch.setattr("quantnifty.position_hold_backtest.final_decision", approved_decision)
    monkeypatch.setattr("quantnifty.position_hold_backtest._thesis_still_valid", lambda *args, **kwargs: True)

    def snapshot(ts, spot, premium):
        return {
            "timestamp": ts,
            "spot": spot,
            "expiry": "2026-08-04",
            "atm_iv": 14,
            "data_integrity": "RECORDED_HISTORICAL",
            "option_chain": [
                {"security_id": "HIST:CE", "strike": 24500, "side": "CE", "last_price": premium, "bid": premium - 0.5, "ask": premium + 0.5, "oi": 5000, "volume": 1000},
                {"security_id": "HIST:PE", "strike": 24500, "side": "PE", "last_price": 100, "bid": 99.5, "ask": 100.5, "oi": 5000, "volume": 1000},
            ],
        }

    snapshots = [
        snapshot("2026-08-04T09:15:00+05:30", 25000, 100),
        snapshot("2026-08-04T09:16:00+05:30", 25020, 105),
        snapshot("2026-08-04T09:17:00+05:30", 25040, 120),
        snapshot("2026-08-04T09:18:00+05:30", 25180, 180),
    ]
    result = run_position_hold_backtest(
        snapshots,
        "directional",
        BacktestConfig(initial_capital=100000, lot_size=65, slippage_bps=0, fixed_cost=0),
    )

    assert result["status"] == "OK"
    assert result["orders_placed"] == 0
    assert result["trading_enabled"] is False
    assert result["position_lifecycle_metrics"]["positions_opened"] == 1
    assert result["trades"][0]["reason"] == "POINT_TARGET"
    assert result["trades"][0]["entry_price"] == 105
    assert result["trades"][0]["exit_price"] == 180
    assert result["trades"][0]["net_pnl"] == 75 * 65


def test_research_robustness_and_cost_sensitivity_are_deterministic():
    trades = [
        {"net_pnl": 100, "regime": "TREND_UP", "direction": "BULLISH", "entry_timestamp": "2026-08-04T09:30:00+05:30", "exit_reason": "POINT_TARGET"},
        {"net_pnl": -50, "regime": "TREND_UP", "direction": "BULLISH", "entry_timestamp": "2026-08-04T10:00:00+05:30", "exit_reason": "POINT_STOP"},
        {"net_pnl": 120, "regime": "TREND_DOWN", "direction": "BEARISH", "entry_timestamp": "2026-08-04T11:00:00+05:30", "exit_reason": "POINT_TARGET"},
    ]
    diagnostics = trade_diagnostics(trades, [])
    assert diagnostics["overall"]["trades"] == 3
    assert diagnostics["by_direction"]["BULLISH"]["trades"] == 2

    metrics = {"trades": 40, "profit_factor": 1.30, "max_drawdown_pct": 10, "expectancy": 25}
    gate = robustness_gate(metrics)
    assert gate["passed"] is True
    sensitivity = cost_sensitivity(metrics, [0, 5, 10])
    assert len(sensitivity) == 3
    assert sensitivity[0]["profit_factor"] >= sensitivity[-1]["profit_factor"]


def test_walk_forward_and_optimizer_are_chronological_and_oos_first():
    observations = [{"timestamp": f"2026-08-04T09:{15 + i:02d}:00+05:30", "value": i} for i in range(10)]
    splits = walk_forward_splits(observations, train_fraction=0.6, validation_fraction=0.2, min_train=3)
    assert splits["train"][0]["value"] == 0
    assert splits["validation"][0]["value"] == 6
    assert splits["oos"][0]["value"] == 8

    grid = parameter_grid({"stop": [50, 75], "target": [100, 150]})
    assert len(grid) == 4
    results = [
        {"id": "weak", "oos": {"trades": 40, "profit_factor": 1.10, "expectancy": 10, "max_drawdown_pct": 5}},
        {"id": "strong", "oos": {"trades": 40, "profit_factor": 1.30, "expectancy": 20, "max_drawdown_pct": 8}},
    ]
    ranked = rank_candidates(results)
    assert ranked[0]["id"] == "strong"
    optimized = optimize_candidates([{"id": "a"}, {"id": "b"}], lambda candidate: {"candidate": candidate, "score": 2 if candidate["id"] == "b" else 1})
    assert optimized[0]["candidate"]["id"] == "b"
