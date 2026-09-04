from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.historical import canonicalize_snapshot, canonicalize_snapshots

IST = ZoneInfo("Asia/Kolkata")


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _identifier(value: Any) -> str:
    number = _number(value)
    return str(int(number)) if number.is_integer() else str(value)


def _timestamp(value: str) -> str:
    dt = datetime.strptime(value, "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
    return dt.isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read {path.name}: {exc}") from exc


def _read_parquet(path: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise RuntimeError("pyarrow is required to ingest recorded Parquet snapshots") from exc
    try:
        return parquet.read_table(path).to_pylist()
    except Exception as exc:
        raise ValueError(f"unable to decode {path.name}: {exc}") from exc


def load_snapshot_bundle(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    runtime_path, option_path, greeks_path = root / "runtime.json", root / "option_chain.parquet", root / "greeks.parquet"
    for path in (runtime_path, option_path, greeks_path):
        if not path.is_file():
            raise ValueError(f"incomplete snapshot bundle: missing {path.name}")
    runtime = _read_json(runtime_path)
    options = _read_parquet(option_path)
    greeks = _read_parquet(greeks_path)
    required = {"Strike", "CE_ID", "CE_LTP", "CE_OI", "CE_VOLUME", "PE_ID", "PE_LTP", "PE_OI", "PE_VOLUME"}
    missing = required - set(options[0]) if options else required
    if missing:
        raise ValueError(f"option_chain.parquet missing columns: {', '.join(sorted(missing))}")
    if not greeks or "Strike" not in greeks[0]:
        raise ValueError("greeks.parquet missing Strike column")
    greek_by_strike = {_number(row.get("Strike")): row for row in greeks}
    rows: list[dict[str, Any]] = []
    for row in options:
        strike = _number(row.get("Strike")); greek = greek_by_strike.get(strike, {})
        for side in ("CE", "PE"):
            prefix = side + "_"
            leg = {"strike": strike, "side": side, "security_id": _identifier(row.get(prefix + "ID")), "last_price": _number(row.get(prefix + "LTP")), "oi": _number(row.get(prefix + "OI")), "volume": _number(row.get(prefix + "VOLUME"))}
            for field in ("IV", "DELTA", "GAMMA", "THETA", "VEGA", "RHO"):
                column = prefix + field
                if column in greek and greek.get(column) is not None:
                    leg[field.lower()] = _number(greek.get(column))
            rows.append(leg)
    snapshot = {"timestamp": _timestamp(str(runtime.get("timestamp", ""))), "spot": _number(runtime.get("spot")), "expiry": str(runtime.get("expiry") or ""), "symbol": str(runtime.get("symbol") or "NIFTY"), "regime": str(runtime.get("regime") or ""), "runtime_status": str(runtime.get("runtime_status") or ""), "recording_path": str(root), "option_chain": rows, "data_integrity": "RECORDED_HISTORICAL"}
    return canonicalize_snapshot(snapshot, "RECORDED_HISTORICAL")


def load_recording(root: str | Path) -> list[dict[str, Any]]:
    base = Path(root)
    if not base.exists():
        raise ValueError(f"recording root does not exist: {base}")
    bundles = sorted({path.parent for path in base.rglob("runtime.json")})
    if not bundles:
        raise ValueError(f"no recorded snapshot bundles found under {base}")
    return canonicalize_snapshots([load_snapshot_bundle(path) for path in bundles], "RECORDED_HISTORICAL")
