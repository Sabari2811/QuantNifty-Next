from __future__ import annotations

from collections import Counter
from typing import Any

SCENARIO_SCHEMA = "adaptive-scenario-v1"


def classify_scenario(trade: dict[str, Any]) -> str:
    strategy = str(trade.get("strategy") or "").lower()
    exit_reason = str(trade.get("exit_reason") or "").upper()
    regime = str(trade.get("regime") or trade.get("market_regime") or "").upper()
    if exit_reason in {"ADAPTIVE_EXHAUSTION", "ADAPTIVE_TRAIL"}:
        return "EXHAUSTION_OR_PROFIT_LOCK"
    if strategy == "early_accumulation" or "EARLY_ACCUMULATION" in regime:
        return "ACCUMULATION_BREAKOUT"
    if strategy == "gamma_blast" or "GAMMA" in regime:
        return "GAMMA_BLAST"
    if "TRANSITION" in regime:
        return "GAMMA_TRANSITION"
    if "RANGE" in regime or strategy == "range":
        return "POSITIVE_GAMMA_RANGE"
    if "LIQUIDITY" in regime:
        return "LIQUIDITY_RISK"
    if "COMPRESSION" in regime or strategy == "breakout_watch":
        return "COMPRESSION_BREAKOUT_WATCH"
    if exit_reason in {"STOP", "ADAPTIVE_STOP"}:
        return "FAILED_DIRECTION"
    return "DIRECTIONAL"


def extract_scenarios(research: dict[str, Any]) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    counts = Counter()
    for strategy_name, result in (research.get("strategies") or {}).items():
        for trade in result.get("trades") or []:
            if not isinstance(trade, dict):
                continue
            scenario = classify_scenario({**trade, "strategy": trade.get("strategy") or strategy_name})
            counts[scenario] += 1
            scenarios.append({"schema": SCENARIO_SCHEMA, "scenario": scenario, "strategy": strategy_name, "direction": trade.get("direction"), "net_pnl": trade.get("net_pnl"), "exit_reason": trade.get("exit_reason"), "timestamp": trade.get("timestamp"), "counterfactual": True})
    return {"schema": SCENARIO_SCHEMA, "day": research.get("day"), "status": "COMPLETED", "counterfactual": True, "scenario_counts": dict(counts), "scenarios": scenarios}
