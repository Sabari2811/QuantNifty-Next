from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.backtest import BacktestConfig, run_backtest
from quantnifty.learning_store import load_snapshots, record_research

IST = ZoneInfo("Asia/Kolkata")
STRATEGIES = ("directional", "gamma_blast", "adaptive")
RESEARCH_STRATEGIES = ("directional", "gamma_blast", "adaptive", "early_accumulation", "transition", "range", "breakout_watch")


def _day(snapshot: dict[str, Any]) -> str | None:
    raw = str(snapshot.get("timestamp") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(IST).date().isoformat()
    except ValueError:
        return raw[:10] or None


def run_after_market_lab(day: str, config: BacktestConfig | None = None) -> dict[str, Any]:
    snapshots = load_snapshots(day)
    if not snapshots:
        return {"status": "NO_DATA", "day": day, "strategies": {}, "orders_placed": 0}
    cfg = config or BacktestConfig()
    results: dict[str, Any] = {}
    for strategy in STRATEGIES:
        try:
            result = run_backtest(snapshots, strategy, cfg)
            results[strategy] = {"status": "TESTED", "metrics": result.get("metrics") or result.get("overall") or {}, "trades": result.get("trades") or [], "split": result.get("split") or {}, "strategy": result.get("strategy")}
        except (TypeError, ValueError, RuntimeError) as exc:
            results[strategy] = {"status": "ERROR", "error": str(exc)}
    unsupported = {strategy: "NOT_YET_EXPOSED_BY_EXECUTION_ENGINE" for strategy in RESEARCH_STRATEGIES if strategy not in STRATEGIES}
    tested_metrics = {name: value.get("metrics") or {} for name, value in results.items() if value.get("status") == "TESTED"}
    ranked = sorted(((float((metric.get("net_pnl") or 0.0)), name) for name, metric in tested_metrics.items()), reverse=True)
    research = {"status": "COMPLETED", "day": day, "observations": len(snapshots), "strategies": results, "strategy_coverage": {"tested": list(STRATEGIES), "pending": unsupported}, "ranking_by_net_pnl": [{"strategy": name, "net_pnl": round(pnl, 2)} for pnl, name in ranked], "orders_placed": 0, "mode": "READ_ONLY_AFTER_MARKET", "counterfactual": True}
    record_research(research)
    return research


def latest_research(day: str | None = None) -> list[dict[str, Any]]:
    from quantnifty.learning_store import load_events
    return load_events("research", day)
