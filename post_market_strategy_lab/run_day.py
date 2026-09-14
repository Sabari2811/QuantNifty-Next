from __future__ import annotations

import argparse
import json
from pathlib import Path

from quantnifty.learning_store import load_snapshots

from .runner import LabConfig, run_single_leg_tournament


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the standalone post-market strategy tournament on stored raw snapshots.")
    parser.add_argument("day", help="IST trading day, e.g. 2026-09-15")
    parser.add_argument("--capital", type=float, default=100000.0)
    parser.add_argument("--lot-size", type=int, default=65)
    parser.add_argument("--max-hold-bars", type=int, default=8)
    parser.add_argument("--stop-pct", type=float, default=0.0075)
    parser.add_argument("--target-pct", type=float, default=0.015)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--output", default=None, help="Optional JSON output path")
    args = parser.parse_args()

    snapshots = load_snapshots(args.day)
    if not snapshots:
        print(json.dumps({"status": "NO_RAW_SNAPSHOTS", "day": args.day, "research_only": True}, indent=2))
        return

    cfg = LabConfig(
        initial_capital=args.capital,
        lot_size=args.lot_size,
        max_hold_bars=args.max_hold_bars,
        stop_pct=args.stop_pct,
        target_pct=args.target_pct,
        slippage_bps=args.slippage_bps,
    )
    report = run_single_leg_tournament(snapshots, cfg)
    report["day"] = args.day
    report["raw_snapshot_count"] = len(snapshots)
    report["source"] = "learning_store.load_snapshots"

    text = json.dumps(report, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
