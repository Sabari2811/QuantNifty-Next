from __future__ import annotations

from dataclasses import asdict
from statistics import mean
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


def _spot_atr_points(ordered: list[dict[str, Any]], index: int, period: int = 20) -> float:
    """Close-to-close ATR proxy from stored NIFTY spot snapshots.

    Stored option-chain snapshots do not contain candle highs/lows, so this is
    deliberately named a spot ATR proxy rather than pretending candle ATR exists.
    """
    start = max(1, index - period + 1)
    moves = [abs(_f(ordered[k].get("spot")) - _f(ordered[k - 1].get("spot"))) for k in range(start, index + 1)]
    moves = [m for m in moves if m > 0]
    return mean(moves) if moves else 0.0


def _point_risk(ordered: list[dict[str, Any]], entry_index: int, entry_spot: float) -> dict[str, Any]:
    atr = _spot_atr_points(ordered, entry_index)
    row = ordered[entry_index]
    iv = _f(row.get("atm_iv"))
    # Use the stored spot-volatility proxy as the base risk unit. ATM IV widens
    # the stop modestly in a high-volatility regime; minimum/maximum point
    # bounds prevent microscopic stops on dense snapshots or runaway risk.
    iv_multiplier = 1.20 if iv >= 20.0 else 1.0 if iv >= 12.0 else 0.90
    raw_stop = atr * 4.0 * iv_multiplier
    stop_points = min(150.0, max(50.0, raw_stop))
    target_points = stop_points * 2.0
    return {
        "method": "SPOT_ATR_PROXY_X4_WITH_ATM_IV_ADJUSTMENT",
        "atr_proxy_points": round(atr, 2),
        "atm_iv": round(iv, 2) if iv else None,
        "iv_multiplier": iv_multiplier,
        "stop_points": round(stop_points, 2),
        "target_points": round(target_points, 2),
        "risk_reward": 2.0,
        "stop_spot": round(entry_spot - stop_points, 2),
        "target_spot": round(entry_spot + target_points, 2),
    }


def run_position_hold_backtest(snapshots: list[dict[str, Any]], strategy: str = "adaptive", config: BacktestConfig | None = None) -> dict[str, Any]:
    """Research-only lifecycle using volatility-derived NIFTY point exits.

    ENTRY -> OPEN -> HOLD/MONITOR -> EXIT. One position at a time. The active
    position is held until its point stop/target, adaptive exit, thesis/risk
    invalidation, expiry or same-day session close. Option P&L is calculated
    from the actual stored entry/exit option premium, while stop/target are
    expressed in NIFTY spot points.
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
    trade_details: list[dict[str, Any]] = []
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
            blocked += 1
            i += 1
            continue
        approved += 1
        instrument = (decision.get("execution_plan") or {}).get("instrument")
        entry_snap = ordered[i + 1]
        leg = _find_leg(entry_snap, instrument)
        if not leg:
            i += 1
            continue
        signal = decision.get("signal") or {}
        direction = _thesis_direction(decision)
        option_side = "CE" if direction == "BULLISH" else "PE" if direction == "BEARISH" else ""
        if option_side and str(leg.get("side") or "").upper() != option_side:
            i += 1
            continue
        entry = _mid_or_last(leg, "BUY")
        entry_spot = _f(entry_snap.get("spot"))
        if entry <= 0 or entry_spot <= 0:
            i += 1
            continue

        entry_dt = _timestamp(entry_snap)
        entry_day = entry_dt.astimezone(IST).date() if entry_dt else None
        expiry = _expiry_datetime(entry_snap.get("expiry"))
        selected = _selected_strategy(decision)
        risk_points = _point_risk(ordered, i + 1, entry_spot)
        stop_spot = entry_spot - risk_points["stop_points"] if direction == "BULLISH" else entry_spot + risk_points["stop_points"]
        target_spot = entry_spot + risk_points["target_points"] if direction == "BULLISH" else entry_spot - risk_points["target_points"]
        risk_points["stop_spot"] = round(stop_spot, 2)
        risk_points["target_spot"] = round(target_spot, 2)

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
            favorable = (spot-entry_spot) if direction == "BULLISH" else (entry_spot-spot)
            peak_favorable = max(peak_favorable, favorable)
            hold_bars += 1
            if (direction == "BULLISH" and spot <= stop_spot) or (direction == "BEARISH" and spot >= stop_spot):
                exit_j, reason = j, "POINT_STOP"
                break
            if (direction == "BULLISH" and spot >= target_spot) or (direction == "BEARISH" and spot <= target_spot):
                exit_j, reason = j, "POINT_TARGET"
                break
            if mode == "adaptive" and selected == "early_accumulation":
                exit_state = adaptive_exit_state(ordered[j], ordered[j-1], direction, entry_spot)
                trailing = _f(exit_state.get("trailing_stop_pct")) / 100.0
                if exit_state.get("action") == "EXIT":
                    exit_j, reason = j, "ADAPTIVE_EXHAUSTION"
                    break
                if peak_favorable >= max(8.0, risk_points["stop_points"] * 0.75) and trailing > 0:
                    trail_points = max(10.0, risk_points["stop_points"] * trailing)
                    trail_level = (entry_spot + peak_favorable - trail_points) if direction == "BULLISH" else (entry_spot - peak_favorable + trail_points)
                    if (direction == "BULLISH" and spot <= trail_level) or (direction == "BEARISH" and spot >= trail_level):
                        exit_j, reason = j, "ADAPTIVE_TRAIL"
                        break
            if not _thesis_still_valid(ordered[j], ordered[j-1], direction):
                exit_j, reason = j, "THESIS_INVALIDATED"
                break

        exit_leg = _find_leg(ordered[exit_j], instrument)
        if not exit_leg:
            i = exit_j
            continue
        exit_price = _mid_or_last(exit_leg, "SELL")
        if exit_price <= 0:
            i = exit_j
            continue
        qty = max(1, int(cfg.lot_size))
        gross = (exit_price-entry)*qty
        costs = _cost(entry,qty,cfg.slippage_bps,cfg.fixed_cost) + _cost(exit_price,qty,cfg.slippage_bps,cfg.fixed_cost)
        net = gross-costs
        trade = Trade(i+1,exit_j,ordered[exit_j].get("timestamp"),direction,mode,_f(instrument.get("strike")) if isinstance(instrument,dict) else None,str(instrument.get("security_id")) if isinstance(instrument,dict) else None,entry_spot,_f(ordered[exit_j].get("spot")),entry,exit_price,qty,gross,costs,net,reason,_f(signal.get("confidence")))
        trades.append(trade)
        trade_details.append({**asdict(trade), "risk_model": risk_points, "hold_bars": max(0, exit_j - (i + 1)), "entry_side": option_side, "entry_timestamp": entry_snap.get("timestamp"), "exit_spot": _f(ordered[exit_j].get("spot"))})
        if mode == "adaptive":
            trade_dt = _timestamp(ordered[exit_j])
            trade_day = trade_dt.astimezone(IST).date().isoformat() if trade_dt else current_day
            regime = str((signal.get("adaptive") or {}).get("regime") or _regime(entry_snap))
            pending_day_trades.append(({"net_pnl": net, "direction": direction}, regime, selected or "directional"))
        i = max(i + 1, exit_j)

    if mode == "adaptive":
        flush_day(active_day)
    metrics = _metrics(trades, cfg.initial_capital, len(ordered))
    return {
        "status":"OK","mode":"READ_ONLY_BACKTEST","strategy":mode,"lookahead_free":True,
        "position_lifecycle":"THESIS_HOLD_UNTIL_INVALIDATION",
        "entry_rule":"decision at t, fill at t+1 available quote; one position at a time",
        "exit_rule":"volatility-derived NIFTY point stop/target, adaptive exits, thesis/risk invalidation, same-day session close or expiry",
        "risk_model":"SPOT_ATR_PROXY_X4_WITH_ATM_IV_ADJUSTMENT",
        "risk_model_detail":"stop=max(50, min(150, spot_ATR_proxy_20*4*IV_multiplier)); target=2R; IV multiplier 0.90 below 12, 1.00 from 12-<20, 1.20 at >=20",
        "cost_model":asdict(cfg),"historical_data":data_status,
        "session_filter":{"market_hours_only":True,"observations":len(ordered)},
        "approved_signals":approved,"blocked_signals":blocked,
        "position_lifecycle_metrics":{"hold_bars":hold_bars,"positions_opened":len(trades),"reentry_suppressed_while_open":True},
        "metrics":metrics,"trades":trade_details,"orders_placed":0,"trading_enabled":False,
    }
