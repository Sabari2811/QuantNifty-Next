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
