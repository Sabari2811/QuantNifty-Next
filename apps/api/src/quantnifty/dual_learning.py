from __future__ import annotations

from collections import defaultdict
from typing import Any

LIVE = "LIVE_MARKET"
POST = "POST_MARKET"


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def summarize_live_and_post_market(live_outcomes: list[dict[str, Any]], post_market_research: dict[str, Any] | None) -> dict[str, Any]:
    """Compare two already-produced tracks without mixing their inputs."""
    live: dict[str, dict[str, Any]] = defaultdict(lambda: {"trades": 0, "net_pnl": 0.0})
    for outcome in live_outcomes:
        strategy = str(outcome.get("strategy") or outcome.get("decision_strategy") or "unknown")
        live[strategy]["trades"] += 1
        live[strategy]["net_pnl"] += _number(outcome.get("net_pnl", outcome.get("pnl", 0.0)))
    post: dict[str, dict[str, Any]] = {}
    for strategy, result in (post_market_research or {}).get("strategies", {}).items():
        if result.get("status") != "TESTED":
            continue
        metrics = result.get("metrics") or {}
        post[str(strategy)] = {"trades": int(_number(metrics.get("trades")) or len(result.get("trades") or [])), "net_pnl": _number(metrics.get("net_pnl"))}
    comparison = []
    for strategy in sorted(set(live) | set(post)):
        lv = live.get(strategy, {"trades": 0, "net_pnl": 0.0})
        pv = post.get(strategy, {"trades": 0, "net_pnl": 0.0})
        comparison.append({"strategy": strategy, "live": {"trades": lv["trades"], "net_pnl": round(lv["net_pnl"], 2)}, "post_market": {"trades": pv["trades"], "net_pnl": round(pv["net_pnl"], 2)}, "combined_pnl": round(lv["net_pnl"] + pv["net_pnl"], 2), "live_profitable": lv["net_pnl"] > 0, "post_market_profitable": pv["net_pnl"] > 0})
    ranked = sorted(comparison, key=lambda x: (x["combined_pnl"], x["post_market"]["net_pnl"], x["live"]["net_pnl"], x["strategy"]), reverse=True)
    return {"schema_version": "dual-learning-v1", "live_track": {"source": LIVE, "independent_from_post_market": True, "strategies": dict(live)}, "post_market_track": {"source": POST, "counterfactual": True, "independent_from_live_trades": True, "strategies": post}, "comparison": comparison, "ranked_for_future_adaptation": [x["strategy"] for x in ranked], "profitable_strategies": [x["strategy"] for x in ranked if x["combined_pnl"] > 0], "negative_strategies": [x["strategy"] for x in ranked if x["combined_pnl"] < 0], "read_only": True}
