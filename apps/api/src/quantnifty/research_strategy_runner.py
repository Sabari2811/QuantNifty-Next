from __future__ import annotations

from dataclasses import asdict
from typing import Any

from quantnifty.backtest import BacktestConfig, run_backtest

RESEARCH_STRATEGIES = ("directional", "gamma_blast", "adaptive", "early_accumulation", "transition", "range", "breakout_watch")


def run_research_strategy(snapshots: list[dict[str, Any]], strategy: str, config: BacktestConfig | None = None) -> dict[str, Any]:
    requested = str(strategy or "").strip().lower()
    if requested not in RESEARCH_STRATEGIES:
        raise ValueError(f"unsupported research strategy: {requested}")
    if requested in {"directional", "gamma_blast", "adaptive"}:
        return run_backtest(snapshots, requested, config)
    research_snapshots = []
    for snapshot in snapshots:
        row = dict(snapshot)
        row["_research_strategy"] = requested
        research_snapshots.append(row)
    result = run_backtest(research_snapshots, "adaptive", config)
    result = dict(result)
    result["strategy"] = requested
    result["research_strategy"] = requested
    result["canonical_engine_strategy"] = "adaptive"
    result["research_only"] = True
    result["orders_placed"] = 0
    result["trading_enabled"] = False
    result["strategy_execution_note"] = "Explicit research strategy is routed through the canonical Adaptive Brain/FinalDecision/Risk pipeline; live API remains restricted to adaptive, directional and gamma_blast."
    result["trades"] = [dict(trade, strategy=requested) for trade in result.get("trades") or []]
    return result
