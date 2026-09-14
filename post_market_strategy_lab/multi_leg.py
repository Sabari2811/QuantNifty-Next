from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from typing import Any
from .runner import LabConfig,IST,_f,_session,_spot,_timestamp,_fill,_cost,_metrics,_front_expiry
from .strategies import all_strategies
MULTI_LEG_STRATEGIES=("Bull Put Spread","Bear Call Spread","Bull Call Spread","Bear Put Spread","ATM Straddle","OTM Strangle","Iron Condor","Iron Fly")
def _rows(snapshot:dict[str,Any],side:str)->list[dict[str,Any]]:return [r for r in snapshot.get("option_chain") or [] if isinstance(r,dict) and str(r.get("side") or r.get("option_type") or "").upper()==side and _f(r.get("last_price") or r.get("ltp"))>0]
def _key(r:dict[str,Any])->tuple[str,str,float,str]:return (str(r.get("security_id") or r.get("instrument_id") or ""),str(r.get("trading_symbol") or r.get("symbol") or ""),_f(r.get("strike")),str(r.get("expiry") or r.get("expiry_date") or ""))
def _find(snapshot:dict[str,Any],key:tuple[str,str,float,str])->dict[str,Any]|None:
    for r in snapshot.get("option_chain") or []:
        if isinstance(r,dict) and _key(r)==key and _f(r.get("last_price") or r.get("ltp"))>0:return r
    return None
def _strike_step(rows:list[dict[str,Any]])->float:
    strikes=sorted({_f(r.get("strike")) for r in rows if _f(r.get("strike"))>0});diffs=[b-a for a,b in zip(strikes,strikes[1:]) if b>a];return min(diffs) if diffs else 50.
def _pick(rows:list[dict[str,Any]],strike:float)->dict[str,Any]|None:return min(rows,key=lambda r:abs(_f(r.get("strike"))-strike)) if rows else None
def _contracts(snapshot:dict[str,Any],name:str)->list[tuple[str,dict[str,Any]]]:
    spot=_spot(snapshot);calls=_rows(snapshot,"CE");puts=_rows(snapshot,"PE")
    if spot<=0 or not calls or not puts:return []
    exp=_front_expiry(calls+puts)
    if exp:
        calls=[r for r in calls if str(r.get("expiry") or r.get("expiry_date") or "")==exp];puts=[r for r in puts if str(r.get("expiry") or r.get("expiry_date") or "")==exp]
    step=_strike_step(calls+puts);ac=_pick(calls,spot);ap=_pick(puts,spot)
    if not ac or not ap:return []
    p=lambda rows,k:_pick(rows,k)
    if name=="Bull Put Spread":legs=[("SELL",p(puts,spot-step)),("BUY",p(puts,spot-2*step))]
    elif name=="Bear Call Spread":legs=[("SELL",p(calls,spot+step)),("BUY",p(calls,spot+2*step))]
    elif name=="Bull Call Spread":legs=[("BUY",ac),("SELL",p(calls,spot+step))]
    elif name=="Bear Put Spread":legs=[("BUY",ap),("SELL",p(puts,spot-step))]
    elif name=="ATM Straddle":legs=[("BUY",ac),("BUY",ap)]
    elif name=="OTM Strangle":legs=[("BUY",p(calls,spot+step)),("BUY",p(puts,spot-step))]
    elif name=="Iron Condor":legs=[("SELL",p(puts,spot-step)),("BUY",p(puts,spot-2*step)),("SELL",p(calls,spot+step)),("BUY",p(calls,spot+2*step))]
    elif name=="Iron Fly":legs=[("SELL",ap),("BUY",p(puts,spot-step)),("SELL",ac),("BUY",p(calls,spot+step))]
    else:return []
    return [(a,r) for a,r in legs if r]
def _cashflow(legs:list[tuple[str,dict[str,Any]]],action:str)->float:
    total=0.
    for side,row in legs:
        trade_side=side if action=="ENTRY" else ("BUY" if side=="SELL" else "SELL");price=_fill(row,trade_side);total+=-price if trade_side=="BUY" else price
    return total
def _costs(legs:list[tuple[str,dict[str,Any]]],cfg:LabConfig,action:str)->float:
    total=0.
    for side,row in legs:
        trade_side=side if action=="ENTRY" else ("BUY" if side=="SELL" else "SELL");total+=_cost(_fill(row,trade_side),cfg.lot_size,cfg,trade_side)
    return total
def _pnl(entry_cash:float,exit_cash:float,entry_cost:float,exit_cost:float,qty:int)->float:return (entry_cash+exit_cash)*qty-entry_cost-exit_cost
def run_multi_leg_strategy(snapshots:list[dict[str,Any]],name:str,cfg:LabConfig|None=None)->dict[str,Any]:
    cfg=cfg or LabConfig();ordered=sorted([dict(s) for s in snapshots if isinstance(s,dict) and _session(s)],key=lambda s:_timestamp(s) or datetime.min.replace(tzinfo=IST));trades=[];i=0
    while i<len(ordered)-1:
        s=ordered[i];prev=ordered[i-1] if i else None
        if name in {"Bull Put Spread","Bull Call Spread"}:
            signals=[x.signal(s,prev) for x in all_strategies()]
            if signals.count("BULLISH")<2:i+=1;continue
        elif name in {"Bear Call Spread","Bear Put Spread"}:
            signals=[x.signal(s,prev) for x in all_strategies()]
            if signals.count("BEARISH")<2:i+=1;continue
        elif name in {"ATM Straddle","OTM Strangle"}:
            v=_f(s.get("volume_ratio") or (s.get("technicals") or {}).get("volume_ratio"));em=_f((s.get("expected_move") or {}).get("move"))
            if not(v>=1.2 or em>0):i+=1;continue
        else:
            signals=[x.signal(s,prev) for x in all_strategies()]
            if signals.count("BULLISH")>=2 or signals.count("BEARISH")>=2:i+=1;continue
        entry=ordered[i+1];legs=_contracts(entry,name)
        if len(legs)<2:i+=1;continue
        keys=[_key(r) for _,r in legs];entry_cash=_cashflow(legs,"ENTRY");entry_cost=_costs(legs,cfg,"ENTRY");risk_base=max(abs(entry_cash)*cfg.lot_size,cfg.initial_capital*.005)
        if "Condor" in name or "Fly" in name or "Spread" in name:
            widths=[]
            for typ in ("CE","PE"):
                rs=[r for _,r in legs if str(r.get("side") or r.get("option_type") or "").upper()==typ]
                if len(rs)>=2:widths.append(abs(_f(rs[0].get("strike"))-_f(rs[1].get("strike")))*cfg.lot_size)
            if widths:risk_base=max(risk_base,max(widths))
        exit_index=min(len(ordered)-1,i+cfg.max_hold_bars);reason="TIME"
        for j in range(i+1,exit_index+1):
            current=[_find(ordered[j],k) for k in keys]
            if any(r is None for r in current):continue
            exit_legs=[(side,r) for (side,_),r in zip(legs,current)];exit_cash=_cashflow(exit_legs,"EXIT");exit_cost=_costs(exit_legs,cfg,"EXIT");pnl=_pnl(entry_cash,exit_cash,entry_cost,exit_cost,cfg.lot_size);ratio=pnl/risk_base if risk_base else 0.
            if ratio<=-cfg.stop_pct:exit_index,reason=j,"STOP";break
            if ratio>=cfg.target_pct:exit_index,reason=j,"TARGET";break
        current=[_find(ordered[exit_index],k) for k in keys]
        if any(r is None for r in current):i=exit_index;continue
        exit_legs=[(side,r) for (side,_),r in zip(legs,current)];exit_cash=_cashflow(exit_legs,"EXIT");exit_cost=_costs(exit_legs,cfg,"EXIT");pnl=_pnl(entry_cash,exit_cash,entry_cost,exit_cost,cfg.lot_size);dt=_timestamp(ordered[exit_index])
        trades.append({"strategy":name,"family":"multi_leg","entry_timestamp":entry.get("timestamp"),"exit_timestamp":ordered[exit_index].get("timestamp"),"day":dt.astimezone(IST).date().isoformat() if dt else "UNKNOWN","legs":[{"action":a,"strike":_f(r.get("strike")),"security_id":_key(r)[0],"trading_symbol":_key(r)[1],"expiry":_key(r)[3]} for a,r in legs],"entry_cashflow_per_unit":round(entry_cash,4),"exit_cashflow_per_unit":round(exit_cash,4),"costs":round(entry_cost+exit_cost,2),"gross_pnl":round((entry_cash+exit_cash)*cfg.lot_size,2),"net_pnl":round(pnl,2),"exit_reason":reason,"contract_policy":"FIXED_AT_ENTRY"})
        i=max(i+1,exit_index)
    return {"strategy":name,"family":"multi_leg","metrics":_metrics(trades,cfg),"trades":trades,"research_only":True,"contract_policy":"FIXED_AT_ENTRY","cost_model":"NSE_OPTIONS_2026_CONFIGURABLE"}
def run_multi_leg_tournament(snapshots:list[dict[str,Any]],cfg:LabConfig|None=None)->dict[str,Any]:
    cfg=cfg or LabConfig();results=[run_multi_leg_strategy(snapshots,n,cfg) for n in MULTI_LEG_STRATEGIES];results.sort(key=lambda r:(r["metrics"]["net_pnl"],r["metrics"]["profit_factor"]),reverse=True)
    return {"schema_version":"post-market-lab-multi-v3","research_only":True,"orders_placed":0,"configuration":asdict(cfg),"tests":len(results),"leaderboard":[{"rank":i+1,"strategy":r["strategy"],**r["metrics"]} for i,r in enumerate(results)],"results":results}
