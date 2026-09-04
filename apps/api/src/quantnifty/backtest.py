from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from math import sqrt
from statistics import mean, pstdev
from typing import Any

from quantnifty.institutional_engine import final_decision
from quantnifty.historical import historical_data_status, canonicalize_snapshots


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 100000.0
    lot_size: int = 1
    max_hold_bars: int = 12
    stop_pct: float = 0.0125
    target_pct: float = 0.025
    slippage_bps: float = 5.0
    fixed_cost: float = 40.0


@dataclass(frozen=True)
class Trade:
    entry_index: int
    exit_index: int
    timestamp: str | None
    direction: str
    strategy: str
    strike: float | None
    security_id: str | None
    entry_spot: float
    exit_spot: float
    entry_price: float
    exit_price: float
    quantity: int
    gross_pnl: float
    costs: float
    net_pnl: float
    exit_reason: str
    confidence: float


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _timestamp(s: dict[str, Any]) -> datetime | None:
    raw = s.get("timestamp")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _expiry_date(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return raw[:10] if len(raw) >= 10 and raw[4:5] == "-" else None


def _find_leg(snapshot: dict[str, Any], instrument: dict[str, Any] | None) -> dict[str, Any] | None:
    if not instrument:
        return None
    rows = snapshot.get("option_chain") or []
    sid = str(instrument.get("security_id") or instrument.get("securityId") or "")
    symbol = str(instrument.get("trading_symbol") or instrument.get("tradingSymbol") or "")
    strike = _f(instrument.get("strike"))
    side = str(instrument.get("side") or instrument.get("option_type") or "").upper()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if sid and str(row.get("security_id") or "") == sid:
            return row
        if symbol and str(row.get("trading_symbol") or "") == symbol:
            return row
        if strike and abs(_f(row.get("strike")) - strike) < 0.001 and (not side or str(row.get("side") or "").upper() == side):
            return row
    return None


def _mid_or_last(row: dict[str, Any], action: str) -> float:
    bid, ask, last = _f(row.get("bid")), _f(row.get("ask")), _f(row.get("last_price"))
    if action == "BUY":
        return ask if ask > 0 else last if last > 0 else bid
    return bid if bid > 0 else last if last > 0 else ask


def _cost(price: float, qty: int, slippage_bps: float, fixed: float) -> float:
    return abs(price * qty) * slippage_bps / 10000.0 + fixed


def _regime(snapshot: dict[str, Any]) -> str:
    intelligence = snapshot.get("intelligence") or {}
    state = (intelligence.get("market_state") or {}).get("state")
    return str(state or snapshot.get("structure") or "UNKNOWN")


def _metrics(trades: list[Trade], initial_capital: float, observations: int) -> dict[str, Any]:
    pnls = [t.net_pnl for t in trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p < 0]
    equity = initial_capital; peak = equity; max_dd = 0.0
    for p in pnls:
        equity += p; peak = max(peak, equity); max_dd = max(max_dd, peak - equity)
    gross_profit = sum(wins); gross_loss = abs(sum(losses)); mean_pnl = mean(pnls) if pnls else 0.0
    by_day: dict[str, float] = {}; confidence = [t.confidence for t in trades]
    for t in trades:
        dt = _timestamp({"timestamp": t.timestamp}); key = dt.date().isoformat() if dt else str(t.entry_index)
        by_day[key] = by_day.get(key, 0.0) + t.net_pnl
    daily = list(by_day.values()); daily_std = pstdev(daily) if len(daily) > 1 else 0.0
    sharpe = mean(daily) / daily_std * sqrt(252) if daily_std > 0 else 0.0
    max_win_streak = max_loss_streak = current_win = current_loss = 0
    for p in pnls:
        if p > 0: current_win += 1; current_loss = 0; max_win_streak = max(max_win_streak, current_win)
        elif p < 0: current_loss += 1; current_win = 0; max_loss_streak = max(max_loss_streak, current_loss)
    costs = sum(t.costs for t in trades); gross = sum(t.gross_pnl for t in trades)
    return {"observations": observations, "trades": len(trades), "wins": len(wins), "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
            "gross_pnl": round(gross, 2), "net_pnl": round(sum(pnls), 2), "costs": round(costs, 2),
            "cost_drag_pct_of_gross": round(costs / abs(gross) * 100, 2) if gross else 0.0,
            "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else (999.0 if gross_profit else 0.0),
            "expectancy_per_trade": round(mean_pnl, 2), "avg_win": round(mean(wins), 2) if wins else 0.0,
            "avg_loss": round(mean(losses), 2) if losses else 0.0, "max_drawdown": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd / initial_capital * 100, 2) if initial_capital else 0.0,
            "max_consecutive_wins": max_win_streak, "max_consecutive_losses": max_loss_streak,
            "ending_equity": round(equity, 2), "sharpe_like": round(sharpe, 3),
            "return_pct": round((equity - initial_capital) / initial_capital * 100, 2) if initial_capital else 0.0,
            "avg_signal_confidence": round(mean(confidence), 2) if confidence else 0.0}


def _trade_slice(trades: list[Trade], start: int, end: int) -> list[Trade]:
    return [t for t in trades if start <= t.entry_index < end]


def _canonical_backtest_input(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not snapshots:
        return []
    provenances = {str(s.get("data_integrity") or "UNKNOWN") for s in snapshots if isinstance(s, dict)}
    if provenances == {"RECORDED_HISTORICAL"}: provenance = "RECORDED_HISTORICAL"
    elif provenances == {"LIVE_PROVIDER"}: provenance = "LIVE_PROVIDER"
    else: raise ValueError("mixed or unknown historical data provenance is not allowed")
    return canonicalize_snapshots(snapshots, provenance)


def run_backtest(snapshots: list[dict[str, Any]], strategy: str = "directional", config: BacktestConfig | None = None) -> dict[str, Any]:
    cfg = config or BacktestConfig(); mode = strategy.strip().lower()
    if mode not in {"directional", "gamma_blast"}: raise ValueError("strategy must be directional or gamma_blast")
    ordered = _canonical_backtest_input(snapshots); data_status = historical_data_status(ordered)
    if len(ordered) < 2:
        return {"status":"INSUFFICIENT_DATA","strategy":mode,"historical_data":data_status,"metrics":_metrics([],cfg.initial_capital,len(ordered)),"trades":[],"regimes":{},"split":{}}
    trades: list[Trade] = []; blocked = approved = 0; i = 0; previous = None
    while i < len(ordered) - 1:
        decision = final_decision(ordered[i], previous, mode); previous = ordered[i]; risk = decision.get("risk") or {}
        if not risk.get("approved"): blocked += 1; i += 1; continue
        approved += 1; instrument = (decision.get("execution_plan") or {}).get("instrument"); entry_snap = ordered[i + 1]
        leg = _find_leg(entry_snap, instrument)
        if not leg: i += 1; continue
        signal = decision.get("signal") or {}; direction = str(signal.get("direction") or "NEUTRAL")
        option_side = "CE" if direction == "BULLISH" else "PE" if direction == "BEARISH" else ""
        if option_side and str(leg.get("side") or "").upper() != option_side: i += 1; continue
        entry = _mid_or_last(leg, "BUY"); entry_spot = _f(entry_snap.get("spot"))
        if entry <= 0 or entry_spot <= 0: i += 1; continue
        max_j = min(len(ordered) - 1, i + max(1, cfg.max_hold_bars)); exit_j, reason = max_j, "TIME"
        for j in range(i + 1, max_j + 1):
            spot = _f(ordered[j].get("spot")); favorable = (spot-entry_spot)/entry_spot if direction == "BULLISH" else (entry_spot-spot)/entry_spot
            if favorable <= -abs(cfg.stop_pct): exit_j, reason = j, "STOP"; break
            if favorable >= abs(cfg.target_pct): exit_j, reason = j, "TARGET"; break
        exit_leg = _find_leg(ordered[exit_j], instrument)
        if not exit_leg: i = exit_j; continue
        exit_price = _mid_or_last(exit_leg, "SELL")
        if exit_price <= 0: i = exit_j; continue
        qty = max(1, int(cfg.lot_size)); gross = (exit_price-entry)*qty
        costs = _cost(entry,qty,cfg.slippage_bps,cfg.fixed_cost) + _cost(exit_price,qty,cfg.slippage_bps,cfg.fixed_cost)
        trades.append(Trade(i+1,exit_j,ordered[exit_j].get("timestamp"),direction,mode,_f(instrument.get("strike")) if isinstance(instrument,dict) else None,str(instrument.get("security_id")) if isinstance(instrument,dict) else None,entry_spot,_f(ordered[exit_j].get("spot")),entry,exit_price,qty,gross,costs,gross-costs,reason,_f(signal.get("confidence"))))
        i = max(i + 1, exit_j)
    n=len(ordered); train_end=max(1,int(n*.60)); val_end=max(train_end+1,int(n*.80)) if n>2 else n
    splits={"in_sample":[0,train_end],"validation":[train_end,min(val_end,n)],"out_of_sample":[min(val_end,n),n]}
    split_metrics={name:_metrics(_trade_slice(trades,a,b),cfg.initial_capital,b-a) for name,(a,b) in splits.items()}
    regimes:dict[str,list[Trade]]={}
    for t in trades:
        entry_snapshot=ordered[min(t.entry_index,n-1)]; regimes.setdefault(_regime(entry_snapshot),[]).append(t)
        dt=_timestamp(entry_snapshot); expiry=_expiry_date(entry_snapshot.get("expiry"))
        if dt and expiry and dt.date().isoformat()==expiry:
            regimes.setdefault("EXPIRY_DAY",[]).append(t)
            if dt.hour==9 and dt.minute<30: regimes.setdefault("EXPIRY_OPEN",[]).append(t)
            if dt.hour*60+dt.minute>=15*60+15: regimes.setdefault("EXPIRY_FINAL_15M",[]).append(t)
    regime_metrics={name:_metrics(ts,cfg.initial_capital,len(ts)) for name,ts in regimes.items()}; risk_gate={"approved":approved,"blocked":blocked,"block_rate_pct":round(blocked/(approved+blocked)*100,2) if approved+blocked else 0.0}; overall=_metrics(trades,cfg.initial_capital,n)
    return {"status":"OK","mode":"READ_ONLY_BACKTEST","strategy":mode,"lookahead_free":True,"entry_rule":"decision at t, fill at t+1 available quote","exit_rule":"next-snapshot spot stop/target, otherwise max-hold time","cost_model":asdict(cfg),"historical_data":data_status,"approved_signals":approved,"blocked_signals":blocked,"risk_gate_effectiveness":risk_gate,"signal_quality":{"traded_signals":len(trades),"trade_win_rate_pct":overall["win_rate_pct"],"avg_confidence":overall["avg_signal_confidence"]},"metrics":overall,"split":split_metrics,"regimes":regime_metrics,"trades":[asdict(t) for t in trades],"orders_placed":0,"trading_enabled":False}


def validation_report(snapshots: list[dict[str, Any]], strategy: str = "directional", config: BacktestConfig | None = None) -> dict[str, Any]:
    result=run_backtest(snapshots,strategy,config)
    return {"status":result.get("status"),"strategy":result.get("strategy"),"lookahead_free":result.get("lookahead_free"),"historical_data":result.get("historical_data"),"oos":result.get("split",{}).get("out_of_sample",{}),"overall":result.get("metrics"),"risk_gate":result.get("risk_gate_effectiveness",{}),"signal_quality":result.get("signal_quality",{}),"regimes":result.get("regimes",{}),"research_only":True,"orders_placed":0}
