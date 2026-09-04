import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from quantnifty.recording_loader import load_recording, load_snapshot_bundle


def write_bundle(root):
    root.mkdir(parents=True)
    (root / "runtime.json").write_text(json.dumps({
        "timestamp": "04-Aug-2026 13:02:21",
        "spot": 24383.6,
        "symbol": "NIFTY",
        "expiry": "08/04/2026 14:00",
        "regime": "RANGE",
        "runtime_status": "RUNNING",
    }), encoding="utf-8")
    option = pd.DataFrame([{
        "Strike": 24400, "CE_ID": 1, "CE_LTP": 100.0, "CE_OI": 1000, "CE_VOLUME": 5000,
        "PE_ID": 2, "PE_LTP": 120.0, "PE_OI": 1100, "PE_VOLUME": 5100,
    }])
    greeks = pd.DataFrame([{
        "Strike": 24400, "CE_IV": 0.10, "CE_DELTA": 0.48, "CE_GAMMA": 0.02, "CE_THETA": -0.01, "CE_VEGA": 0.03,
        "PE_IV": 0.11, "PE_DELTA": -0.52, "PE_GAMMA": 0.02, "PE_THETA": -0.01, "PE_VEGA": 0.03,
    }])
    pq.write_table(pa.Table.from_pandas(option, preserve_index=False), root / "option_chain.parquet")
    pq.write_table(pa.Table.from_pandas(greeks, preserve_index=False), root / "greeks.parquet")


def test_load_snapshot_bundle_builds_canonical_rows(tmp_path):
    root = tmp_path / "000001_13-02-21"
    write_bundle(root)
    snapshot = load_snapshot_bundle(root)
    assert snapshot["data_integrity"] == "RECORDED_HISTORICAL"
    assert snapshot["historical_snapshot"] is True
    assert snapshot["timestamp"].endswith("+05:30")
    assert {row["side"] for row in snapshot["option_chain"]} == {"CE", "PE"}
    assert snapshot["option_chain"][0]["gamma"] == 0.02


def test_load_recording_sorts_bundles(tmp_path):
    root = tmp_path / "snapshots"
    write_bundle(root / "b")
    write_bundle(root / "a")
    snapshots = load_recording(root)
    assert len(snapshots) == 2
    assert all(s["data_integrity"] == "RECORDED_HISTORICAL" for s in snapshots)
