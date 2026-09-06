from __future__ import annotations

from typing import Any


VALID_DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL"}
VALID_PHASES = {"PRE_OPEN", "NORMAL_ADAPTIVE", "CAS_REENTRY", "CLOSED", "UNKNOWN"}


def _num(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_snapshot(data: dict[str, Any], mode: str = "LIVE") -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return {"valid": False, "stage": "input", "errors": ["snapshot_not_mapping"]}
    if not str(data.get("timestamp") or "").strip():
        errors.append("missing_timestamp")
    if not _num(data.get("spot")) or float(data.get("spot") or 0) <= 0:
        errors.append("invalid_spot")
    integrity = str(data.get("data_integrity") or "").upper()
    expected = "LIVE_PROVIDER" if str(mode).upper() not in {"BACKTEST", "REPLAY"} else "RECORDED_HISTORICAL"
    if integrity != expected:
        errors.append(f"data_integrity_expected_{expected}")
    if not isinstance(data.get("option_chain"), list):
        errors.append("option_chain_not_list")
    return {"valid": not errors, "stage": "input", "errors": errors, "mode": str(mode).upper(), "data_integrity": integrity}


def validate_signal(signal: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    direction = str(signal.get("direction") or "").upper()
    if direction not in VALID_DIRECTIONS:
        errors.append("invalid_direction")
    confidence = signal.get("confidence")
    if not _num(confidence) or not 0 <= float(confidence) <= 100:
        errors.append("invalid_confidence")
    if not isinstance(signal.get("scores"), dict):
        errors.append("missing_scores")
    if not isinstance(signal.get("evidence"), list):
        errors.append("missing_evidence")
    return {"valid": not errors, "stage": "signal", "errors": errors, "direction": direction, "confidence": float(confidence) if _num(confidence) else None}


def validate_risk(risk: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    gates = risk.get("gates")
    if not isinstance(gates, dict) or not gates:
        errors.append("missing_gates")
    else:
        non_bool = [k for k, v in gates.items() if not isinstance(v, bool)]
        if non_bool:
            errors.append("non_boolean_gates:" + ",".join(non_bool))
        expected = all(v is True for v in gates.values())
        if bool(risk.get("approved")) != expected:
            errors.append("approval_gate_mismatch")
    reasons = risk.get("reasons")
    if not isinstance(reasons, list):
        errors.append("missing_reasons")
    elif isinstance(gates, dict):
        expected_reasons = {k for k, v in gates.items() if v is False}
        if set(reasons) != expected_reasons:
            errors.append("reason_gate_mismatch")
    return {"valid": not errors, "stage": "risk", "errors": errors, "approved": bool(risk.get("approved"))}


def validate_execution_plan(plan: dict[str, Any], signal: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    approved = bool(risk.get("approved"))
    if plan.get("execution_enabled") is not False:
        errors.append("execution_must_remain_disabled")
    if plan.get("order_action") != "DISABLED":
        errors.append("order_action_must_be_disabled")
    expected_status = "APPROVED_READ_ONLY" if approved else "BLOCKED"
    if plan.get("status") != expected_status:
        errors.append("plan_status_mismatch")
    direction = str(signal.get("direction") or "NEUTRAL").upper()
    instrument = plan.get("instrument")
    if instrument and direction in {"BULLISH", "BEARISH"}:
        side = str(instrument.get("side") or instrument.get("option_type") or "").upper()
        expected_side = "CE" if direction == "BULLISH" else "PE"
        if side and side != expected_side:
            errors.append("instrument_direction_mismatch")
    if approved:
        for field in ("stop_points", "target_points", "risk_reward"):
            if not _num(plan.get(field)) or float(plan.get(field) or 0) <= 0:
                errors.append(f"invalid_{field}")
    return {"valid": not errors, "stage": "execution_plan", "errors": errors}


def validate_decision(data: dict[str, Any], result: dict[str, Any], mode: str = "LIVE") -> dict[str, Any]:
    signal = result.get("signal") if isinstance(result, dict) else {}
    risk = result.get("risk") if isinstance(result, dict) else {}
    plan = result.get("execution_plan") if isinstance(result, dict) else {}
    stages = {
        "input": validate_snapshot(data, mode),
        "signal": validate_signal(signal if isinstance(signal, dict) else {}),
        "risk": validate_risk(risk if isinstance(risk, dict) else {}),
        "execution_plan": validate_execution_plan(plan if isinstance(plan, dict) else {}, signal if isinstance(signal, dict) else {}, risk if isinstance(risk, dict) else {}),
    }
    errors = [f"{name}:{err}" for name, stage in stages.items() for err in stage["errors"]]
    return {"valid": not errors, "stages": stages, "errors": errors}
