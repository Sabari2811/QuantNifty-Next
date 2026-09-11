from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.historical import canonicalize_snapshots

IST = ZoneInfo("Asia/Kolkata")


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _find_column(headers: list[str], *aliases: str) -> str | None:
    normalized = {_norm(h): h for h in headers}
    for alias in aliases:
        hit = normalized.get(_norm(alias))
        if hit:
            return hit
    return None


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _timestamp(row: dict[str, Any], columns: dict[str, str]) -> str:
    raw = row.get(columns["timestamp"], "")
    if isinstance(raw, datetime):
        dt = raw
    else:
        text = str(raw).strip()
        formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
        )
        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"invalid timestamp: {text!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.isoformat()


def _columns(headers: list[str]) -> dict[str, str]:
    def required(name: str, *aliases: str) -> str:
        value = _find_column(headers, name, *aliases)
        if value is None:
            raise ValueError(f"historical options CSV is missing required column: {name}")
        return value

    return {
        "timestamp": required("timestamp", "datetime", "date_time", "date", "time"),
        "strike": required("strike", "strike_price"),
        "option_type": required("option_type", "right", "type", "side", "ce_pe"),
        "close": required("close", "ltp", "last_price", "market_price"),
        "volume": required("volume", "vol"),
        "oi": required("open_interest", "oi", "openinterest"),
    } | {
        key: value
        for key, aliases in {
            "open": ("open",),
            "high": ("high",),
            "low": ("low",),
            "bid": ("bid", "best_bid"),
            "ask": ("ask", "best_ask"),
            "expiry": ("expiry", "expiry_date", "expiration"),
            "symbol": ("symbol", "trading_symbol", "instrument"),
            "spot": ("spot", "spot_price", "underlying", "underlying_price"),
        }.items()
        if (value := _find_column(headers, *aliases)) is not None
    }


def _side(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"CE", "C", "CALL", "CALLS"}:
        return "CE"
    if text in {"PE", "P", "PUT", "PUTS"}:
        return "PE"
    if text.endswith("CE"):
        return "CE"
    if text.endswith("PE"):
        return "PE"
    raise ValueError(f"unsupported option side: {value!r}")


def _security_id(row: dict[str, Any], columns: dict[str, str], side: str, strike: float, expiry: str) -> str:
    for key in ("security_id", "securityid", "token", "instrument_token"):
        column = _find_column(list(row.keys()), key)
        if column and str(row.get(column) or "").strip():
            return str(row[column]).strip()
    symbol = str(row.get(columns.get("symbol", ""), "")).strip()
    return f"HIST:{symbol or 'NIFTY'}:{expiry}:{strike:g}:{side}"


def load_option_csv(path: str | Path, provenance: str = "RECORDED_HISTORICAL") -> list[dict[str, Any]]:
    """Load generic 1-minute NIFTY option CSV into the canonical snapshot contract.

    The adapter is intentionally permissive about provider column names but strict
    about the fields V3 needs for option P&L: timestamp, strike, CE/PE, close/LTP,
    volume and open interest. Bid/ask, expiry and spot are retained when supplied.
    Missing Greeks are left absent rather than fabricated.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f"historical options CSV does not exist: {file_path}")
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        if not headers:
            raise ValueError("historical options CSV is empty")
        columns = _columns(headers)
        grouped: dict[str, dict[str, Any]] = {}
        for row in reader:
            timestamp = _timestamp(row, columns)
            strike = _number(row.get(columns["strike"]))
            side = _side(row.get(columns["option_type"]))
            if strike <= 0:
                raise ValueError(f"invalid strike for {timestamp}: {row.get(columns['strike'])!r}")
            expiry = str(row.get(columns.get("expiry", ""), "") or "").strip()
            spot = _number(row.get(columns.get("spot", ""))) if columns.get("spot") else 0.0
            if not spot:
                symbol_text = str(row.get(columns.get("symbol", ""), "")) if columns.get("symbol") else ""
                spot = _number(row.get("underlying_price")) if "underlying_price" in row else 0.0
            leg = {
                "strike": strike,
                "side": side,
                "security_id": _security_id(row, columns, side, strike, expiry),
                "last_price": _number(row.get(columns["close"])),
                "oi": _number(row.get(columns["oi"])),
                "volume": _number(row.get(columns["volume"])),
            }
            for field in ("open", "high", "low", "bid", "ask"):
                if columns.get(field):
                    value = _number(row.get(columns[field]))
                    if value > 0:
                        leg[field] = value
            if columns.get("symbol"):
                leg["trading_symbol"] = str(row.get(columns["symbol"]) or "").strip()
            key = timestamp
            snapshot = grouped.setdefault(key, {"timestamp": timestamp, "spot": spot, "option_chain": [], "data_integrity": provenance})
            if spot > 0:
                snapshot["spot"] = spot
            if expiry:
                snapshot["expiry"] = expiry
            snapshot["option_chain"].append(leg)

    snapshots = list(grouped.values())
    if not snapshots:
        return []
    for snapshot in snapshots:
        if _number(snapshot.get("spot")) <= 0:
            raise ValueError(f"snapshot {snapshot['timestamp']} is missing a positive NIFTY spot")
        if not snapshot.get("expiry"):
            raise ValueError(f"snapshot {snapshot['timestamp']} is missing option expiry")
    return canonicalize_snapshots(snapshots, provenance)
