from __future__ import annotations
import argparse,json
from pathlib import Path
from quantnifty.learning_store import load_snapshots
from .runner import LabConfig,run_single_leg_tournament
from .multi_leg import run_multi_leg_tournament
from .robustness import add_monte_carlo,slippage_stress

def main()->None:
    p=argparse.ArgumentParser(description="Run the isolated post-market research lab on raw stored snapshots.")
    p.add_argument("day",help="IST trading day, e.g. 2026-09-15");p.add_argument("--capital",type=float,default=100000.);p.add_argument("--lot-size",type=int,default=65);p.add_argument("--max-hold-bars",type=int,default=8);p.add_argument("--stop-pct",type=float,default=.0075);p.add_argument("--target-pct",type=float,default=.015);p.add_argument("--slippage-bps",type=float,default=5.);p.add_argument("--output",default=None)
    a=p.parse_args();snapshots=load_snapshots(a.day)
    if not snapshots:
        print(json.dumps({"status":"NO_RAW_SNAPSHOTS","day":a.day,"research_only":True},indent=2));return
    cfg=LabConfig(initial_capital=a.capital,lot_size=a.lot_size,max_hold_bars=a.max_hold_bars,stop_pct=a.stop_pct,target_pct=a.target_pct,slippage_bps=a.slippage_bps)
    single=run_single_leg_tournament(snapshots,cfg);multi=run_multi_leg_tournament(snapshots,cfg);add_monte_carlo(single,cfg,5000);add_monte_carlo(multi,cfg,5000)
    report={"schema_version":"post-market-lab-day-v2","status":"OK","day":a.day,"raw_snapshot_count":len(snapshots),"source":"quantnifty.learning_store.load_snapshots","mode":"RAW_LIVE_SESSION_COUNTERFACTUAL","research_only":True,"orders_placed":0,"single_leg":single,"multi_leg":multi,"slippage_stress":slippage_stress(snapshots,cfg)}
    text=json.dumps(report,indent=2,default=str)
    if a.output:Path(a.output).write_text(text,encoding="utf-8")
    print(text)
if __name__=="__main__":main()
