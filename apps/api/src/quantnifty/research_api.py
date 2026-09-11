from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from quantnifty.after_market_lab import run_after_market_lab
from quantnifty.learning_store import load_events

router = APIRouter(tags=["after-market-research"])
IST = ZoneInfo("Asia/Kolkata")


def _today_ist() -> str:
    return datetime.now(IST).date().isoformat()


def _latest(day: str) -> dict[str, Any] | None:
    events = load_events("research", day)
    rows = [e.get("research") for e in events if isinstance(e, dict) and isinstance(e.get("research"), dict)]
    if not rows:
        return None
    return rows[-1]


def _pnl_row(name: str, value: dict[str, Any]) -> dict[str, Any]:
    metrics = value.get("metrics") or value.get("overall") or {}
    trades = value.get("trades") or []
    net = metrics.get("net_pnl")
    if net is None:
        net = sum(float(t.get("pnl") or t.get("realized_pnl") or 0.0) for t in trades if isinstance(t, dict))
    wins = metrics.get("wins")
    losses = metrics.get("losses")
    if wins is None:
        wins = sum(1 for t in trades if isinstance(t, dict) and float(t.get("pnl") or t.get("realized_pnl") or 0.0) > 0)
    if losses is None:
        losses = sum(1 for t in trades if isinstance(t, dict) and float(t.get("pnl") or t.get("realized_pnl") or 0.0) < 0)
    count = metrics.get("trades")
    if count is None:
        count = len(trades)
    win_rate = metrics.get("win_rate")
    if win_rate is None:
        win_rate = (wins / count * 100.0) if count else 0.0
    return {
        "strategy": name,
        "status": value.get("status"),
        "trades": int(count or 0),
        "wins": int(wins or 0),
        "losses": int(losses or 0),
        "win_rate_pct": round(float(win_rate or 0.0), 2),
        "net_pnl": round(float(net or 0.0), 2),
        "gross_pnl": round(float(metrics.get("gross_pnl") or 0.0), 2),
        "profit_factor": metrics.get("profit_factor"),
        "max_drawdown": metrics.get("max_drawdown") if metrics.get("max_drawdown") is not None else metrics.get("max_dd"),
        "research_only": True,
    }


@router.get("/api/v1/research/results")
def research_results(day: str | None = None, run_if_missing: bool = True):
    target = str(day or _today_ist()).strip()
    try:
        datetime.strptime(target, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "day must be YYYY-MM-DD") from exc

    research = _latest(target)
    generated = False
    if research is None and run_if_missing:
        research = run_after_market_lab(target)
        generated = True
    if research is None:
        return {"status": "NO_DATA", "day": target, "source": "STORED_DAY", "strategies": [], "total_net_pnl": 0.0, "research_only": True}

    strategies = research.get("strategies") or {}
    rows = [_pnl_row(str(name), value) for name, value in strategies.items() if isinstance(value, dict)]
    rows.sort(key=lambda row: (-float(row.get("net_pnl") or 0.0), str(row.get("strategy") or "")))
    return {
        "status": research.get("status", "COMPLETED"),
        "day": target,
        "source": research.get("training_source", "STORED_DAY"),
        "observations": research.get("observations", 0),
        "generated_now": generated,
        "strategy_coverage": research.get("strategy_coverage") or {},
        "strategies": rows,
        "ranking_by_net_pnl": research.get("ranking_by_net_pnl") or [],
        "total_net_pnl": round(sum(float(row.get("net_pnl") or 0.0) for row in rows), 2),
        "orders_placed": int(research.get("orders_placed") or 0),
        "mode": research.get("mode", "READ_ONLY_AFTER_MARKET"),
        "research_only": True,
        "scenarios": research.get("scenarios") or {},
        "policy": research.get("policy") or {},
    }
