from __future__ import annotations
import random
from dataclasses import replace
from typing import Any
from .runner import LabConfig,run_single_leg_tournament
from .multi_leg import run_multi_leg_tournament

def monte_carlo(pnls:list[float],initial_capital:float,simulations:int=5000,seed:int=42)->dict[str,Any]:
    if not pnls:return {"simulations":0,"status":"NO_TRADES"}
    rng=random.Random(seed);dds=[];ending=[];ruin=0
    for _ in range(max(1,simulations)):
        seq=list(pnls);rng.shuffle(seq);equity=initial_capital;peak=equity;dd=0.
        for p in seq:
            equity+=p;peak=max(peak,equity);dd=max(dd,peak-equity)
            if equity<=0:ruin+=1;break
        dds.append(dd);ending.append(equity)
    dds.sort();ending.sort();pick=lambda a,p:a[min(len(a)-1,max(0,int((len(a)-1)*p)))]
    return {"simulations":len(dds),"seed":seed,"median_ending_capital":round(pick(ending,.5),2),"p05_ending_capital":round(pick(ending,.05),2),"p95_ending_capital":round(pick(ending,.95),2),"median_max_drawdown":round(pick(dds,.5),2),"p95_max_drawdown":round(pick(dds,.95),2),"risk_of_ruin_pct":round(ruin/len(dds)*100,3)}

def slippage_stress(snapshots:list[dict[str,Any]],cfg:LabConfig|None=None,bps:tuple[float,...]=(0,5,10,20))->dict[str,Any]:
    cfg=cfg or LabConfig();runs=[]
    for x in bps:
        c=replace(cfg,slippage_bps=float(x));single=run_single_leg_tournament(snapshots,c);multi=run_multi_leg_tournament(snapshots,c);runs.append({"slippage_bps":x,"single_leg_top5":single["leaderboard"][:5],"multi_leg":multi["leaderboard"]})
    return {"stress_type":"slippage_bps","runs":runs}

def robustness_gate(metrics:dict[str,Any],min_trades:int=20)->dict[str,Any]:
    checks={"minimum_trades":metrics.get("trades",0)>=min_trades,"positive_expectancy":metrics.get("expectancy_per_trade",0)>0,"profit_factor_gt_1":metrics.get("profit_factor",0)>1,"positive_net_pnl":metrics.get("net_pnl",0)>0}
    return {"passed":all(checks.values()),"checks":checks}

def add_monte_carlo(report:dict[str,Any],cfg:LabConfig|None=None,simulations:int=5000)->dict[str,Any]:
    cfg=cfg or LabConfig()
    for r in report.get("results",[]):
        r["monte_carlo"]=monte_carlo([float(t.get("net_pnl",0)) for t in r.get("trades",[])],cfg.initial_capital,simulations);r["robustness_gate"]=robustness_gate(r.get("metrics",{}))
    return report

def walk_forward_validation(days_to_snapshots:dict[str,list[dict[str,Any]]],cfg:LabConfig|None=None,min_train_days:int=5)->dict[str,Any]:
    """Chronological forward evaluation. No future session is used to produce a test-day result."""
    cfg=cfg or LabConfig();days=sorted(days_to_snapshots);folds=[]
    for idx,day in enumerate(days):
        if idx<min_train_days:continue
        test=run_single_leg_tournament(days_to_snapshots[day],cfg);multi=run_multi_leg_tournament(days_to_snapshots[day],cfg)
        folds.append({"test_day":day,"prior_session_count":idx,"single_leg_leaderboard":test["leaderboard"],"multi_leg_leaderboard":multi["leaderboard"]})
    return {"method":"CHRONOLOGICAL_FORWARD_VALIDATION","min_train_days":min_train_days,"folds":folds,"note":"Strategies are fixed-rule in this lab; prior sessions are validation context, not parameter-fitting data."}
