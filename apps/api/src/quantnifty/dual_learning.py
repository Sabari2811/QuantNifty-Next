from __future__ import annotations

from collections import defaultdict
from typing import Any


LIVE = "LIVE_MARKET"
POST = "POST_MARKET"


def _pnl(result: dict[str, Any]) -> float:
    metrics = result.get("metrics") or {}
    try:
        return float(metrics.get("net_pnl") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def summarize_live_and_post_market(
    live_outcomes: list[dict[str, Any]],
    post_market_research: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a deterministic, read-only comparison of the two learning tracks.

    Live outcomes describe what the live paper Brain actually did. Post-market
    research is counterfactual: every configured strategy is evaluated against
    the day's raw market snapshots independently of live decisions/outcomes.
    """
    live: dict[str, dict[str, Any]] = defaultdict(lambda: {"trades": 0, "net_pnl": 0.0})
    for outcome in live_outcomes:
        strategy = str(outcome.get("strategy") or outcome.get("decision_strategy") or "unknown")
        pnl = outcome.get("net_pnl", outcome.get("pnl", 0.0))
        try:
            pnl = float(pnl or 0.0)
        except (TypeError, ValueError):
            pnl = 0.0
        live[strategy]["trades"] += 1
        live[strategy]["net_pnl"] += pnl

    post: dict[str, dict[str, Any]] = {}
    for strategy, result in (post_market_research or {}).get("strategies", {}).items():
        if result.get("status") != "TESTED":
            continue
        post[str(strategy)] = {
            "trades": int((result.get("metrics") or {}).get("trades") or len(result.get("trades") or [])),
            "net_pnl": _pnl(result),
        }

    strategies = sorted(set(live) | set(post))
    comparison = []
    for strategy in strategies:
        lp = live.get(strategy, {}).get("net_pnl", 0.0)
        pp = post.get(strategy, {}).get("net_pnl", 0.0)
        comparison.append({
            "strategy": strategy,
            "live": {**live.get(strategy, {"trades": 0, "net_pnl": 0.0}), "net_pnl": round(lp, 2)},
            "post_market": {**post.get(strategy, {"trades": 0, "net_pnl": 0.0}), "net_pnl": round(pp, 2)},
            "combined_pnl": round(lp + pp, 2),
            "live_profitable": lp > 0,
            "post_market_profitable": pp > 0,
        })

    combined_rank = sorted(comparison, key=lambda x: (x["combined_pnl"], x["post_market"]["net_pnl"], x["live"]["net_pnl"], x["strategy"]), reverse=True)
    return {
        "schema_version": "dual-learning-v1",
        "live_track": {"source": LIVE, "independent_from_post_market": True, "strategies": dict(live)},
        "post_market_track": {"source": POST, "counterfactual": True, "independent_from_live_trades": True, "strategies": post},
        "comparison": comparison,
        "ranked_for_future_adaptation": [x["strategy"] for x in combined_rank],
        "profitable_strategies": [x["strategy"] for x in combined_rank if x["combined_pnl"] > 0],
        "negative_strategies": [x["strategy"] for x in combined_rank if x["combined_pnl"] < 0],
        "read_only": True,
    }
