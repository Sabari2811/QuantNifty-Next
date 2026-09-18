from __future__ import annotations

from quantnifty.adaptive_policy import ANCHOR_STRATEGY
from quantnifty.backtest import BacktestConfig
from quantnifty.learning_store import load_snapshots, load_events, record_research
from quantnifty.policy_runtime import validate_and_persist
from quantnifty.research_strategy_runner import RESEARCH_STRATEGIES, run_research_strategy
from quantnifty.scenario_engine import extract_scenarios
from quantnifty.trade_learning import analyze_trade_lesson, summarize_trade_lessons

STRATEGIES = ("directional", "gamma_blast", "adaptive")


def run_after_market_lab(day: str, config: BacktestConfig | None = None) -> dict[str, object]:
    """Run an independent counterfactual test on today's raw market dataset.

    This function intentionally loads only raw snapshots. It does not load,
    inspect, score, or rewrite live decisions, paper trades, or live outcomes.
    The resulting P&L is a separate post-market learning track.
    """
    snapshots = load_snapshots(day)
    if not snapshots:
        return {"status": "NO_DATA", "day": day, "strategies": {}, "orders_placed": 0, "track": "POST_MARKET", "input_dataset": "RAW_MARKET_SNAPSHOTS"}
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
                "counterfactual": True,
            }
        except (TypeError, ValueError, RuntimeError) as exc:
            results[strategy] = {"status": "ERROR", "error": str(exc), "research_only": True, "counterfactual": True}
    tested_metrics = {name: value.get("metrics") or {} for name, value in results.items() if value.get("status") == "TESTED"}
    ranked = sorted(((float((metric.get("net_pnl") or 0.0)), name) for name, metric in tested_metrics.items()), reverse=True)
    research = {
        "type": "after_market",
        "training_type": "DAILY_AFTER_MARKET",
        "training_source": "STORED_DAY",
        "track": "POST_MARKET",
        "input_dataset": "RAW_MARKET_SNAPSHOTS",
        "status": "COMPLETED",
        "day": day,
        "observations": len(snapshots),
        "strategies": results,
        "strategy_coverage": {"tested": list(RESEARCH_STRATEGIES), "pending": []},
        "ranking_by_net_pnl": [{"strategy": name, "net_pnl": round(pnl, 2)} for pnl, name in ranked],
        "orders_placed": 0,
        "mode": "READ_ONLY_AFTER_MARKET",
        "research_only": True,
        "counterfactual": True,
        "live_trade_data_accessed": False,
        "live_decision_data_accessed": False,
        "live_outcome_data_accessed": True,
        "live_outcome_access_mode": "CLOSED_PAPER_ONLY_AFTER_MARKET",
    }
    research["scenarios"] = extract_scenarios(research)
    closed_outcomes = []
    for event in load_events("outcomes", day):
        outcome = event.get("outcome") if isinstance(event, dict) else None
        if isinstance(outcome, dict) and str(outcome.get("status") or outcome.get("lifecycle") or "").upper() == "CLOSED":
            closed_outcomes.append(outcome)
    lessons = [analyze_trade_lesson(outcome) for outcome in closed_outcomes]
    research["trade_learning"] = summarize_trade_lessons(lessons)
    anchor_metrics = results.get(ANCHOR_STRATEGY, {}).get("metrics") or {}
    candidate_metrics = {name: value.get("metrics") or {} for name, value in results.items() if name != ANCHOR_STRATEGY and value.get("status") == "TESTED"}
    policy_event = validate_and_persist(day, "DAY_AGGREGATE", anchor_metrics, candidate_metrics)
    research["policy"] = policy_event.get("research") if isinstance(policy_event, dict) else policy_event
    record_research(research)
    return research


def latest_research(day: str | None = None) -> list[dict[str, object]]:
    from quantnifty.learning_store import load_events
    return load_events("research", day)
