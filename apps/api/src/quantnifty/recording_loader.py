from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.historical import canonicalize_snapshot, canonicalize_snapshots
from quantnifty.report_importer import load_report_to_temporary_root

IST = ZoneInfo("Asia/Kolkata")
_AUX_HEADER = re.compile(rb"FILE : (?P<name>analytics\.json|decision\.json)\r\nPATH : (?P<path>[^\r\n]+)\r\n(?P<sep>=+)(?:\r\n|\n)")


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


def _extract_auxiliary_json(report: Path, destination: Path) -> int:
    """Extract analytics/decision JSON omitted by the binary snapshot importer."""
    data = report.read_bytes()
    matches = list(_AUX_HEADER.finditer(data))
    written = 0
    for index, match in enumerate(matches):
        original = match.group("path").decode("utf-8", "replace")
        if "\\data\\snapshots\\" not in original.lower():
            continue
        relative = Path(*original.replace("\\", "/").split("/data/snapshots/", 1)[1].split("/"))
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(data)
        framed = data[content_start:content_end]
        separator = re.search(rb"(?:\r\n){1,3}={10,}\r\n(?:FILE :|$)", framed)
        if separator:
            framed = framed[:separator.start()]
        content = framed.strip(b"\r\n=")
        try:
            json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content + b"\n")
        written += 1
    return written


def _parse_signal_repr(value: Any) -> dict[str, Any]:
    raw = str(value or "")
    match = re.search(r"Signal\(name='([^']*)',\s*confidence=([-+]?\d+(?:\.\d+)?)\)", raw)
    if not match:
        return {}
    confidence = _number(match.group(2))
    return {"name": match.group(1), "confidence": int(confidence) if confidence.is_integer() else confidence}


def _parse_validation_repr(value: Any) -> dict[str, Any]:
    raw = str(value or "")
    match = re.search(r"ValidationResult\(valid=(True|False),\s*grade='([^']*)',\s*confidence=([-+]?\d+(?:\.\d+)?),\s*risk_multiplier=([-+]?\d+(?:\.\d+)?),\s*warnings=(\[[^]]*\])\)", raw)
    if not match:
        return {}
    confidence = _number(match.group(3))
    risk_multiplier = _number(match.group(4))
    return {
        "valid": match.group(1) == "True",
        "grade": match.group(2),
        "confidence": int(confidence) if confidence.is_integer() else confidence,
        "risk_multiplier": risk_multiplier,
        "warnings": [],
    }


def _parse_trade_repr(value: Any) -> dict[str, Any]:
    raw = str(value or "")
    if not raw.startswith("Trade("):
        return {}
    result: dict[str, Any] = {}
    for field, token in re.findall(r"(contract|option_type|strike|entry|stop_loss|target1|target2|risk_reward)=((?:'[^']*')|(?:[^,\)]+))", raw):
        token = token.strip()
        if token.startswith("'") and token.endswith("'"):
            result[field] = token[1:-1]
        else:
            result[field] = _number(token)
    return result


def _normalize_recorded_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Normalize recorder repr strings into stable comparison-only evidence."""
    if not decision:
        return {}
    out = dict(decision)
    signal = _parse_signal_repr(out.get("signal"))
    if signal:
        out["signal"] = signal
    validation = _parse_validation_repr(out.get("validation"))
    if validation:
        out["validation"] = validation
    trade = _parse_trade_repr(out.get("trade"))
    if trade:
        out["trade"] = trade
    return out


def _recorded_intelligence(analytics: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    dealer = analytics.get("dealer") or {}
    dealer_flow = analytics.get("dealer_flow") or {}
    liquidity = analytics.get("liquidity") or {}
    gamma_flip = analytics.get("gamma_flip") or {}
    oi_flow = analytics.get("oi_flow") or {}
    oi_summary = oi_flow.get("summary") or {}
    iv_skew = analytics.get("iv_skew") or {}
    expected = analytics.get("expected_move") or {}
    market_structure = analytics.get("market_structure") or {}
    smart = analytics.get("smart_strike") or {}
    option_type = str(smart.get("option_type") or "").upper()
    strike = _number(smart.get("strike"))
    selected = None
    if strike and option_type in {"CE", "PE"}:
        selected = next((r for r in rows if abs(_number(r.get("strike")) - strike) < 0.001 and str(r.get("side")) == option_type), None)
    selection = dict(smart) if smart else {}
    if selected:
        selection["security_id"] = selected.get("security_id")
        selection["side"] = option_type
    elif option_type:
        selection["side"] = option_type
    smart_reasons = smart.get("reasons") or []
    liquidity_score = 100.0 if "Good Liquidity" in smart_reasons else 0.0
    avg_call_iv = _number(iv_skew.get("average_call_iv"))
    avg_put_iv = _number(iv_skew.get("average_put_iv"))
    return {
        "bias": str(market_structure.get("bias") or "NEUTRAL").upper(),
        "structure": str(market_structure.get("structure") or "UNKNOWN"),
        "gex": _number(dealer.get("total_gex")),
        "dex": _number(dealer_flow.get("total_dex")),
        "vanna_proxy": _number(dealer_flow.get("total_vanna")),
        "gamma_flip": gamma_flip.get("gamma_flip"),
        "atm_iv": (avg_call_iv + avg_put_iv) / 2.0 if avg_call_iv or avg_put_iv else 0.0,
        "iv_skew": iv_skew.get("iv_skew"),
        "expected_move": {"move": _number(expected.get("expected_move")), "lower": expected.get("lower"), "upper": expected.get("upper")},
        "recorded_oi_flow_bias": str(oi_summary.get("market_bias") or "NEUTRAL").upper(),
        "liquidity_score": liquidity_score,
        "intelligence": {"market_state": {"state": str(dealer.get("market_mode") or "UNKNOWN")}},
        "strike_selection": [selection] if selection else [],
        "recorded_analytics": analytics,
        "recorded_liquidity": liquidity,
    }


def load_snapshot_bundle(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    runtime_path, option_path, greeks_path = root / "runtime.json", root / "option_chain.parquet", root / "greeks.parquet"
    for path in (runtime_path, option_path, greeks_path):
        if not path.is_file():
            raise ValueError(f"incomplete snapshot bundle: missing {path.name}")
    runtime = _read_json(runtime_path)
    options = _read_parquet(option_path)
    greeks = _read_parquet(greeks_path)
    analytics_path = root / "analytics.json"
    analytics = _read_json(analytics_path) if analytics_path.is_file() else {}
    decision_path = root / "decision.json"
    decision = _read_json(decision_path) if decision_path.is_file() else {}
    required = {"Strike", "CE_ID", "CE_LTP", "CE_OI", "CE_VOLUME", "PE_ID", "PE_LTP", "PE_OI", "PE_VOLUME"}
    missing = required - set(options[0]) if options else required
    if missing:
        raise ValueError(f"option_chain.parquet missing columns: {', '.join(sorted(missing))}")
    if not greeks or "Strike" not in greeks[0]:
        raise ValueError("greeks.parquet missing Strike column")
    greek_by_strike = {_number(row.get("Strike")): row for row in greeks}
    rows: list[dict[str, Any]] = []
    for row in options:
        strike = _number(row.get("Strike"))
        greek = greek_by_strike.get(strike, {})
        for side in ("CE", "PE"):
            prefix = side + "_"
            leg = {"strike": strike, "side": side, "security_id": _identifier(row.get(prefix + "ID")), "last_price": _number(row.get(prefix + "LTP")), "oi": _number(row.get(prefix + "OI")), "volume": _number(row.get(prefix + "VOLUME"))}
            for field in ("IV", "DELTA", "GAMMA", "THETA", "VEGA", "RHO"):
                column = prefix + field
                if column in greek and greek.get(column) is not None:
                    leg[field.lower()] = _number(greek.get(column))
            rows.append(leg)
    snapshot = {"timestamp": _timestamp(str(runtime.get("timestamp", ""))), "spot": _number(runtime.get("spot")), "expiry": str(runtime.get("expiry") or ""), "symbol": str(runtime.get("symbol") or "NIFTY"), "regime": str(runtime.get("regime") or ""), "runtime_status": str(runtime.get("runtime_status") or ""), "recording_path": str(root), "option_chain": rows, "data_integrity": "RECORDED_HISTORICAL"}
    snapshot.update(_recorded_intelligence(analytics, rows))
    snapshot["recorded_decision"] = _normalize_recorded_decision(decision)
    return canonicalize_snapshot(snapshot, "RECORDED_HISTORICAL")


def _load_directory(base: Path) -> list[dict[str, Any]]:
    bundles = sorted({path.parent for path in base.rglob("runtime.json")})
    if not bundles:
        raise ValueError(f"no recorded snapshot bundles found under {base}")
    return canonicalize_snapshots([load_snapshot_bundle(path) for path in bundles], "RECORDED_HISTORICAL")


def load_recording(root: str | Path) -> list[dict[str, Any]]:
    base = Path(root)
    if not base.exists():
        raise ValueError(f"recording root does not exist: {base}")
    if base.is_file():
        if base.suffix.lower() != ".txt":
            raise ValueError(f"recording path must be a snapshot directory or .txt recorder export: {base}")
        with load_report_to_temporary_root(base) as temp:
            _extract_auxiliary_json(base, Path(temp.name))
            return _load_directory(Path(temp))
    return _load_directory(base)
