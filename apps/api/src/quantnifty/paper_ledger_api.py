from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from quantnifty.learning_store import load_events, load_snapshots
from quantnifty.paper_trade_tracker import trading_day

router = APIRouter(tags=["paper-trading"])
IST = ZoneInfo("Asia/Kolkata")


def _day_now() -> str:
    return datetime.now(IST).date().isoformat()


def _num(value: Any) -> float:
    try: return float(value or 0.0)
    except (TypeError, ValueError): return 0.0


def _outcomes_for_day(day: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in load_events("outcomes"):
        outcome = event.get("outcome") if isinstance(event, dict) else None
        if not isinstance(outcome, dict): continue
        event_timestamp = event.get("timestamp") if isinstance(event, dict) else None
        candidate_day = str(outcome.get("day") or trading_day(outcome.get("entry_timestamp")) or trading_day(outcome.get("exit_timestamp")) or trading_day(event_timestamp) or "")
        if candidate_day != day: continue
        row = dict(outcome); row["timestamp"] = event_timestamp or row.get("exit_timestamp") or row.get("entry_timestamp"); rows.append(row)
    return rows


def _closed_rows(day: str) -> list[dict[str, Any]]:
    return sorted([r for r in _outcomes_for_day(day) if str(r.get("status") or "").upper() == "CLOSED"], key=lambda r: str(r.get("exit_timestamp") or r.get("timestamp") or ""))


def _open_rows(day: str) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in _outcomes_for_day(day):
        trade_id = str(row.get("trade_id") or "")
        if not trade_id: continue
        if str(row.get("status") or "").upper() == "OPEN": latest[trade_id] = row
        elif str(row.get("status") or "").upper() == "CLOSED": latest.pop(trade_id, None)
    return sorted(latest.values(), key=lambda r: str(r.get("entry_timestamp") or r.get("timestamp") or ""))


def _latest_open_lifecycle() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in load_events("outcomes"):
        outcome = event.get("outcome") if isinstance(event, dict) else None
        if not isinstance(outcome, dict): continue
        trade_id = str(outcome.get("trade_id") or "")
        if trade_id: latest[trade_id] = outcome
    return latest


def _leg(snapshot: dict[str, Any], instrument: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(instrument, dict): return None
    sid = str(instrument.get("security_id") or ""); symbol = str(instrument.get("trading_symbol") or ""); strike = _num(instrument.get("strike")); side = str(instrument.get("side") or instrument.get("option_type") or "").upper()
    for row in snapshot.get("option_chain") or []:
        if not isinstance(row, dict): continue
        if sid and str(row.get("security_id") or "") == sid: return row
        if symbol and str(row.get("trading_symbol") or "") == symbol: return row
        if not sid and not symbol and strike and abs(_num(row.get("strike")) - strike) < .001 and (not side or str(row.get("side") or "").upper() == side): return row
    return None


def _sell_mark(row: dict[str, Any] | None) -> tuple[float, str]:
    if not row: return 0.0, "UNAVAILABLE"
    bid, last, ask = _num(row.get("bid")), _num(row.get("last_price")), _num(row.get("ask"))
    if bid > 0: return bid, "BID"
    if last > 0: return last, "LAST"
    if ask > 0: return ask, "ASK"
    return 0.0, "UNAVAILABLE"


def _dynamic_open_row(row: dict[str, Any], latest_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(row); entry = _num(row.get("entry_price")); quantity = max(1, int(_num(row.get("quantity")) or 1)); direction = str(row.get("direction") or "NEUTRAL").upper()
    result.update({"quantity": quantity, "entry_value": round(entry * quantity, 4) if entry > 0 else 0.0, "mark_price": None, "mark_source": "UNAVAILABLE", "mark_timestamp": None, "unrealized_pnl": None, "unrealized_pnl_pct": None, "current_spot": None})
    if latest_snapshot:
        result["current_spot"] = _num(latest_snapshot.get("spot")); result["mark_timestamp"] = latest_snapshot.get("timestamp"); mark, source = _sell_mark(_leg(latest_snapshot, row.get("instrument"))); result["mark_price"] = round(mark, 6) if mark > 0 else None; result["mark_source"] = source
        if mark > 0 and entry > 0:
            pnl = (mark - entry) * quantity; result["unrealized_pnl"] = round(pnl, 4); result["unrealized_pnl_pct"] = round((mark - entry) / entry * 100.0, 4)
        elif result["current_spot"] and _num(row.get("entry_spot")) > 0:
            spot_proxy = (result["current_spot"] - _num(row.get("entry_spot"))) if direction == "BULLISH" else (_num(row.get("entry_spot")) - result["current_spot"]); result["unrealized_pnl"] = round(spot_proxy * quantity, 4); result["unrealized_pnl_pct"] = round(spot_proxy / _num(row.get("entry_spot")) * 100.0, 4); result["mark_source"] = "SPOT_PROXY"
    return result


def _decision_summary(day: str) -> dict[str, Any]:
    events = load_events("decisions", day); directions: Counter[str] = Counter(); names: Counter[str] = Counter(); approved = blocked = 0; latest = None
    for event in events:
        decision = event.get("decision") if isinstance(event, dict) else None
        if not isinstance(decision, dict): continue
        signal = decision.get("signal") or {}; direction = str(signal.get("direction") or "NEUTRAL").upper(); directions[direction] += 1; name = str(signal.get("name") or decision.get("strategy") or "UNKNOWN").upper(); names[name] += 1; risk = decision.get("risk") or {}
        if bool(risk.get("approved")): approved += 1
        else: blocked += 1
        latest = {"timestamp": event.get("timestamp"), "strategy": event.get("strategy"), "direction": direction, "signal": signal, "risk": risk}
    return {"total": len(events), "approved": approved, "blocked": blocked, "direction_distribution": dict(sorted(directions.items())), "signal_distribution": dict(sorted(names.items())), "latest": latest}


@router.get("/api/v1/paper/ledger")
def paper_ledger(day: str | None = Query(default=None, description="IST trading day YYYY-MM-DD; defaults to today")) -> dict[str, Any]:
    selected_day = str(day or _day_now()); closed = _closed_rows(selected_day); opened = _open_rows(selected_day); snapshots = [s for s in load_snapshots(selected_day) if isinstance(s, dict)]; latest_snapshot = snapshots[-1] if snapshots else None; open_rows = [_dynamic_open_row(row, latest_snapshot) for row in opened]
    realized = sum(_num(r.get("realized_pnl", r.get("gross_pnl_proxy"))) for r in closed); spot_proxy = sum(_num(r.get("spot_move_proxy")) for r in closed); unrealized = sum(_num(r.get("unrealized_pnl")) for r in open_rows if r.get("unrealized_pnl") is not None); total_pnl = realized + unrealized; option_rows = [r for r in closed if str(r.get("pnl_basis") or "").startswith("OPTION_PREMIUM") and _num(r.get("exit_price")) > 0]
    stale_open_count = sum(1 for outcome in _latest_open_lifecycle().values() if str(outcome.get("status") or "").upper() == "OPEN" and (str(outcome.get("day") or trading_day(outcome.get("entry_timestamp")) or "") < selected_day))
    return {"mode": "READ_ONLY_PAPER", "day": selected_day, "currency": "INR", "status": "OK", "trading": "DISABLED", "session_policy": {"new_decisions_stop_at": "15:30 IST", "all_paper_positions_close_by": "15:30 IST", "overnight_carry": False}, "ledger": closed, "open_positions": open_rows, "mark_to_market": {"snapshot_timestamp": latest_snapshot.get("timestamp") if latest_snapshot else None, "spot": _num(latest_snapshot.get("spot")) if latest_snapshot else None, "open_unrealized_pnl": round(unrealized, 4), "dynamic": bool(open_rows)}, "summary": {"closed_trades": len(closed), "open_positions": len(open_rows), "realized_pnl": round(realized, 4), "unrealized_pnl": round(unrealized, 4), "total_pnl": round(total_pnl, 4), "gross_pnl_proxy": round(realized, 4), "spot_move_proxy": round(spot_proxy, 4), "option_premium_pnl_trades": len(option_rows), "net_pnl": round(total_pnl, 4), "charges": 0.0, "stale_open_positions": stale_open_count, "note": "Paper P&L only. Closed-trade P&L uses option premium when entry/exit prices are available; otherwise spot_move_proxy. Open positions are marked dynamically from the latest LIVE_PROVIDER snapshot. Broker charges are not modeled. Overnight carry is prohibited."}, "decisions": _decision_summary(selected_day)}
