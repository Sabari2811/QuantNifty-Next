from __future__ import annotations

from quantnifty.after_market_lab import run_after_market_lab


def test_after_market_lab_requires_recorded_day(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTNIFTY_LEARNING_ROOT", str(tmp_path))
    result = run_after_market_lab("2026-09-07")
    assert result["status"] == "NO_DATA"
    assert result["orders_placed"] == 0


def test_after_market_strategy_contract_is_explicit():
    from quantnifty.after_market_lab import RESEARCH_STRATEGIES, STRATEGIES
    assert set(STRATEGIES) == {"directional", "gamma_blast", "adaptive"}
    assert set(STRATEGIES).issubset(set(RESEARCH_STRATEGIES))


def test_after_market_persists_complete_training_record(monkeypatch):
    from quantnifty.after_market_lab import RESEARCH_STRATEGIES

    snapshots = [{"timestamp": "2026-09-07T10:00:00+00:00", "spot": 25000}]
    saved = []

    monkeypatch.setattr("quantnifty.after_market_lab.load_snapshots", lambda day: snapshots)
    monkeypatch.setattr(
        "quantnifty.after_market_lab.run_research_strategy",
        lambda snapshots, strategy, cfg: {"metrics": {"net_pnl": 10}, "trades": [], "split": {}, "canonical_engine_strategy": "adaptive"},
    )
    monkeypatch.setattr("quantnifty.after_market_lab.extract_scenarios", lambda research: {"schema_version": "adaptive-scenario-v1", "counts": {}})
    monkeypatch.setattr(
        "quantnifty.after_market_lab.validate_and_persist",
        lambda *args: {"research": {"policy_id": "policy-test", "future_safe": True}},
    )
    monkeypatch.setattr("quantnifty.after_market_lab.record_research", lambda research: saved.append(research))

    result = run_after_market_lab("2026-09-07")

    assert result["status"] == "COMPLETED"
    assert result["training_type"] == "DAILY_AFTER_MARKET"
    assert result["training_source"] == "STORED_DAY"
    assert set(result["strategies"]) == set(RESEARCH_STRATEGIES)
    assert result["policy"]["policy_id"] == "policy-test"
    assert result["scenarios"]["schema_version"] == "adaptive-scenario-v1"
    assert saved == [result]
