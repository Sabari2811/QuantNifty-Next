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
_AUX_HEADER = re.compile(rb"FILE : (analytics\\.json|decision\\.json)\\r\\nPATH : ([^\\r\\n]+)\\r\\n=+(?:\\r\\n|\\n)")


def _number(value: Any) -> float:
    try: return float(value)
    except (TypeError, ValueError): return 0.0


def _identifier(value: Any) -> str:
    n = _number(value); return str(int(n)) if n.is_integer() else str(value)


def _timestamp(value: str) -> str:
    return datetime.strptime(value, "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ValueError(f"unable to read {path.name}: {exc}") from exc


def _read_parquet(path: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as parquet
        return parquet.read_table(path).to_pylist()
    except ImportError as exc: raise RuntimeError("pyarrow is required to ingest recorded Parquet snapshots") from exc
    except Exception as exc: raise ValueError(f"unable to decode {path.name}: {exc}") from exc


def _extract_auxiliary_json(report: Path, destination: Path) -> int:
    data = report.read_bytes(); matches = list(_AUX_HEADER.finditer(data)); written = 0
    for index, match in enumerate(matches):
        original = match.group(2).decode("utf-8", "replace")
        if "\\\\data\\\\snapshots\\\\" not in original.lower(): continue
        relative = Path(*original.replace("\\", "/").split("/data/snapshots/", 1)[1].split("/"))
        start = match.end(); end = matches[index + 1].start() if index + 1 < len(matches) else len(data); framed = data[start:end]
        separator = re.search(rb"(?:\r\n){1,3}={10,}\r\n(?:FILE :|$)", framed)
        if separator: framed = framed[:separator.start()]
        content = framed.strip(b"\r\n=")
        try: json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError): continue
        output = destination / relative; output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(content + b"\n"); written += 1
    return written


def _parse_signal_repr(value: Any) -> dict[str, Any]:
    m = re.search(r"Signal\(name='([^']*)',\s*confidence=([-+]?\d+(?:\.\d+)?)\)", str(value or ""))
    if not m: return {}
    c = _number(m.group(2)); return {"name": m.group(1), "confidence": int(c) if c.is_integer() else c}


def _parse_validation_repr(value: Any) -> dict[str, Any]:
    m = re.search(r"ValidationResult\(valid=(True|False),\s*grade='([^']*)',\s*confidence=([-+]?\d+(?:\.\d+)?),\s*risk_multiplier=([-+]?\d+(?:\.\d+)?),\s*warnings=(\[[^]]*\])\)", str(value or ""))
    if not m: return {}
    c = _number(m.group(3)); return {"valid": m.group(1) == "True", "grade": m.group(2), "confidence": int(c) if c.is_integer() else c, "risk_multiplier": _number(m.group(4)), "warnings": []}


def _parse_trade_repr(value: Any) -> dict[str, Any]:
    raw = str(value or ""); out: dict[str, Any] = {}
    if not raw.startswith("Trade("): return out
    for field, token in re.findall(r"(contract|option_type|strike|entry|stop_loss|target1|target2|risk_reward)=((?:'[^']*')|(?:[^,\)]+))", raw):
        token = token.strip(); out[field] = token[1:-1] if token.startswith("'") and token.endswith("'") else _number(token)
    return out


def _normalize_recorded_decision(decision: dict[str, Any]) -> dict[str, Any]:
    if not decision: return {}
    out = dict(decision); signal = _parse_signal_repr(out.get("signal")); validation = _parse_validation_repr(out.get("validation")); trade = _parse_trade_repr(out.get("trade"))
    if signal: out["signal"] = signal
    if validation: out["validation"] = validation
    if trade: out["trade"] = trade
    return out


def _copy_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _recorded_intelligence(analytics: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    dealer = _copy_dict(analytics.get("dealer")); dealer_flow = _copy_dict(analytics.get("dealer_flow")); liquidity = _copy_dict(analytics.get("liquidity")); gamma = _copy_dict(analytics.get("gamma_flip")); oi = _copy_dict(analytics.get("oi_flow")); oi_summary = _copy_dict(oi.get("summary")); iv = _copy_dict(analytics.get("iv_skew")); expected = _copy_dict(analytics.get("expected_move")); market = _copy_dict(analytics.get("market_structure")); smart = _copy_dict(analytics.get("smart_strike")); probability = _copy_dict(analytics.get("probability")); pcr = _copy_dict(analytics.get("pcr")); technical = _copy_dict(analytics.get("technical")); volatility = _copy_dict(analytics.get("volatility")); inst = _copy_dict(analytics.get("institutional_score")); institutional = _copy_dict(inst.get("institutional")); iv_details = _copy_dict(analytics.get("iv_skew_details"));
    # Preserve the recorder's own intelligence namespace verbatim while also projecting
    # the canonical fields consumed by the live institutional decision path.
    option_type = str(smart.get("option_type") or "").upper(); strike = _number(smart.get("strike")); selected = next((r for r in rows if strike and abs(_number(r.get("strike"))-strike)<.001 and str(r.get("side"))==option_type), None)
    selection = dict(smart) if smart else {}
    if selected: selection.update({"security_id": selected.get("security_id"), "side": option_type})
    elif option_type: selection["side"] = option_type
    smart_reasons = smart.get("reasons") or []
    probability = {k: v for k, v in probability.items()}
    pcr = {k: v for k, v in pcr.items()}
    technical = {k: v for k, v in technical.items()}
    volatility_snapshot = {k: v for k, v in volatility.items()}
    # The replay path uses iv_skew_details as canonical evidence; recorded exports
    # historically also stored the same fields at the top level, so retain both.
    if not iv_details and iv: iv_details = dict(iv)
    expected_move = {"move": _number(expected.get("expected_move", expected.get("move"))), "lower": expected.get("lower"), "upper": expected.get("upper")}
    return {
        "bias": str(market.get("bias") or analytics.get("bias") or "NEUTRAL").upper(), "structure": str(market.get("structure") or analytics.get("structure") or "UNKNOWN"), "market_structure_confidence": _number(market.get("confidence")),
        "gex": _number(dealer.get("total_gex", analytics.get("gex"))), "dex": _number(dealer_flow.get("total_dex", analytics.get("dex"))), "vanna_proxy": _number(dealer_flow.get("total_vanna", analytics.get("vanna_proxy"))), "charm": _number(dealer_flow.get("total_charm", analytics.get("charm"))),
        "dealer_gamma": str(dealer.get("dealer_gamma") or analytics.get("dealer_gamma") or "").upper(), "dealer_pressure": str(dealer_flow.get("dealer_pressure") or "").upper(), "dealer_hedging": str(dealer_flow.get("dealer_hedging") or "").upper(),
        "gamma_flip": gamma.get("gamma_flip", analytics.get("gamma_flip")), "gamma_flip_direction": str(gamma.get("direction") or analytics.get("gamma_flip_direction") or "").upper(), "atm_iv": (_number(iv.get("average_call_iv"))+_number(iv.get("average_put_iv")))/2.0 if iv else _number(analytics.get("atm_iv")),
        "iv_skew": iv.get("iv_skew", analytics.get("iv_skew")), "iv_bias": str(iv.get("iv_bias") or analytics.get("iv_bias") or "").upper(), "iv_market_sentiment": str(iv.get("market_sentiment") or "").upper(), "iv_skew_details": iv_details, "expected_move": expected_move,
        "recorded_oi_flow_bias": str(oi_summary.get("market_bias") or analytics.get("recorded_oi_flow_bias") or "NEUTRAL").upper(), "recorded_oi_trend": str(oi_summary.get("trend") or "").upper(),
        "liquidity_score": 100.0 if "Good Liquidity" in smart_reasons else _number(liquidity.get("score", analytics.get("liquidity_score"))), "intelligence": {"market_state": {"state": str(dealer.get("market_mode") or analytics.get("market_state") or "UNKNOWN")}},
        "strike_selection": [selection] if selection else [], "probability": probability, "pcr": pcr, "technical": technical, "volatility_snapshot": volatility_snapshot,
        "recorded_institutional_score": institutional, "recorded_analytics": analytics, "recorded_liquidity": liquidity,
    }


def load_snapshot_bundle(directory: str | Path) -> dict[str, Any]:
    root = Path(directory); runtime_path, option_path, greeks_path = root/"runtime.json", root/"option_chain.parquet", root/"greeks.parquet"
    for path in (runtime_path, option_path, greeks_path):
        if not path.is_file(): raise ValueError(f"incomplete snapshot bundle: missing {path.name}")
    runtime = _read_json(runtime_path); options = _read_parquet(option_path); greeks = _read_parquet(greeks_path); analytics = _read_json(root/"analytics.json") if (root/"analytics.json").is_file() else {}; decision = _read_json(root/"decision.json") if (root/"decision.json").is_file() else {}
    required = {"Strike","CE_ID","CE_LTP","CE_OI","CE_VOLUME","PE_ID","PE_LTP","PE_OI","PE_VOLUME"}
    missing = required - set(options[0]) if options else required
    if missing: raise ValueError(f"option_chain.parquet missing columns: {', '.join(sorted(missing))}")
    if not greeks or "Strike" not in greeks[0]: raise ValueError("greeks.parquet missing Strike column")
    greek_by_strike = {_number(r.get("Strike")): r for r in greeks}; rows=[]
    for row in options:
        strike=_number(row.get("Strike")); greek=greek_by_strike.get(strike,{})
        for side in ("CE","PE"):
            prefix=side+"_"; leg={"strike":strike,"side":side,"security_id":_identifier(row.get(prefix+"ID")),"last_price":_number(row.get(prefix+"LTP")),"oi":_number(row.get(prefix+"OI")),"volume":_number(row.get(prefix+"VOLUME"))}
            for field in ("IV","DELTA","GAMMA","THETA","VEGA","RHO","VANNA","CHARM"):
                col=prefix+field
                if col in greek and greek.get(col) is not None: leg[field.lower()]=_number(greek.get(col))
            rows.append(leg)
    snapshot={"timestamp":_timestamp(str(runtime.get("timestamp",""))),"spot":_number(runtime.get("spot")),"expiry":str(runtime.get("expiry") or ""),"symbol":str(runtime.get("symbol") or "NIFTY"),"regime":str(runtime.get("regime") or ""),"runtime_status":str(runtime.get("runtime_status") or ""),"recording_path":str(root),"option_chain":rows,"data_integrity":"RECORDED_HISTORICAL"}
    snapshot.update(_recorded_intelligence(analytics,rows)); snapshot["recorded_decision"]=_normalize_recorded_decision(decision)
    return canonicalize_snapshot(snapshot,"RECORDED_HISTORICAL")


def _load_directory(base: Path) -> list[dict[str, Any]]:
    bundles=sorted({p.parent for p in base.rglob("runtime.json")})
    if not bundles: raise ValueError(f"no recorded snapshot bundles found under {base}")
    return canonicalize_snapshots([load_snapshot_bundle(p) for p in bundles],"RECORDED_HISTORICAL")


def load_recording(root: str | Path) -> list[dict[str, Any]]:
    base=Path(root)
    if not base.exists(): raise ValueError(f"recording root does not exist: {base}")
    if base.is_file():
        if base.suffix.lower() != ".txt": raise ValueError(f"recording path must be a snapshot directory or .txt recorder export: {base}")
        with load_report_to_temporary_root(base) as temp:
            _extract_auxiliary_json(base,Path(temp)); return _load_directory(Path(temp))
    return _load_directory(base)
