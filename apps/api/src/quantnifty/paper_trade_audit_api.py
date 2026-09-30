from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from zoneinfo import ZoneInfo

from quantnifty.learning_store import load_events

IST = ZoneInfo("Asia/Kolkata")

router = APIRouter()


def _ts(value: Any) -> datetime | None:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _today_ist() -> str:
    return datetime.now(IST).date().isoformat()


def _day(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return _today_ist()
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD") from exc


def _outcomes(day: str) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in load_events("outcomes", day):
        row = event.get("outcome") if isinstance(event, dict) else None
        if not isinstance(row, dict):
            continue
        trade_id = str(row.get("trade_id") or "").strip()
        if not trade_id:
            continue
        stamp = str(row.get("exit_timestamp") or row.get("entry_timestamp") or row.get("timestamp") or "")
        previous = latest.get(trade_id)
        previous_stamp = str((previous or {}).get("exit_timestamp") or (previous or {}).get("entry_timestamp") or (previous or {}).get("timestamp") or "")
        if previous is None or stamp >= previous_stamp:
            latest[trade_id] = row
    return sorted(latest.values(), key=lambda row: str(row.get("entry_timestamp") or row.get("timestamp") or ""))


def _decision_match(entry_timestamp: Any, decisions: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float | None]:
    target = _ts(entry_timestamp)
    if target is None:
        return None, None
    best = None
    best_delta = None
    for event in decisions:
        timestamp = event.get("timestamp")
        current = _ts(timestamp)
        if current is None:
            continue
        delta = abs((current - target).total_seconds())
        if best_delta is None or delta < best_delta:
            best = event
            best_delta = delta
    if best is None or best_delta is None:
        return None, None
    return best, round(best_delta, 3)


def _logic_trace(outcome: dict[str, Any], matched_decision: dict[str, Any] | None) -> dict[str, Any]:
    decision = outcome.get("entry_decision") if isinstance(outcome.get("entry_decision"), dict) else {}
    risk = outcome.get("entry_risk") if isinstance(outcome.get("entry_risk"), dict) else {}
    signal = decision.get("signal") if isinstance(decision.get("signal"), dict) else {}
    execution = decision.get("execution_plan") if isinstance(decision.get("execution_plan"), dict) else {}
    return {
        "strategy": outcome.get("strategy") or decision.get("strategy"),
        "decision_action": decision.get("decision_action"),
        "signal": {
            "direction": signal.get("direction") or outcome.get("direction"),
            "confidence": signal.get("confidence"),
            "evidence": signal.get("evidence", []),
            "rationale": signal.get("rationale", []),
            "adaptive": signal.get("adaptive", {}),
        },
        "risk": {
            "approved": risk.get("approved"),
            "gates": risk.get("gates", {}),
            "reasons": risk.get("reasons", []),
            "context_alignment": risk.get("context_alignment"),
        },
        "execution_plan": execution,
        "entry_gate": outcome.get("entry_reasons", {}),
        "entry_trigger": outcome.get("entry_trigger"),
        "entry_mode": outcome.get("entry_mode"),
        "exit_policy": outcome.get("exit_policy", {}),
        "risk_anchor": outcome.get("risk_anchor"),
        "matched_decision_timestamp": matched_decision.get("timestamp") if matched_decision else None,
    }


@router.get("/api/v1/paper/trade-audit")
def paper_trade_audit(
    day: str | None = Query(default=None, description="IST trading day in YYYY-MM-DD"),
) -> dict[str, Any]:
    target_day = _day(day)
    outcome_rows = _outcomes(target_day)
    decision_events = load_events("decisions", target_day)

    trades: list[dict[str, Any]] = []
    for outcome in outcome_rows:
        matched, delta = _decision_match(outcome.get("entry_timestamp"), decision_events)
        status = str(outcome.get("status") or outcome.get("lifecycle") or "").upper()
        trades.append({
            "trade_id": outcome.get("trade_id"),
            "status": status,
            "direction": outcome.get("direction"),
            "strategy": outcome.get("strategy"),
            "entry_timestamp": outcome.get("entry_timestamp"),
            "entry_spot": outcome.get("entry_spot"),
            "entry_price": outcome.get("entry_price"),
            "entry_delta": outcome.get("entry_delta"),
            "delta_risk_at_entry": outcome.get("delta_risk_at_entry"),
            "instrument": outcome.get("instrument"),
            "quantity": outcome.get("quantity"),
            "entry_trigger": outcome.get("entry_trigger"),
            "entry_mode": outcome.get("entry_mode"),
            "entry_reasons": outcome.get("entry_reasons", {}),
            "entry_decision": outcome.get("entry_decision", {}),
            "entry_risk": outcome.get("entry_risk", {}),
            "exit_timestamp": outcome.get("exit_timestamp"),
            "exit_spot": outcome.get("exit_spot"),
            "exit_price": outcome.get("exit_price"),
            "exit_delta": outcome.get("exit_delta"),
            "delta_risk_at_exit": outcome.get("delta_risk_at_exit"),
            "exit_reason": outcome.get("exit_reason") or outcome.get("close_reason"),
            "exit_reasons": outcome.get("exit_reasons", {}),
            "exit_decision": outcome.get("exit_decision", {}),
            "premium_stop": outcome.get("premium_sl"),
            "premium_target": outcome.get("premium_target"),
            "realized_pnl": outcome.get("realized_pnl"),
            "gross_pnl_proxy": outcome.get("gross_pnl_proxy"),
            "pnl_basis": outcome.get("pnl_basis"),
            "read_only": outcome.get("read_only"),
            "execution": outcome.get("execution"),
            "logic_trace": _logic_trace(outcome, matched),
            "persisted_decision_match": {
                "timestamp": matched.get("timestamp") if matched else None,
                "strategy": matched.get("strategy") if matched else None,
                "delta_seconds": delta,
                "available": matched is not None,
            },
        })

    closed = [row for row in trades if row["status"] == "CLOSED"]
    open_trades = [row for row in trades if row["status"] == "OPEN"]
    pnl_values = [float(row["realized_pnl"]) for row in closed if isinstance(row.get("realized_pnl"), (int, float))]
    return {
        "mode": "READ_ONLY_PAPER",
        "day": target_day,
        "source": "quantnifty_learning_events",
        "trading": "DISABLED",
        "summary": {
            "trades_recorded": len(trades),
            "closed_trades": len(closed),
            "open_trades": len(open_trades),
            "total_realized_pnl": round(sum(pnl_values), 4),
            "decision_events": len(decision_events),
        },
        "trades": trades,
    }


__all__ = ["router"]
