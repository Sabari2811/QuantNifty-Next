from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.adaptive_policy import ANCHOR_STRATEGY
from quantnifty.backtest import BacktestConfig
from quantnifty.learning_store import load_snapshots, record_research
from quantnifty.policy_runtime import validate_and_persist
from quantnifty.research_strategy_runner import RESEARCH_STRATEGIES, run_research_strategy
from quantnifty.scenario_engine import extract_scenarios

IST = ZoneInfo("Asia/Kolkata")


def run_after_market_lab(day: str, config: BacktestConfig | None = None) -> dict[str, Any]:
    snapshots = load_snapshots(day)
    if not snapshots:
        return {"status": "NO_DATA", "day": day, "strategies": {}, "orders_placed": 0}
    cfg = config or BacktestConfig()
    results: dict[str, Any] = {}
    for strategy in RESEARCH_STRATEGIES:
        try:
            result = run_research_strategy(snapshots, strategy, cfg)
            results[strategy] = {"status": "TESTED", "metrics": result.get("metrics") or result.get("overall") or {}, "trades": result.get("trades") or [], "split": result.get("split") or {}, "strategy": strategy, "canonical_engine_strategy": result.get("canonical_engine_strategy", strategy), "research_only": True}
        except (TypeError, ValueError, RuntimeError) as exc:
            results[strategy] = {"status": "ERROR", "error": str(exc), "research_only": True}
    tested_metrics = {name: value.get("metrics") or {} for name, value in results.items() if value.get("status") == "TESTED"}
    ranked = sorted(((float((metric.get("net_pnl") or 0.0)), name) for name, metric in tested_metrics.items()), reverse=True)
    research = {"type": "after_market", "status": "COMPLETED", "day": day, "observations": len(snapshots), "strategies": results, "strategy_coverage": {"tested": list(RESEARCH_STRATEGIES), "pending": []}, "ranking_by_net_pnl": [{"strategy": name, "net_pnl": round(pnl, 2)} for pnl, name in ranked], "orders_placed": 0, "mode": "READ_ONLY_AFTER_MARKET", "counterfactual": True}
    scenarios = extract_scenarios(research)
    research["scenarios"] = scenarios
    record_research(research)
    anchor_metrics = results.get(ANCHOR_STRATEGY, {}).get("metrics") or {}
    candidate_metrics = {name: value.get("metrics") or {} for name, value in results.items() if name != ANCHOR_STRATEGY and value.get("status") == "TESTED"}
    policy_event = validate_and_persist(day, "DAY_AGGREGATE", anchor_metrics, candidate_metrics)
    research["policy"] = policy_event.get("research") if isinstance(policy_event, dict) else policy_event
    return research


def latest_research(day: str | None = None) -> list[dict[str, Any]]:
    from quantnifty.learning_store import load_events
    return load_events("research", day)
