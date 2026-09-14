from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from .runner import LabConfig, IST, _f, _session, _spot, _timestamp, _fill, _metrics
from .strategies import all_strategies

MULTI_LEG_STRATEGIES = ("Bull Put Spread", "Bear Call Spread", "Bull Call Spread", "Bear Put Spread", "ATM Straddle", "OTM Strangle", "Iron Condor", "Iron Fly")


def _rows(snapshot: dict[str, Any], side: str) -> list[dict[str, Any]]:
    out=[]
    for r in snapshot.get("option_chain") or []:
        if not isinstance(r,dict): continue
        typ=str(r.get("side") or r.get("option_type") or "").upper()
        if typ == side and _f(r.get("last_price") or r.get("ltp")) > 0: out.append(r)
    return out


def _key(r: dict[str,Any]) -> tuple[str,str,float,str]:
    return (str(r.get("security_id") or r.get("instrument_id") or ""),str(r.get("trading_symbol") or r.get("symbol") or ""),_f(r.get("strike")),str(r.get("expiry") or r.get("expiry_date") or ""))


def _find(snapshot: dict[str,Any], key: tuple[str,str,float,str]) -> dict[str,Any] | None:
    for r in snapshot.get("option_chain") or []:
        if isinstance(r,dict) and _key(r)==key and _f(r.get("last_price") or r.get("ltp"))>0: return r
    return None


def _strike_step(rows: list[dict[str,Any]], spot: float) -> float:
    strikes=sorted({_f(r.get("strike")) for r in rows if _f(r.get("strike"))>0})
    diffs=[b-a for a,b in zip(strikes,strikes[1:]) if b>a]
    return min(diffs) if diffs else 50.0


def _pick(rows: list[dict[str,Any]], strike: float) -> dict[str,Any] | None:
    return min(rows,key=lambda r:abs(_f(r.get("strike"))-strike)) if rows else None


def _contracts(snapshot: dict[str,Any], name: str) -> list[tuple[str,dict[str,Any]]]:
    spot=_spot(snapshot); calls=_rows(snapshot,"CE"); puts=_rows(snapshot,"PE")
    if spot<=0 or not calls or not puts: return []
    step=_strike_step(calls+puts,spot); atm_call=_pick(calls,spot); atm_put=_pick(puts,spot)
    if not atm_call or not atm_put: return []
    def p(rows, k): return _pick(rows,k)
    if name=="Bull Put Spread": legs=[("SELL",p(puts,spot-step)),("BUY",p(puts,spot-2*step))]
    elif name=="Bear Call Spread": legs=[("SELL",p(calls,spot+step)),("BUY",p(calls,spot+2*step))]
    elif name=="Bull Call Spread": legs=[("BUY",atm_call),("SELL",p(calls,spot+step))]
    elif name=="Bear Put Spread": legs=[("BUY",atm_put),("SELL",p(puts,spot-step))]
    elif name=="ATM Straddle": legs=[("BUY",atm_call),("BUY",atm_put)]
    elif name=="OTM Strangle": legs=[("BUY",p(calls,spot+step)),("BUY",p(puts,spot-step))]
    elif name=="Iron Condor": legs=[("SELL",p(puts,spot-step)),("BUY",p(puts,spot-2*step)),("SELL",p(calls,spot+step)),("BUY",p(calls,spot+2*step))]
    elif name=="Iron Fly": legs=[("SELL",atm_put),("BUY",p(puts,spot-step)),("SELL",atm_call),("BUY",p(calls,spot+step))]
    else: return []
    return [(a,r) for a,r in legs if r]


def _cashflow(legs: list[tuple[str,dict[str,Any]]], action: str) -> float:
    total=0.0
    for side,row in legs:
        # action is ENTRY or EXIT; reverse trade direction on exit.
        trade_side=side if action=="ENTRY" else ("BUY" if side=="SELL" else "SELL")
        price=_fill(row,trade_side)
        total += -price if trade_side=="BUY" else price
    return total


def _cost(legs: list[tuple[str,dict[str,Any]]], cfg: LabConfig, action: str) -> float:
    total=0.0
    for side,row in legs:
        trade_side=side if action=="ENTRY" else ("BUY" if side=="SELL" else "SELL")
        price=_fill(row,trade_side)
        total += abs(price*cfg.lot_size)*cfg.slippage_bps/10000.0 + cfg.fixed_cost_per_side
    return total


def _pnl(entry_cash: float, exit_cash: float, entry_cost: float, exit_cost: float, qty: int) -> float:
    return (entry_cash+exit_cash)*qty-entry_cost-exit_cost


def run_multi_leg_strategy(snapshots: list[dict[str,Any]], name: str, cfg: LabConfig|None=None) -> dict[str,Any]:
    cfg=cfg or LabConfig(); ordered=sorted([dict(s) for s in snapshots if isinstance(s,dict) and _session(s)],key=lambda s:_timestamp(s) or datetime.min.replace(tzinfo=IST))
    trades=[]; i=0
    # Map confluence strategies to the directional gate; range structures require a neutral regime.
    while i < len(ordered)-1:
        s=ordered[i]; prev=ordered[i-1] if i else None
        direction=None
        if name in {"Bull Put Spread","Bull Call Spread"}: direction="BULLISH"
        elif name in {"Bear Call Spread","Bear Put Spread"}: direction="BEARISH"
        elif name in {"ATM Straddle","OTM Strangle"}: direction="NEUTRAL"
        elif name in {"Iron Condor","Iron Fly"}: direction="NEUTRAL"
        if direction in {"BULLISH","BEARISH"}:
            signals=[x.signal(s,prev) for x in all_strategies()]
            agree=signals.count(direction)>=2
            if not agree: i+=1; continue
        elif name in {"ATM Straddle","OTM Strangle"}:
            # Volatility structures require an expansion cue.
            v=_f(s.get("volume_ratio") or (s.get("technicals") or {}).get("volume_ratio")); em=_f((s.get("expected_move") or {}).get("move"));
            if not (v>=1.2 or em>0): i+=1; continue
        else:
            # Premium-selling structures only enter when there is no strong directional agreement.
            signals=[x.signal(s,prev) for x in all_strategies()]
            if signals.count("BULLISH")>=2 or signals.count("BEARISH")>=2: i+=1; continue
        entry=ordered[i+1]; legs=_contracts(entry,name)
        if len(legs)<2: i+=1; continue
        keys=[_key(r) for _,r in legs]; entry_cash=_cashflow(legs,"ENTRY"); entry_cost=_cost(legs,cfg,"ENTRY")
        risk_base=max(abs(entry_cash)*cfg.lot_size, cfg.initial_capital*0.005)
        # Credit spreads/condors have finite-width max loss; use it as a safer risk denominator.
        strikes=[_f(r.get("strike")) for _,r in legs];
        if "Condor" in name or "Fly" in name or "Spread" in name:
            widths=[]
            calls=[x for _,x in legs if str(x.get("side") or x.get("option_type") or "").upper()=="CE"]
            puts=[x for _,x in legs if str(x.get("side") or x.get("option_type") or "").upper()=="PE"]
            for group in (calls,puts):
                if len(group)>=2: widths.append(abs(_f(group[0].get("strike"))-_f(group[1].get("strike")))*cfg.lot_size)
            if widths: risk_base=max(risk_base,max(widths))
        exit_index=min(len(ordered)-1,i+cfg.max_hold_bars); reason="TIME"
        for j in range(i+1,exit_index+1):
            current=[]
            for key in keys:
                r=_find(ordered[j],key)
                if not r: current=[]; break
                current.append(r)
            if len(current)!=len(keys): continue
            exit_legs=[(side,r) for (side,_),r in zip(legs,current)]; exit_cash=_cashflow(exit_legs,"EXIT"); exit_cost=_cost(exit_legs,cfg,"EXIT")
            pnl=_pnl(entry_cash,exit_cash,entry_cost,exit_cost,cfg.lot_size); ratio=pnl/risk_base if risk_base else 0
            if ratio<=-cfg.stop_pct: exit_index,reason=j,"STOP"; break
            if ratio>=cfg.target_pct: exit_index,reason=j,"TARGET"; break
        current=[]
        for key in keys:
            r=_find(ordered[exit_index],key)
            if not r: current=[]; break
            current.append(r)
        if len(current)!=len(keys): i=exit_index; continue
        exit_legs=[(side,r) for (side,_),r in zip(legs,current)]; exit_cash=_cashflow(exit_legs,"EXIT"); exit_cost=_cost(exit_legs,cfg,"EXIT")
        pnl=_pnl(entry_cash,exit_cash,entry_cost,exit_cost,cfg.lot_size); dt=_timestamp(ordered[exit_index])
        trades.append({"strategy":name,"family":"multi_leg","entry_timestamp":entry.get("timestamp"),"exit_timestamp":ordered[exit_index].get("timestamp"),"day":dt.astimezone(IST).date().isoformat() if dt else "UNKNOWN","legs":[{"action":a,"strike":_f(r.get("strike")),"security_id":_key(r)[0],"trading_symbol":_key(r)[1]} for a,r in legs],"entry_cashflow_per_unit":round(entry_cash,4),"exit_cashflow_per_unit":round(exit_cash,4),"costs":round(entry_cost+exit_cost,2),"gross_pnl":round((entry_cash+exit_cash)*cfg.lot_size,2),"net_pnl":round(pnl,2),"exit_reason":reason,"contract_policy":"FIXED_AT_ENTRY"})
        i=max(i+1,exit_index)
    return {"strategy":name,"family":"multi_leg","metrics":_metrics(trades,cfg),"trades":trades,"research_only":True,"contract_policy":"FIXED_AT_ENTRY"}


def run_multi_leg_tournament(snapshots: list[dict[str,Any]], cfg: LabConfig|None=None) -> dict[str,Any]:
    cfg=cfg or LabConfig(); results=[run_multi_leg_strategy(snapshots,n,cfg) for n in MULTI_LEG_STRATEGIES]
    results.sort(key=lambda r:(r["metrics"]["net_pnl"],r["metrics"]["profit_factor"]),reverse=True)
    return {"schema_version":"post-market-lab-multi-v1","research_only":True,"orders_placed":0,"configuration":asdict(cfg),"tests":len(results),"leaderboard":[{"rank":i+1,"strategy":r["strategy"],**r["metrics"]} for i,r in enumerate(results)],"results":results}
