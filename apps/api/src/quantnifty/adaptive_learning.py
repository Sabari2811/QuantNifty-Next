from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from quantnifty.historical import historical_data_status

POLICY_SCHEMA_VERSION = "adaptive-policy-v1"
MIN_STRATEGY_SAMPLES = 5


def _f(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _score(stats: dict[str, Any]) -> float:
    trades = int(stats.get("trades") or 0)
    if trades <= 0:
        return 0.0
    wins = int(stats.get("wins") or 0)
    win_rate = wins / trades
    avg_pnl = _f(stats.get("net_pnl")) / trades
    pnl_component = 0.5 + max(-0.5, min(0.5, avg_pnl / 400.0))
    evidence = min(1.0, trades / MIN_STRATEGY_SAMPLES)
    return round((0.55 * win_rate + 0.45 * pnl_component) * (0.35 + 0.65 * evidence), 6)


def build_validated_policy(snapshots: Iterable[dict[str, Any]], trades: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build a research artifact from live/same-day stored evidence only.

    Pre-existing historical recordings are deliberately rejected as a learning
    source. There is no calendar-day or trading-day startup gate; sample-size
    controls remain at strategy promotion time.
    """
    values = list(snapshots)
    data_status = historical_data_status(values)
    provenance = set(data_status.get("provenance") or [])
    if not values or "RECORDED_HISTORICAL" in provenance or not provenance.issubset({"LIVE_PROVIDER"}):
        return {
            "schema_version": POLICY_SCHEMA_VERSION,
            "status": "LIVE_LEARNING_SOURCE_REQUIRED",
            "learning_ready": False,
            "historical_data": data_status,
            "strategies": {},
            "regimes": {},
        }

    ordered = sorted(values, key=lambda row: str(row.get("timestamp") or ""))
    training_end = _timestamp(ordered[-1].get("timestamp"))
    by_strategy: dict[str, dict[str, Any]] = {}
    by_regime: dict[str, dict[str, dict[str, Any]]] = {}
    for trade in trades:
        strategy = str(trade.get("strategy") or "").strip().lower()
        if not strategy:
            continue
        regime = str(trade.get("regime") or "UNKNOWN").upper()
        net_pnl = _f(trade.get("net_pnl"))
        bucket = by_strategy.setdefault(strategy, {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
        bucket["trades"] += 1
        bucket["wins"] += int(net_pnl > 0)
        bucket["losses"] += int(net_pnl < 0)
        bucket["net_pnl"] += net_pnl
        rb = by_regime.setdefault(regime, {}).setdefault(strategy, {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
        rb["trades"] += 1
        rb["wins"] += int(net_pnl > 0)
        rb["losses"] += int(net_pnl < 0)
        rb["net_pnl"] += net_pnl

    for bucket in by_strategy.values():
        bucket["score"] = _score(bucket)
        bucket["net_pnl"] = round(bucket["net_pnl"], 2)
    for regime in by_regime.values():
        for bucket in regime.values():
            bucket["score"] = _score(bucket)
            bucket["net_pnl"] = round(bucket["net_pnl"], 2)

    eligible = [(stats["score"], strategy) for strategy, stats in by_strategy.items() if int(stats.get("trades") or 0) >= MIN_STRATEGY_SAMPLES]
    eligible.sort(reverse=True)
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "status": "VALIDATED_RESEARCH_POLICY",
        "learning_ready": True,
        "promotion_status": "RESEARCH_ONLY_PENDING_LIVE_PROMOTION",
        "historical_data": data_status,
        "training_start": ordered[0].get("timestamp"),
        "training_end": training_end.isoformat() if training_end else None,
        "minimum_strategy_samples": MIN_STRATEGY_SAMPLES,
        "strategies": by_strategy,
        "regimes": by_regime,
        "recommended_global_strategy": eligible[0][1] if eligible else None,
    }


def validate_live_policy(policy: dict[str, Any], live_timestamp: Any) -> dict[str, Any]:
    """Fail closed unless a policy is validated and strictly prior to live time."""
    errors: list[str] = []
    if policy.get("schema_version") != POLICY_SCHEMA_VERSION:
        errors.append("schema_version")
    if policy.get("status") != "VALIDATED_RESEARCH_POLICY":
        errors.append("status")
    if not policy.get("learning_ready"):
        errors.append("learning_ready")
    historical = policy.get("historical_data") or {}
    provenance = set(historical.get("provenance") or [])
    if "RECORDED_HISTORICAL" in provenance or not provenance.issubset({"LIVE_PROVIDER"}):
        errors.append("historical_provenance")
    trained_until = _timestamp(policy.get("training_end"))
    live_at = _timestamp(live_timestamp)
    if trained_until is None:
        errors.append("training_end")
    if live_at is None:
        errors.append("live_timestamp")
    if trained_until and live_at and trained_until >= live_at:
        errors.append("future_data_leak")
    return {"valid": not errors, "errors": errors, "schema_version": policy.get("schema_version")}
