from __future__ import annotations

from quantnifty.adaptive_policy import ANCHOR_STRATEGY
from quantnifty.backtest import BacktestConfig
from quantnifty.learning_store import load_snapshots, record_research
from quantnifty.policy_runtime import validate_and_persist
from quantnifty.research_strategy_runner import RESEARCH_STRATEGIES, run_research_strategy
from quantnifty.scenario_engine import extract_scenarios

# Backward-compatible name retained for existing tests/UI integrations.
STRATEGIES = ("directional", "gamma_blast", "adaptive")


def run_after_market_lab(day: str, config: BacktestConfig | None = None) -> dict[str, object]:
    snapshots = load_snapshots(day)
    if not snapshots:
        return {"status": "NO_DATA", "day": day, "strategies": {}, "orders_placed": 0}
    cfg = config or BacktestConfig()
    results: dict[str, object] = {}
    for strategy in RESEARCH_STRATEGIES:
        try:
            result = run_research_strategy(snapshots, strategy, cfg)
            results[strategy] = {
                "status": "TESTED",
                "metrics": result.get("metrics") or result.get("overall") or {},
                "trades": result.get("trades") or [],
                "split": result.get("split") or {},
                "strategy": strategy,
                "canonical_engine_strategy": result.get("canonical_engine_strategy", strategy),
                "position_lifecycle": result.get("position_lifecycle"),
                "risk_model": result.get("risk_model"),
                "risk_model_detail": result.get("risk_model_detail"),
                "entry_rule": result.get("entry_rule"),
                "exit_rule": result.get("exit_rule"),
                "research_only": True,
            }
        except (TypeError, ValueError, RuntimeError) as exc:
            results[strategy] = {"status": "ERROR", "error": str(exc), "research_only": True}
    tested_metrics = {name: value.get("metrics") or {} for name, value in results.items() if value.get("status") == "TESTED"}
    ranked = sorted(((float((metric.get("net_pnl") or 0.0)), name) for name, metric in tested_metrics.items()), reverse=True)
    research = {"type": "after_market", "training_type": "DAILY_AFTER_MARKET", "training_source": "STORED_DAY", "status": "COMPLETED", "day": day, "observations": len(snapshots), "strategies": results, "strategy_coverage": {"tested": list(RESEARCH_STRATEGIES), "pending": []}, "ranking_by_net_pnl": [{"strategy": name, "net_pnl": round(pnl, 2)} for pnl, name in ranked], "orders_placed": 0, "mode": "READ_ONLY_AFTER_MARKET", "counterfactual": False}
    research["scenarios"] = extract_scenarios(research)
    anchor_metrics = results.get(ANCHOR_STRATEGY, {}).get("metrics") or {}
    candidate_metrics = {name: value.get("metrics") or {} for name, value in results.items() if name != ANCHOR_STRATEGY and value.get("status") == "TESTED"}
    policy_event = validate_and_persist(day, "DAY_AGGREGATE", anchor_metrics, candidate_metrics)
    research["policy"] = policy_event.get("research") if isinstance(policy_event, dict) else policy_event
    # Persist only after policy/scenario enrichment so the durable daily
    # training event is a complete record of the post-market run.
    record_research(research)
    return research


def latest_research(day: str | None = None) -> list[dict[str, object]]:
    from quantnifty.learning_store import load_events
    return load_events("research", day)
