from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import mean, pstdev
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

TIME_BUCKETS = (
    ("09:15-09:30", 9, 15, 9, 30),
    ("09:30-10:30", 9, 30, 10, 30),
    ("10:30-12:00", 10, 30, 12, 0),
    ("12:00-14:00", 12, 0, 14, 0),
    ("14:00-15:00", 14, 0, 15, 0),
    ("15:00-15:30", 15, 0, 15, 31),
)


def _ts(value: Any):
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def time_bucket(timestamp: Any) -> str:
    dt = _ts(timestamp)
    if dt is None:
        return "UNKNOWN"
    local = dt.astimezone(IST)
    minute = local.hour * 60 + local.minute
    for name, sh, sm, eh, em in TIME_BUCKETS:
        start = sh * 60 + sm
        end = eh * 60 + em
        if start <= minute < end:
            return name
    return "OUTSIDE_SESSION"


def _profit_factor(pnls: Iterable[float]) -> float:
    values = list(pnls)
    gp = sum(p for p in values if p > 0)
    gl = abs(sum(p for p in values if p < 0))
    return round(gp / gl, 3) if gl else (999.0 if gp else 0.0)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnls = [float(r.get("net_pnl") or 0.0) for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    return {
        "trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 2) if pnls else 0.0,
        "net_pnl": round(sum(pnls), 2),
        "profit_factor": _profit_factor(pnls),
        "expectancy": round(mean(pnls), 2) if pnls else 0.0,
        "avg_win": round(mean(wins), 2) if wins else 0.0,
        "avg_loss": round(mean(losses), 2) if losses else 0.0,
    }


def _group(rows: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    return {name: _summary(items) for name, items in sorted(groups.items())}


def trade_diagnostics(trades: Iterable[Any], snapshots: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Research-only diagnostics. Never changes entry/exit decisions."""
    rows: list[dict[str, Any]] = []
    for trade in trades:
        if hasattr(trade, "__dataclass_fields__"):
            from dataclasses import asdict
            row = asdict(trade)
        else:
            row = dict(trade)
        entry_index = int(row.get("entry_index") or 0)
        entry = snapshots[entry_index] if snapshots and 0 <= entry_index < len(snapshots) else None
        row["regime"] = str((entry or {}).get("regime") or (entry or {}).get("structure") or "UNKNOWN")
        row["time_bucket"] = time_bucket(row.get("timestamp") or (entry or {}).get("timestamp"))
        rows.append(row)

    return {
        "by_regime": _group(rows, lambda r: r["regime"]),
        "by_time_bucket": _group(rows, lambda r: r["time_bucket"]),
        "by_direction": _group(rows, lambda r: str(r.get("direction") or "UNKNOWN")),
        "by_exit_reason": _group(rows, lambda r: str(r.get("exit_reason") or "UNKNOWN")),
        "overall": _summary(rows),
    }


def walk_forward_splits(observations: int, train_fraction: float = 0.60, validation_fraction: float = 0.20, min_train: int = 100) -> list[dict[str, tuple[int, int]]]:
    """Return chronological train/validation/OOS windows; no shuffling."""
    n = max(0, int(observations))
    if n < 3:
        return []
    train = max(int(n * train_fraction), min_train)
    train = min(train, n - 2)
    validation = max(1, int(n * validation_fraction))
    if train + validation >= n:
        validation = max(1, n - train - 1)
    return [{
        "train": (0, train),
        "validation": (train, train + validation),
        "out_of_sample": (train + validation, n),
    }]


def robustness_gate(metrics: dict[str, Any], *, min_trades: int = 30, min_profit_factor: float = 1.15, max_drawdown_pct: float = 20.0, min_expectancy: float = 0.0) -> dict[str, Any]:
    """Conservative research gate; this is not a claim of profitability."""
    checks = {
        "enough_trades": int(metrics.get("trades") or 0) >= min_trades,
        "positive_expectancy": float(metrics.get("expectancy_per_trade", metrics.get("expectancy", 0)) or 0) > min_expectancy,
        "profit_factor": float(metrics.get("profit_factor") or 0) >= min_profit_factor,
        "drawdown": float(metrics.get("max_drawdown_pct") or 0) <= max_drawdown_pct,
    }
    return {"passed": all(checks.values()), "checks": checks, "thresholds": {"min_trades": min_trades, "min_profit_factor": min_profit_factor, "max_drawdown_pct": max_drawdown_pct, "min_expectancy": min_expectancy}}


def cost_sensitivity(base: dict[str, Any], scenarios: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a deterministic research sensitivity label to caller-provided runs."""
    result = []
    for scenario in scenarios:
        row = dict(scenario)
        row["survives_base_profitability"] = float(row.get("net_pnl") or 0) > 0 and float(row.get("profit_factor") or 0) > 1
        result.append(row)
    return result
