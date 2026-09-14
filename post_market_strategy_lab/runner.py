from __future__ import annotations
from dataclasses import asdict,dataclass
from datetime import datetime,time,date
from statistics import mean,pstdev
from math import sqrt
from typing import Any
from zoneinfo import ZoneInfo
from .strategies import StrategySpec,all_strategies
IST=ZoneInfo("Asia/Kolkata"); OPEN=time(9,15); CLOSE=time(15,30)
@dataclass
class LabConfig:
    initial_capital:float=100000.0; lot_size:int=65; max_hold_bars:int=8; stop_pct:float=.0075; target_pct:float=.015; slippage_bps:float=5.0; fixed_cost_per_side:float=20.0; transaction_charge_rate:float=.0003553; sebi_rate:float=.000001; stamp_rate:float=.00003; stt_sell_rate:float=.0015; gst_rate:float=.18; min_volume:float=0.0

def _f(v:Any)->float:
    try:return float(v or 0.0)
    except(TypeError,ValueError):return 0.0

def _timestamp(s:dict[str,Any])->datetime|None:
    raw=s.get("timestamp")
    if not raw:return None
    try:return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except ValueError:return None

def _session(s:dict[str,Any])->bool:
    dt=_timestamp(s)
    if not dt:return False
    x=dt.astimezone(IST);return x.weekday()<5 and OPEN<=x.time()<=CLOSE

def _spot(s:dict[str,Any])->float:return _f(s.get("spot") or s.get("nifty") or s.get("close"))
def _side(direction:str)->str:return "CE" if direction=="BULLISH" else "PE" if direction=="BEARISH" else ""
def _expiry_value(v:Any)->str:return str(v or "")

def _front_expiry(rows:list[dict[str,Any]])->str|None:
    vals=sorted({_expiry_value(r.get("expiry") or r.get("expiry_date")) for r in rows if (r.get("expiry") or r.get("expiry_date"))})
    return vals[0] if vals else None

def _option_key(row:dict[str,Any])->tuple[str,str,float,str]:return (str(row.get("security_id") or row.get("instrument_id") or ""),str(row.get("trading_symbol") or row.get("symbol") or ""),_f(row.get("strike")),_expiry_value(row.get("expiry") or row.get("expiry_date")))

def _select_option(snapshot:dict[str,Any],direction:str,variant:str="ATM")->dict[str,Any]|None:
    side=_side(direction);spot=_spot(snapshot);rows=[r for r in snapshot.get("option_chain") or [] if isinstance(r,dict) and str(r.get("side") or r.get("option_type") or "").upper()==side and _f(r.get("last_price") or r.get("ltp"))>0]
    if not rows or spot<=0:return None
    exp=_front_expiry(rows)
    if exp:rows=[r for r in rows if _expiry_value(r.get("expiry") or r.get("expiry_date"))==exp]
    rows.sort(key=lambda r:abs(_f(r.get("strike"))-spot))
    if variant=="ATM":return rows[0]
    if variant=="ITM":
        x=[r for r in rows if (_f(r.get("strike"))<spot if side=="CE" else _f(r.get("strike"))>spot)];return min(x,key=lambda r:abs(_f(r.get("strike"))-spot)) if x else rows[0]
    if variant=="OTM":
        x=[r for r in rows if (_f(r.get("strike"))>spot if side=="CE" else _f(r.get("strike"))<spot)];return min(x,key=lambda r:abs(_f(r.get("strike"))-spot)) if x else rows[0]
    target={"D050":.50,"D060":.60,"D070":.70}.get(variant);return min(rows,key=lambda r:abs(abs(_f(r.get("delta")))-target)) if target is not None else rows[0]

def _find_fixed(snapshot:dict[str,Any],key:tuple[str,str,float,str])->dict[str,Any]|None:
    for row in snapshot.get("option_chain") or []:
        if isinstance(row,dict) and _option_key(row)==key and _f(row.get("last_price") or row.get("ltp"))>0:return row
    return None

def _fill(row:dict[str,Any],action:str)->float:
    bid,ask,last=_f(row.get("bid")),_f(row.get("ask")),_f(row.get("last_price") or row.get("ltp"));return (ask or last or bid) if action=="BUY" else (bid or last or ask)

def _cost(price:float,qty:int,cfg:LabConfig,action:str)->float:
    premium=abs(price*qty);brokerage=cfg.fixed_cost_per_side;txn=premium*cfg.transaction_charge_rate;sebi=premium*cfg.sebi_rate;stamp=premium*cfg.stamp_rate if action=="BUY" else 0.0;stt=premium*cfg.stt_sell_rate if action=="SELL" else 0.0;gst=cfg.gst_rate*(brokerage+txn+sebi);slippage=premium*cfg.slippage_bps/10000.0;return brokerage+txn+sebi+stamp+stt+gst+slippage

def _metrics(trades:list[dict[str,Any]],cfg:LabConfig)->dict[str,Any]:
    pnls=[float(t["net_pnl"]) for t in trades];wins=[p for p in pnls if p>0];losses=[p for p in pnls if p<0];gp,gl=sum(wins),abs(sum(losses));equity=cfg.initial_capital;peak=equity;dd=0.;by_day={}
    for t in trades:
        equity+=t["net_pnl"];peak=max(peak,equity);dd=max(dd,peak-equity);by_day[t["day"]]=by_day.get(t["day"],0)+t["net_pnl"]
    daily=list(by_day.values());sd=pstdev(daily) if len(daily)>1 else 0.
    return {"trades":len(trades),"wins":len(wins),"losses":len(losses),"win_rate_pct":round(len(wins)/len(trades)*100,2) if trades else 0.,"gross_pnl":round(sum(float(t["gross_pnl"]) for t in trades),2),"net_pnl":round(sum(pnls),2),"costs":round(sum(float(t["costs"]) for t in trades),2),"profit_factor":round(gp/gl,3) if gl else(999. if gp else 0.),"expectancy_per_trade":round(mean(pnls),2) if pnls else 0.,"avg_win":round(mean(wins),2) if wins else 0.,"avg_loss":round(mean(losses),2) if losses else 0.,"max_drawdown":round(dd,2),"max_drawdown_pct":round(dd/cfg.initial_capital*100,2),"return_pct":round((equity-cfg.initial_capital)/cfg.initial_capital*100,2),"sharpe_like":round(mean(daily)/sd*sqrt(252),3) if sd else 0.,"best_day":round(max(by_day.values()),2) if by_day else 0.,"worst_day":round(min(by_day.values()),2) if by_day else 0.}

def run_strategy(snapshots:list[dict[str,Any]],strategy:StrategySpec,cfg:LabConfig|None=None,variant:str="ATM")->dict[str,Any]:
    cfg=cfg or LabConfig();ordered=sorted([dict(s) for s in snapshots if isinstance(s,dict) and _session(s)],key=lambda s:_timestamp(s) or datetime.min.replace(tzinfo=IST));trades=[];i=0
    while i<len(ordered)-1:
        previous=ordered[i-1] if i else None;direction=strategy.signal(ordered[i],previous)
        if direction not in {"BULLISH","BEARISH"}:i+=1;continue
        entry_snap=ordered[i+1];row=_select_option(entry_snap,direction,variant)
        if not row or _f(row.get("volume"))<cfg.min_volume:i+=1;continue
        key=_option_key(row);entry=_fill(row,"BUY")
        if entry<=0:i+=1;continue
        exit_index=min(len(ordered)-1,i+cfg.max_hold_bars);reason="TIME"
        for j in range(i+1,exit_index+1):
            exit_row=_find_fixed(ordered[j],key)
            if not exit_row:continue
            exit_price=_fill(exit_row,"SELL");move=(exit_price-entry)/entry if exit_price>0 else 0.
            if move<=-cfg.stop_pct:exit_index,reason=j,"STOP";break
            if move>=cfg.target_pct:exit_index,reason=j,"TARGET";break
        exit_row=_find_fixed(ordered[exit_index],key)
        if not exit_row:i=exit_index;continue
        exit_price=_fill(exit_row,"SELL")
        if exit_price<=0:i=exit_index;continue
        qty=max(1,cfg.lot_size);gross=(exit_price-entry)*qty;costs=_cost(entry,qty,cfg,"BUY")+_cost(exit_price,qty,cfg,"SELL");dt=_timestamp(ordered[exit_index])
        trades.append({"strategy":strategy.name,"family":strategy.family,"variant":variant,"direction":direction,"strike":key[2],"security_id":key[0],"trading_symbol":key[1],"expiry":key[3],"entry_timestamp":entry_snap.get("timestamp"),"exit_timestamp":ordered[exit_index].get("timestamp"),"day":dt.astimezone(IST).date().isoformat() if dt else "UNKNOWN","entry_price":round(entry,4),"exit_price":round(exit_price,4),"quantity":qty,"gross_pnl":round(gross,2),"costs":round(costs,2),"net_pnl":round(gross-costs,2),"exit_reason":reason})
        i=max(i+1,exit_index)
    return {"strategy":strategy.name,"family":strategy.family,"variant":variant,"metrics":_metrics(trades,cfg),"trades":trades,"research_only":True,"contract_policy":"FIXED_AT_ENTRY","cost_model":"NSE_OPTIONS_2026_CONFIGURABLE"}

def run_single_leg_tournament(snapshots:list[dict[str,Any]],cfg:LabConfig|None=None)->dict[str,Any]:
    cfg=cfg or LabConfig();variants=("ATM","ITM","OTM","D050","D060","D070");results=[run_strategy(snapshots,s,cfg,v) for s in all_strategies() for v in variants];results.sort(key=lambda r:(r["metrics"]["net_pnl"],r["metrics"]["profit_factor"],r["metrics"]["expectancy_per_trade"]),reverse=True)
    return {"schema_version":"post-market-lab-v4","mode":"RAW_LIVE_SESSION_COUNTERFACTUAL","research_only":True,"orders_placed":0,"configuration":asdict(cfg),"strategy_count":len(all_strategies()),"variant_count":len(variants),"tests":len(results),"leaderboard":[{"rank":i+1,"strategy":r["strategy"],"variant":r["variant"],**r["metrics"]} for i,r in enumerate(results)],"results":results}
