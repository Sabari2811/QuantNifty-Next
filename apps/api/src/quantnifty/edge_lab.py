from __future__ import annotations

from datetime import datetime
from typing import Any


HORIZONS = (5, 15, 30)


def _f(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _closest_index(snapshots: list[dict[str, Any]], timestamp: Any) -> int | None:
    target = _ts(timestamp)
    if target is None or not snapshots:
        return None
    best_index = None
    best_delta = None
    for index, snapshot in enumerate(snapshots):
        current = _ts(snapshot.get("timestamp"))
        if current is None:
            continue
        delta = abs((current - target).total_seconds())
        if best_delta is None or delta < best_delta:
            best_index, best_delta = index, delta
    return best_index


def _snapshot_at_or_after(snapshots: list[dict[str, Any]], start_index: int, seconds: int) -> dict[str, Any] | None:
    start = _ts(snapshots[start_index].get("timestamp"))
    if start is None:
        return None
    target = start.timestamp() + seconds
    for snapshot in snapshots[start_index:]:
        current = _ts(snapshot.get("timestamp"))
        if current is not None and current.timestamp() >= target:
            return snapshot
    return None


def _leg(snapshot: dict[str, Any] | None, instrument: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict) or not isinstance(instrument, dict):
        return None
    wanted_side = str(instrument.get("side") or instrument.get("option_type") or "").upper()
    wanted_security = str(instrument.get("security_id") or "")
    wanted_strike = _f(instrument.get("strike"))
    rows = snapshot.get("option_chain") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        side = str(row.get("side") or row.get("option_type") or "").upper()
        if wanted_side and side != wanted_side:
            continue
        if wanted_security and str(row.get("security_id") or "") == wanted_security:
            return row
        if wanted_strike > 0 and abs(_f(row.get("strike")) - wanted_strike) < 0.01:
            return row
    return None


def _move(entry: dict[str, Any], later: dict[str, Any] | None, direction: str, instrument: dict[str, Any] | None) -> dict[str, Any]:
    if not later:
        return {"available": False}
    entry_spot = _f(entry.get("spot"))
    later_spot = _f(later.get("spot"))
    spot_points = later_spot - entry_spot
    favorable_points = spot_points if direction == "BULLISH" else -spot_points if direction == "BEARISH" else 0.0
    spot_pct = favorable_points / entry_spot * 100.0 if entry_spot > 0 else 0.0
    entry_leg = _leg(entry, instrument)
    later_leg = _leg(later, instrument)
    entry_premium = _f((entry_leg or {}).get("last_price"))
    later_premium = _f((later_leg or {}).get("last_price"))
    premium_change = later_premium - entry_premium if entry_premium > 0 and later_premium > 0 else 0.0
    premium_pct = premium_change / entry_premium * 100.0 if entry_premium > 0 else None
    return {
        "available": True,
        "timestamp": later.get("timestamp"),
        "spot": later_spot,
        "spot_move_points": round(spot_points, 2),
        "favorable_spot_points": round(favorable_points, 2),
        "favorable_spot_pct": round(spot_pct, 3),
        "option_premium": later_premium if later_premium > 0 else None,
        "option_premium_change": round(premium_change, 2) if entry_premium > 0 else None,
        "option_premium_change_pct": round(premium_pct, 3) if premium_pct is not None else None,
    }


def _max_favorable(snapshots: list[dict[str, Any]], start_index: int, end_index: int, direction: str) -> float:
    entry = _f(snapshots[start_index].get("spot"))
    if entry <= 0:
        return 0.0
    values = [_f(row.get("spot")) for row in snapshots[start_index:end_index + 1] if _f(row.get("spot")) > 0]
    if not values:
        return 0.0
    if direction == "BULLISH":
        return round(max(values) - entry, 2)
    if direction == "BEARISH":
        return round(entry - min(values), 2)
    return 0.0


def _decision_payload(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("decision") if isinstance(event, dict) else None
    return value if isinstance(value, dict) else {}


def _classification(decision: dict[str, Any]) -> tuple[str, str]:
    validation = decision.get("validation") if isinstance(decision.get("validation"), dict) else {}
    risk = decision.get("risk") if isinstance(decision.get("risk"), dict) else {}
    action = str(validation.get("decision_action") or "").upper()
    direction = str((decision.get("signal") or {}).get("direction") or "NEUTRAL").upper()
    if action == "TAKE_TRADE" or bool(risk.get("approved")):
        return "ENTER_CANDIDATE", action or "TAKE_TRADE"
    if direction in {"BULLISH", "BEARISH"}:
        return "DO_NOT_ENTER_SETUP", action or "WAIT_CONFIRMATION"
    return "OBSERVATION", action or "NO_TRADE"


def _pattern_key(row: dict[str, Any]) -> str:
    blockers = row.get("blockers") or []
    if row.get("classification") == "ENTER_CANDIDATE":
        return f"ENTER|{row.get('strategy')}|{row.get('direction')}"
    return f"BLOCK|{row.get('strategy')}|{row.get('direction')}|{'/'.join(sorted(blockers)[:3])}"


def build_edge_analysis(snapshots: list[dict[str, Any]], decision_events: list[dict[str, Any]]) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    ordered = sorted(snapshots, key=lambda row: str(row.get("timestamp") or ""))
    events = sorted(decision_events, key=lambda row: str(row.get("timestamp") or ""))

    for event in events:
        decision = _decision_payload(event)
        index = _closest_index(ordered, event.get("timestamp"))
        if index is None:
            continue
        signal = decision.get("signal") if isinstance(decision.get("signal"), dict) else {}
        risk = decision.get("risk") if isinstance(decision.get("risk"), dict) else {}
        confirmation = risk.get("confirmation") if isinstance(risk.get("confirmation"), dict) else {}
        plan = decision.get("execution_plan") if isinstance(decision.get("execution_plan"), dict) else {}
        instrument = plan.get("instrument") if isinstance(plan.get("instrument"), dict) else None
        direction = str(signal.get("direction") or "NEUTRAL").upper()
        strategy = str((signal.get("adaptive") or {}).get("selected_strategy") or decision.get("strategy") or "unknown").lower()
        classification, action = _classification(decision)
        blockers = [str(value) for value in (risk.get("reasons") or [])]
        if confirmation.get("reasons"):
            blockers.extend(str(value) for value in confirmation.get("reasons") or [])
        blockers = list(dict.fromkeys(blockers))
        entry = ordered[index]
        horizons: dict[str, Any] = {}
        for minutes in HORIZONS:
            later = _snapshot_at_or_after(ordered, index, minutes * 60)
            horizons[f"{minutes}m"] = _move(entry, later, direction, instrument)
        eod = _move(entry, ordered[-1] if ordered else None, direction, instrument)
        threshold = max(8.0, min(25.0, _f((entry.get("expected_move") or {}).get("move")) * 0.07 or 12.0))
        move_15 = horizons["15m"]
        favorable_15 = bool(move_15.get("available") and (
            _f(move_15.get("favorable_spot_points")) >= threshold
            or _f(move_15.get("option_premium_change_pct")) >= 2.0
        ))
        if classification == "DO_NOT_ENTER_SETUP":
            outcome_label = "COUNTERFACTUAL_FOLLOW_THROUGH" if favorable_15 else "NO_FOLLOW_THROUGH"
        elif classification == "ENTER_CANDIDATE":
            outcome_label = "FOLLOW_THROUGH" if favorable_15 else "FALSE_SETUP"
        else:
            outcome_label = "OBSERVATION"
        confirmation_gates = confirmation.get("gates") if isinstance(confirmation.get("gates"), dict) else {}
        evidence_tags = [key for key, value in confirmation_gates.items() if value]
        row = {
            "timestamp": entry.get("timestamp"),
            "spot": entry.get("spot"),
            "classification": classification,
            "action": action,
            "strategy": strategy,
            "direction": direction,
            "confidence": signal.get("confidence"),
            "key_level": confirmation.get("level"),
            "displacement_points": confirmation.get("move_points"),
            "minimum_displacement_points": confirmation.get("minimum_displacement_points"),
            "supporting_confirmations": confirmation.get("score"),
            "confirmation_gates": confirmation_gates,
            "evidence_tags": evidence_tags,
            "blockers": blockers,
            "instrument": {
                "side": instrument.get("side") if instrument else None,
                "strike": instrument.get("strike") if instrument else None,
                "expiry": instrument.get("expiry") if instrument else None,
                "security_id": instrument.get("security_id") if instrument else None,
                "delta": instrument.get("delta") if instrument else None,
                "iv": instrument.get("iv") if instrument else None,
                "premium": instrument.get("last_price") if instrument else None,
            },
            "horizons": horizons,
            "eod": eod,
            "max_favorable_spot_points": _max_favorable(ordered, index, min(len(ordered) - 1, index + 30), direction),
            "outcome": outcome_label,
            "counterfactual_only": classification != "ENTER_CANDIDATE",
        }
        observations.append(row)

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in observations:
        groups.setdefault(_pattern_key(row), []).append(row)
    candidates: list[dict[str, Any]] = []
    for key, rows in groups.items():
        if len(rows) < 3:
            continue
        favorable = sum(1 for row in rows if row.get("outcome") in {"FOLLOW_THROUGH", "COUNTERFACTUAL_FOLLOW_THROUGH"})
        avg_15 = sum(_f((row.get("horizons") or {}).get("15m", {}).get("favorable_spot_points")) for row in rows) / len(rows)
        candidates.append({
            "pattern": key,
            "observations": len(rows),
            "follow_through_rate_pct": round(favorable / len(rows) * 100.0, 2),
            "avg_favorable_spot_points_15m": round(avg_15, 2),
            "sample_policy": ">=3 observations; descriptive research only",
        })
    candidates.sort(key=lambda row: (-row["follow_through_rate_pct"], -row["observations"], row["pattern"]))
    return {
        "schema": "decision-edge-analysis-v1",
        "status": "COMPLETED",
        "observations": len(observations),
        "enter_candidates": sum(1 for row in observations if row["classification"] == "ENTER_CANDIDATE"),
        "do_not_enter_setups": sum(1 for row in observations if row["classification"] == "DO_NOT_ENTER_SETUP"),
        "counterfactual_follow_through": sum(1 for row in observations if row["outcome"] == "COUNTERFACTUAL_FOLLOW_THROUGH"),
        "false_setups": sum(1 for row in observations if row["outcome"] == "FALSE_SETUP"),
        "edge_candidates": candidates,
        "observations_detail": observations,
        "lookahead_free_decision_fields": True,
        "future_outcomes_used_only_for_after_market_labeling": True,
        "orders_placed": 0,
        "research_only": True,
    }
