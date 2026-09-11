from __future__ import annotations

from dataclasses import asdict
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.backtest import (
    BacktestConfig, Trade, _canonical_backtest_input, _cost, _expiry_datetime,
    _find_leg, _f, _is_market_session, _metrics, _mid_or_last, _regime, _timestamp,
)
from quantnifty.historical import historical_data_status
from quantnifty.institutional_engine import final_decision
from quantnifty.research_brain import adaptive_exit_state, update_adaptive_memory

IST = ZoneInfo("Asia/Kolkata")


def _thesis_direction(decision: dict[str, Any]) -> str:
    return str((decision.get("signal") or {}).get("direction") or "NEUTRAL").upper()


def _selected_strategy(decision: dict[str, Any]) -> str:
    signal = decision.get("signal") or {}
    risk = decision.get("risk") or {}
    return str((signal.get("adaptive") or {}).get("selected_strategy") or risk.get("selected_strategy") or "").lower()


def _thesis_still_valid(snapshot: dict[str, Any], previous: dict[str, Any] | None, direction: str) -> bool:
    decision = final_decision(dict(snapshot), previous, "BACKTEST", "BACKTEST")
    if _thesis_direction(decision) != direction:
        return False
    return bool((decision.get("risk") or {}).get("approved"))


def run_position_hold_backtest(snapshots: list[dict[str, Any]], strategy: str = "adaptive", config: BacktestConfig | None = None) -> dict[str, Any]:
    """Research-only lifecycle: enter once, hold the thesis, then exit on risk,
    target, invalidation, expiry or same-day session close. No re-entry while open.
    """
    cfg = config or BacktestConfig()
    mode = strategy.strip().lower()
    if mode not in {"directional", "gamma_blast", "adaptive"}:
        raise ValueError("strategy must be directional, gamma_blast, or adaptive")
    canonical = _canonical_backtest_input(snapshots)
    data_status = historical_data_status(canonical)
    ordered = [s for s in canonical if _is_market_session(s)]
    if len(ordered) < 2:
        return {"status":"INSUFFICIENT_DATA","strategy":mode,"historical_data":data_status,"session_filter":{"market_hours_only":True,"observations":len(ordered)},"metrics":_metrics([],cfg.initial_capital,len(ordered)),"trades":[]}

    trades: list[Trade] = []
    blocked = approved = hold_bars = 0
    i = 0
    previous: dict[str, Any] | None = None
    adaptive_memory: dict[str, Any] = {"by_regime": {}, "global": {}, "recent_days": [], "last_direction": None}
    active_day: str | None = None
    day_open_memory: dict[str, Any] = adaptive_memory
    pending_day_trades: list[tuple[dict[str, Any], str, str]] = []

    def flush_day(day: str | None) -> None:
        nonlocal adaptive_memory, pending_day_trades
        if not day:
            return
        for trade_row, regime, selected in pending_day_trades:
            adaptive_memory = update_adaptive_memory(adaptive_memory, trade_row, day, regime, selected)
        pending_day_trades = []

    while i < len(ordered) - 1:
        current_dt = _timestamp(ordered[i])
        current_day = current_dt.astimezone(IST).date().isoformat() if current_dt else None
        if mode == "adaptive" and current_day != active_day:
            flush_day(active_day)
            active_day = current_day
            day_open_memory = {
                "by_regime": {k: dict(v) for k, v in (adaptive_memory.get("by_regime") or {}).items()},
                "global": {k: dict(v) for k, v in (adaptive_memory.get("global") or {}).items()},
                "recent_days": list(adaptive_memory.get("recent_days") or []),
                "last_direction": adaptive_memory.get("last_direction"),
            }

        decision_input = dict(ordered[i])
        if mode == "adaptive":
            decision_input["_adaptive_memory"] = day_open_memory
        decision = final_decision(decision_input, previous, mode, "BACKTEST")
        previous = ordered[i]
        risk = decision.get("risk") or {}
        if not risk.get("approved"):
            blocked += 1; i += 1; continue
        approved += 1
        instrument = (decision.get("execution_plan") or {}).get("instrument")
        entry_snap = ordered[i + 1]
        leg = _find_leg(entry_snap, instrument)
        if not leg:
            i += 1; continue
        signal = decision.get("signal") or {}
        direction = _thesis_direction(decision)
        option_side = "CE" if direction == "BULLISH" else "PE" if direction == "BEARISH" else ""
        if option_side and str(leg.get("side") or "").upper() != option_side:
            i += 1; continue
        entry = _mid_or_last(leg, "BUY")
        entry_spot = _f(entry_snap.get("spot"))
        if entry <= 0 or entry_spot <= 0:
            i += 1; continue

        entry_dt = _timestamp(entry_snap)
        entry_day = entry_dt.astimezone(IST).date() if entry_dt else None
        expiry = _expiry_datetime(entry_snap.get("expiry"))
        selected = _selected_strategy(decision)
        exit_j = i + 1
        reason = "SESSION_CLOSE"
        peak_favorable = 0.0

        for j in range(i + 1, len(ordered)):
            ts = _timestamp(ordered[j])
            if entry_day is not None and ts is not None and ts.astimezone(IST).date() != entry_day:
                exit_j, reason = j - 1, "SESSION_CLOSE"
                break
            if expiry and ts and ts.astimezone(IST) > expiry:
                exit_j, reason = max(i + 1, j - 1), "EXPIRY"
                break
            spot = _f(ordered[j].get("spot"))
            favorable = (spot-entry_spot)/entry_spot if direction == "BULLISH" else (entry_spot-spot)/entry_spot
            peak_favorable = max(peak_favorable, favorable); hold_bars += 1
            if favorable <= -abs(cfg.stop_pct): exit_j, reason = j, "STOP"; break
            if favorable >= abs(cfg.target_pct): exit_j, reason = j, "TARGET"; break
            if mode == "adaptive" and selected == "early_accumulation":
                exit_state = adaptive_exit_state(ordered[j], ordered[j-1], direction, entry_spot)
                trailing = _f(exit_state.get("trailing_stop_pct")) / 100.0
                if exit_state.get("action") == "EXIT": exit_j, reason = j, "ADAPTIVE_EXHAUSTION"; break
                if peak_favorable >= 0.008 and trailing > 0 and favorable <= peak_favorable - trailing:
                    exit_j, reason = j, "ADAPTIVE_TRAIL"; break
            if not _thesis_still_valid(ordered[j], ordered[j-1], direction):
                exit_j, reason = j, "THESIS_INVALIDATED"; break

        exit_leg = _find_leg(ordered[exit_j], instrument)
        if not exit_leg:
            i = exit_j; continue
        exit_price = _mid_or_last(exit_leg, "SELL")
        if exit_price <= 0:
            i = exit_j; continue
        qty = max(1, int(cfg.lot_size))
        gross = (exit_price-entry)*qty
        costs = _cost(entry,qty,cfg.slippage_bps,cfg.fixed_cost) + _cost(exit_price,qty,cfg.slippage_bps,cfg.fixed_cost)
        net = gross-costs
        trade = Trade(i+1,exit_j,ordered[exit_j].get("timestamp"),direction,mode,_f(instrument.get("strike")) if isinstance(instrument,dict) else None,str(instrument.get("security_id")) if isinstance(instrument,dict) else None,entry_spot,_f(ordered[exit_j].get("spot")),entry,exit_price,qty,gross,costs,net,reason,_f(signal.get("confidence")))
        trades.append(trade)
        if mode == "adaptive":
            trade_dt = _timestamp(ordered[exit_j])
            trade_day = trade_dt.astimezone(IST).date().isoformat() if trade_dt else current_day
            regime = str((signal.get("adaptive") or {}).get("regime") or _regime(entry_snap))
            pending_day_trades.append(({"net_pnl": net, "direction": direction}, regime, selected or "directional"))
        i = max(i + 1, exit_j)

    if mode == "adaptive": flush_day(active_day)
    metrics = _metrics(trades, cfg.initial_capital, len(ordered))
    return {
        "status":"OK","mode":"READ_ONLY_BACKTEST","strategy":mode,"lookahead_free":True,
        "position_lifecycle":"THESIS_HOLD_UNTIL_INVALIDATION",
        "entry_rule":"decision at t, fill at t+1 available quote; one position at a time",
        "exit_rule":"spot stop/target, adaptive exits, thesis/risk invalidation, same-day session close or expiry",
        "cost_model":asdict(cfg),"historical_data":data_status,
        "session_filter":{"market_hours_only":True,"observations":len(ordered)},
        "approved_signals":approved,"blocked_signals":blocked,
        "position_lifecycle_metrics":{"hold_bars":hold_bars,"positions_opened":len(trades),"reentry_suppressed_while_open":True},
        "metrics":metrics,"trades":[asdict(t) for t in trades],"orders_placed":0,"trading_enabled":False,
    }
