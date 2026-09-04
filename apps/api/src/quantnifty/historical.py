from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

CANONICAL_PROVENANCE = {"RECORDED_HISTORICAL", "LIVE_PROVIDER"}
REQUIRED_SNAPSHOT_KEYS = ("timestamp", "spot", "option_chain")
REQUIRED_LEG_KEYS = ("strike", "side", "security_id", "last_price", "oi", "volume")


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"expected numeric value, got {value!r}") from exc


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("timestamp is required")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {raw!r}") from exc
    return dt.isoformat()


def canonicalize_snapshot(raw: dict[str, Any], provenance: str = "RECORDED_HISTORICAL") -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("snapshot must be an object")
    missing = [key for key in REQUIRED_SNAPSHOT_KEYS if key not in raw]
    if missing:
        raise ValueError(f"snapshot missing required fields: {', '.join(missing)}")
    if provenance not in CANONICAL_PROVENANCE:
        raise ValueError(f"unsupported provenance: {provenance}")
    rows = raw.get("option_chain")
    if not isinstance(rows, list) or not rows:
        raise ValueError("option_chain must be a non-empty list")
    canonical_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"option_chain[{index}] must be an object")
        missing_leg = [key for key in REQUIRED_LEG_KEYS if key not in row]
        if missing_leg:
            raise ValueError(f"option_chain[{index}] missing required fields: {', '.join(missing_leg)}")
        side = str(row.get("side", "")).upper()
        if side not in {"CE", "PE"}:
            raise ValueError(f"option_chain[{index}] side must be CE or PE")
        item = dict(row)
        item.update({
            "strike": _float(row["strike"]),
            "side": side,
            "security_id": str(row["security_id"]),
            "last_price": _float(row["last_price"]),
            "oi": _float(row["oi"]),
            "volume": _float(row["volume"]),
        })
        for field in ("previous_oi", "previous_close", "bid", "ask", "bid_qty", "ask_qty", "iv", "delta", "gamma", "theta", "vega"):
            if field in item and item[field] is not None:
                item[field] = _float(item[field])
        canonical_rows.append(item)
    canonical_rows.sort(key=lambda row: (row["strike"], 0 if row["side"] == "CE" else 1, row["security_id"]))
    out = dict(raw)
    out.update({
        "timestamp": _timestamp(raw["timestamp"]),
        "spot": _float(raw["spot"]),
        "option_chain": canonical_rows,
        "rows": len(canonical_rows),
        "data_integrity": provenance,
        "historical_snapshot": provenance == "RECORDED_HISTORICAL",
    })
    return out


def canonicalize_snapshots(snapshots: Iterable[dict[str, Any]], provenance: str = "RECORDED_HISTORICAL") -> list[dict[str, Any]]:
    result = [canonicalize_snapshot(snapshot, provenance) for snapshot in snapshots]
    result.sort(key=lambda snapshot: snapshot["timestamp"])
    if len({snapshot["timestamp"] for snapshot in result}) != len(result):
        raise ValueError("duplicate snapshot timestamps are not allowed")
    return result


def historical_data_status(snapshots: Iterable[dict[str, Any]]) -> dict[str, Any]:
    values = list(snapshots)
    if not values:
        return {"status": "NOT_PROVIDED", "observations": 0, "provenance": None}
    provenance = {str(value.get("data_integrity") or "UNKNOWN") for value in values if isinstance(value, dict)}
    if provenance == {"RECORDED_HISTORICAL"}:
        status = "VALID_HISTORICAL"
    elif "RECORDED_HISTORICAL" in provenance:
        status = "MIXED_PROVENANCE"
    else:
        status = "NON_HISTORICAL"
    return {"status": status, "observations": len(values), "provenance": sorted(provenance)}
