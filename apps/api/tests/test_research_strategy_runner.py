from __future__ import annotations

from quantnifty.backtest import BacktestConfig
from quantnifty.research_strategy_runner import TUNED_CONFIG, _scenario_filter, run_research_strategy


def test_tuned_research_profile_uses_full_lot_and_intraday_risk():
    assert TUNED_CONFIG.lot_size == 65
    assert TUNED_CONFIG.max_hold_bars == 8
    assert TUNED_CONFIG.stop_pct == 0.0075
    assert TUNED_CONFIG.target_pct == 0.015


def test_scenario_filter_does_not_relabel_full_adaptive_stream():
    snapshots = [
        {"timestamp": "2026-09-11T03:50:00+00:00", "spot": 25000, "liquidity_score": 80, "gex": 100, "bias": "NEUTRAL", "expected_move": {"move": 100}},
        {"timestamp": "2026-09-11T04:00:00+00:00", "spot": 25010, "liquidity_score": 80, "gex": -100, "bias": "NEUTRAL", "expected_move": {"move": 100}},
    ]
    filtered = _scenario_filter(snapshots, "transition")
    assert isinstance(filtered, list)
    assert len(filtered) <= len(snapshots)


def test_legacy_default_config_is_replaced_by_tuned_profile(monkeypatch):
    captured = {}

    def fake_run(snapshots, strategy, config):
        captured["strategy"] = strategy
        captured["config"] = config
        return {"metrics": {}, "trades": [], "split": {}}

    monkeypatch.setattr("quantnifty.research_strategy_runner.run_backtest", fake_run)
    result = run_research_strategy([], "adaptive", BacktestConfig())
    assert result["research_only"] is True
    assert captured["config"] == TUNED_CONFIG
    assert captured["config"].lot_size == 65
