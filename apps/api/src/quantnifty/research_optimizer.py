from __future__ import annotations

from itertools import product
from typing import Any, Callable, Iterable

from quantnifty.research_analytics import robustness_gate


def parameter_grid(spec: dict[str, Iterable[Any]]) -> list[dict[str, Any]]:
    """Build deterministic research-only parameter candidates."""
    if not spec:
        return [{}]
    keys = list(spec)
    values = [list(spec[k]) for k in keys]
    return [dict(zip(keys, combo)) for combo in product(*values)]


def rank_candidates(results: Iterable[dict[str, Any]], *, min_oos_trades: int = 30) -> list[dict[str, Any]]:
    """Rank by OOS expectancy/profit factor, not win rate."""
    ranked = []
    for result in results:
        row = dict(result)
        oos = row.get("out_of_sample") or row.get("oos") or {}
        row["robustness_gate"] = robustness_gate(oos, min_trades=min_oos_trades)
        ranked.append(row)
    ranked.sort(key=lambda r: (
        bool((r.get("robustness_gate") or {}).get("passed")),
        float((r.get("out_of_sample") or r.get("oos") or {}).get("profit_factor") or 0),
        float((r.get("out_of_sample") or r.get("oos") or {}).get("expectancy_per_trade", (r.get("out_of_sample") or r.get("oos") or {}).get("expectancy", 0)) or 0),
        -float((r.get("out_of_sample") or r.get("oos") or {}).get("max_drawdown_pct") or 0),
    ), reverse=True)
    return ranked


def optimize_candidates(candidates: Iterable[dict[str, Any]], evaluator: Callable[[dict[str, Any]], dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate candidates in supplied order; caller decides data split.

    This function deliberately performs no live-data calls and cannot mutate
    trading configuration. It is intended for offline research/walk-forward runs.
    """
    results = []
    for params in candidates:
        outcome = dict(evaluator(dict(params)))
        outcome["parameters"] = dict(params)
        results.append(outcome)
    return rank_candidates(results)
