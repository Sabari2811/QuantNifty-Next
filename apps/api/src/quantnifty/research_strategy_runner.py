from __future__ import annotations

from typing import Any

from quantnifty.backtest import BacktestConfig
from quantnifty.position_hold_backtest import run_position_hold_backtest
from quantnifty.research_brain import market_regime

RESEARCH_STRATEGIES = (
    "directional", "gamma_blast", "adaptive", "early_accumulation",
    "transition", "range", "breakout_watch",
)

TUNED_CONFIG = BacktestConfig(
    initial_capital=100000.0, lot_size=65, max_hold_bars=8,
    stop_pct=0.0075, target_pct=0.015, slippage_bps=5.0, fixed_cost=40.0,
)


def _regime_name(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> str:
    return str((market_regime(snapshot, previous) or {}).get("regime") or "")


def _scenario_filter(snapshots: list[dict[str, Any]], strategy: str) -> list[dict[str, Any]]:
    if strategy in {"directional", "gamma_blast", "adaptive"}:
        return snapshots
    wanted = {
        "early_accumulation": {"EARLY_ACCUMULATION"},
        "transition": {"GAMMA_TRANSITION"},
        "range": {"POSITIVE_GAMMA_RANGE"},
        "breakout_watch": {"COMPRESSION"},
    }.get(strategy, set())
    if not wanted:
        return snapshots
    selected: list[dict[str, Any]] = []
    previous = None
    for snapshot in snapshots:
        if _regime_name(snapshot, previous) in wanted:
            selected.append(dict(snapshot))
        previous = snapshot
    return selected


def _annotate_result(result: dict[str, Any], strategy: str, source_observations: int, research_observations: int) -> dict[str, Any]:
    result = dict(result)
    result.update({
        "strategy": strategy,
        "research_strategy": strategy,
        "canonical_engine_strategy": "adaptive" if strategy not in {"directional", "gamma_blast"} else strategy,
        "research_only": True,
        "orders_placed": 0,
        "trading_enabled": False,
        "source_observations": source_observations,
        "research_observations": research_observations,
        "tuning": {
            "profile": "INTRADAY_OPTION_RESEARCH_V3_THESIS_HOLD",
            "lot_size": TUNED_CONFIG.lot_size,
            "max_hold_bars": TUNED_CONFIG.max_hold_bars,
            "stop_pct": TUNED_CONFIG.stop_pct,
            "target_pct": TUNED_CONFIG.target_pct,
            "slippage_bps": TUNED_CONFIG.slippage_bps,
            "fixed_cost_per_leg": TUNED_CONFIG.fixed_cost,
            "position_lifecycle": "THESIS_HOLD_UNTIL_INVALIDATION",
            "note": "Research-only lifecycle tuning; one position at a time and same-direction signals do not re-enter while the thesis is open.",
        },
    })
    return result


def run_research_strategy(snapshots: list[dict[str, Any]], strategy: str, config: BacktestConfig | None = None) -> dict[str, Any]:
    requested = str(strategy or "").strip().lower()
    if requested not in RESEARCH_STRATEGIES:
        raise ValueError(f"unsupported research strategy: {requested}")
    legacy_default = BacktestConfig()
    cfg = TUNED_CONFIG if config is None or config == legacy_default else config
    source_count = len(snapshots)
    research_snapshots = _scenario_filter(snapshots, requested)
    engine_strategy = requested if requested in {"directional", "gamma_blast", "adaptive"} else "adaptive"
    return _annotate_result(
        run_position_hold_backtest(research_snapshots, engine_strategy, cfg),
        requested, source_count, len(research_snapshots),
    )
