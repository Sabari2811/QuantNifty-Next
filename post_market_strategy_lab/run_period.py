from __future__ import annotations
import argparse,json
from collections import defaultdict
from pathlib import Path
from quantnifty.learning_store import load_snapshots
from .multi_leg import run_multi_leg_tournament
from .robustness import add_monte_carlo,slippage_stress,walk_forward_validation
from .runner import LabConfig,run_single_leg_tournament

def _combine(reports:list[dict],initial_capital:float)->list[dict]:
    buckets=defaultdict(list)
    for report in reports:
        for r in report.get("results",[]):buckets[(r["strategy"],r.get("variant",""))].extend(r.get("trades",[]))
    rows=[]
    for (strategy,variant),trades in buckets.items():
        pnl=sum(float(t.get("net_pnl",0)) for t in trades);gross=sum(float(t.get("gross_pnl",0)) for t in trades);costs=sum(float(t.get("costs",0)) for t in trades);wins=sum(1 for t in trades if float(t.get("net_pnl",0))>0);losses=sum(1 for t in trades if float(t.get("net_pnl",0))<0);gp=sum(float(t.get("net_pnl",0)) for t in trades if float(t.get("net_pnl",0))>0);gl=abs(sum(float(t.get("net_pnl",0)) for t in trades if float(t.get("net_pnl",0))<0));equity=initial_capital;peak=equity;dd=0.
        for t in sorted(trades,key=lambda x:x.get("exit_timestamp","")):equity+=float(t.get("net_pnl",0));peak=max(peak,equity);dd=max(dd,peak-equity)
        rows.append({"strategy":strategy,"variant":variant,"trades":len(trades),"wins":wins,"losses":losses,"win_rate_pct":round(wins/len(trades)*100,2) if trades else 0,"gross_pnl":round(gross,2),"net_pnl":round(pnl,2),"costs":round(costs,2),"profit_factor":round(gp/gl,3) if gl else(999 if gp else 0),"expectancy_per_trade":round(pnl/len(trades),2) if trades else 0,"max_drawdown":round(dd,2),"return_pct":round((equity-initial_capital)/initial_capital*100,2)})
    return sorted(rows,key=lambda x:(x["net_pnl"],x["profit_factor"]),reverse=True)

def main()->None:
    ap=argparse.ArgumentParser(description="Run QuantNifty post-market research over stored raw sessions only.");ap.add_argument("days",help="Comma-separated IST trading days, oldest first");ap.add_argument("--capital",type=float,default=100000.);ap.add_argument("--lot-size",type=int,default=65);ap.add_argument("--max-hold-bars",type=int,default=8);ap.add_argument("--stop-pct",type=float,default=.0075);ap.add_argument("--target-pct",type=float,default=.015);ap.add_argument("--slippage-bps",type=float,default=5.);ap.add_argument("--output")
    a=ap.parse_args();days=[x.strip() for x in a.days.split(",") if x.strip()];cfg=LabConfig(initial_capital=a.capital,lot_size=a.lot_size,max_hold_bars=a.max_hold_bars,stop_pct=a.stop_pct,target_pct=a.target_pct,slippage_bps=a.slippage_bps);daily=[];loaded={};raw={}
    for day in days:
        snaps=load_snapshots(day);loaded[day]=len(snaps)
        if not snaps:continue
        raw[day]=snaps;single=run_single_leg_tournament(snaps,cfg);multi=run_multi_leg_tournament(snaps,cfg);add_monte_carlo(single,cfg,2000);add_monte_carlo(multi,cfg,2000);daily.append({"day":day,"single":single,"multi":multi})
    if not daily:report={"status":"NO_RAW_SNAPSHOTS","days":days,"loaded_counts":loaded,"research_only":True}
    else:
        split=max(1,int(len(daily)*.7));is_days=daily[:split];oos_days=daily[split:]
        report={"schema_version":"post-market-lab-period-v2","status":"OK","mode":"RAW_LIVE_SESSION_COUNTERFACTUAL","research_only":True,"orders_placed":0,"days_requested":days,"days_with_data":[d["day"] for d in daily],"raw_snapshot_counts":loaded,"in_sample_days":[d["day"] for d in is_days],"oos_days":[d["day"] for d in oos_days],"in_sample_leaderboard":_combine([d["single"] for d in is_days],cfg.initial_capital),"oos_leaderboard":_combine([d["single"] for d in oos_days],cfg.initial_capital) if oos_days else [],"daily_reports":daily,"walk_forward":walk_forward_validation(raw,cfg,min_train_days=min(5,max(1,len(raw)//3))),"slippage_stress_last_session":slippage_stress(raw[daily[-1]["day"]],cfg)}
    text=json.dumps(report,indent=2,default=str)
    if a.output:Path(a.output).write_text(text,encoding="utf-8")
    print(text)
if __name__=="__main__":main()
