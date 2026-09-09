from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from quantnifty.learning_store import load_events

router = APIRouter(tags=["paper-trading"])
IST = ZoneInfo("Asia/Kolkata")


def _day_now() -> str:
    return datetime.now(IST).date().isoformat()


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _closed_rows(day: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in load_events("outcomes", day):
        outcome = event.get("outcome") if isinstance(event, dict) else None
        if not isinstance(outcome, dict) or str(outcome.get("status") or "").upper() != "CLOSED":
            continue
        row = dict(outcome)
        row["timestamp"] = event.get("timestamp") or row.get("exit_timestamp") or row.get("entry_timestamp")
        rows.append(row)
    return sorted(rows, key=lambda row: str(row.get("exit_timestamp") or row.get("timestamp") or ""))


def _decision_summary(day: str) -> dict[str, Any]:
    events = load_events("decisions", day)
    directions: Counter[str] = Counter()
    names: Counter[str] = Counter()
    approved = blocked = 0
    latest: dict[str, Any] | None = None
    for event in events:
        decision = event.get("decision") if isinstance(event, dict) else None
        if not isinstance(decision, dict):
            continue
        signal = decision.get("signal") or {}
        direction = str(signal.get("direction") or "NEUTRAL").upper()
        directions[direction] += 1
        name = str(signal.get("name") or decision.get("strategy") or "UNKNOWN").upper()
        names[name] += 1
        risk = decision.get("risk") or {}
        if bool(risk.get("approved")):
            approved += 1
        else:
            blocked += 1
        latest = {"timestamp": event.get("timestamp"), "strategy": event.get("strategy"), "direction": direction, "signal": signal, "risk": risk}
    return {"total": len(events), "approved": approved, "blocked": blocked, "direction_distribution": dict(sorted(directions.items())), "signal_distribution": dict(sorted(names.items())), "latest": latest}


@router.get("/api/v1/paper/ledger")
def paper_ledger(day: str | None = Query(default=None, description="IST trading day YYYY-MM-DD; defaults to today")) -> dict[str, Any]:
    selected_day = str(day or _day_now())
    rows = _closed_rows(selected_day)
    gross = sum(_num(row.get("gross_pnl_proxy")) for row in rows)
    spot_proxy = sum(_num(row.get("spot_move_proxy")) for row in rows)
    option_rows = [row for row in rows if str(row.get("pnl_basis") or "").startswith("OPTION_PREMIUM") and _num(row.get("exit_price")) > 0]
    return {
        "mode": "READ_ONLY_PAPER",
        "day": selected_day,
        "currency": "INR",
        "status": "OK",
        "trading": "DISABLED",
        "ledger": rows,
        "summary": {
            "closed_trades": len(rows),
            "gross_pnl_proxy": round(gross, 4),
            "spot_move_proxy": round(spot_proxy, 4),
            "option_premium_pnl_trades": len(option_rows),
            "net_pnl": round(gross, 4),
            "charges": 0.0,
            "note": "Paper P&L only. gross_pnl_proxy is option-premium P&L when both entry/exit option prices are available; otherwise spot_move_proxy is used. Broker charges are not modeled.",
        },
        "decisions": _decision_summary(selected_day),
    }
