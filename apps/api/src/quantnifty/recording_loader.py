from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from quantnifty.historical import canonicalize_snapshot, canonicalize_snapshots

IST = ZoneInfo("Asia/Kolkata")


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _timestamp(value: str) -> str:
    dt = datetime.strptime(value, "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
    return dt.isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read {path.name}: {exc}") from exc


def _read_parquet(path: Path):
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise RuntimeError("pyarrow is required to ingest recorded Parquet snapshots") from exc
    try:
        return parquet.read_table(path).to_pandas()
    except Exception as exc:
        raise ValueError(f"unable to decode {path.name}: {exc}") from exc


def load_snapshot_bundle(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    runtime_path = root / "runtime.json"
    option_path = root / "option_chain.parquet"
    greeks_path = root / "greeks.parquet"
    for path in (runtime_path, option_path, greeks_path):
        if not path.is_file():
            raise ValueError(f"incomplete snapshot bundle: missing {path.name}")
    runtime = _read_json(runtime_path)
    options = _read_parquet(option_path)
    greeks = _read_parquet(greeks_path)
    required_options = {"Strike", "CE_ID", "CE_LTP", "CE_OI", "CE_VOLUME", "PE_ID", "PE_LTP", "PE_OI", "PE_VOLUME"}
    missing = required_options - set(options.columns)
    if missing:
        raise ValueError(f"option_chain.parquet missing columns: {', '.join(sorted(missing))}")
    if "Strike" not in greeks.columns:
        raise ValueError("greeks.parquet missing Strike column")
    greek_by_strike = {float(row["Strike"]): row for _, row in greeks.iterrows()}
    rows: list[dict[str, Any]] = []
    for _, row in options.iterrows():
        strike = _number(row["Strike"])
        greek = greek_by_strike.get(strike, {})
        for side in ("CE", "PE"):
            prefix = side + "_"
            leg = {
                "strike": strike,
                "side": side,
                "security_id": str(row[prefix + "ID"]),
                "last_price": _number(row[prefix + "LTP"]),
                "oi": _number(row[prefix + "OI"]),
                "volume": _number(row[prefix + "VOLUME"]),
            }
            for field in ("IV", "DELTA", "GAMMA", "THETA", "VEGA", "RHO"):
                column = prefix + field
                if column in greeks.columns:
                    leg[field.lower()] = _number(greek.get(column))
            rows.append(leg)
    snapshot = {
        "timestamp": _timestamp(str(runtime.get("timestamp", ""))),
        "spot": _number(runtime.get("spot")),
        "expiry": str(runtime.get("expiry") or ""),
        "symbol": str(runtime.get("symbol") or "NIFTY"),
        "regime": str(runtime.get("regime") or ""),
        "runtime_status": str(runtime.get("runtime_status") or ""),
        "recording_path": str(root),
        "option_chain": rows,
        "data_integrity": "RECORDED_HISTORICAL",
    }
    return canonicalize_snapshot(snapshot, "RECORDED_HISTORICAL")


def load_recording(root: str | Path) -> list[dict[str, Any]]:
    base = Path(root)
    if not base.exists():
        raise ValueError(f"recording root does not exist: {base}")
    bundles = sorted({path.parent for path in base.rglob("runtime.json")})
    if not bundles:
        raise ValueError(f"no recorded snapshot bundles found under {base}")
    snapshots = [load_snapshot_bundle(path) for path in bundles]
    return canonicalize_snapshots(snapshots, "RECORDED_HISTORICAL")
