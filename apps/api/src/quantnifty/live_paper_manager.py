from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.learning_store import load_events, record_outcome
from quantnifty.paper_trade_tracker import PaperTrade, make_trade_id, same_trading_day, session_close_required, trading_day

IST = ZoneInfo("Asia/Kolkata")


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _quantity(plan: dict[str, Any], instrument: dict[str, Any] | None) -> int:
    candidates = [
        plan.get("quantity"), plan.get("qty"), plan.get("lot_quantity"), plan.get("lot_size"),
        (instrument or {}).get("quantity"), (instrument or {}).get("qty"), (instrument or {}).get("lot_size"),
        (instrument or {}).get("lotSize"), (instrument or {}).get("lot_size_quantity"),
    ]
    for value in candidates:
        try:
            value_int = int(float(value))
            if value_int > 0:
                return value_int
        except (TypeError, ValueError):
            continue
    return 1


def _leg(snapshot: dict[str, Any], instrument: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(instrument, dict):
        return None
    sid = str(instrument.get("security_id") or "")
    symbol = str(instrument.get("trading_symbol") or "")
    strike = _f(instrument.get("strike")); side = str(instrument.get("side") or instrument.get("option_type") or "").upper()
    for row in snapshot.get("option_chain") or []:
        if not isinstance(row, dict):
            continue
        if sid and str(row.get("security_id") or "") == sid:
            return row
        if symbol and str(row.get("trading_symbol") or "") == symbol:
            return row
        if not sid and not symbol and strike and abs(_f(row.get("strike")) - strike) < .001 and (not side or str(row.get("side") or "").upper() == side):
            return row
    return None


def _price(row: dict[str, Any] | None, action: str) -> float:
    if not row:
        return 0.0
    bid, ask, last = _f(row.get("bid")), _f(row.get("ask")), _f(row.get("last_price"))
    if action == "BUY":
        return ask if ask > 0 else last if last > 0 else bid
    return bid if bid > 0 else last if last > 0 else ask


def _entry_reasons(decision: dict[str, Any]) -> dict[str, Any]:
    signal = decision.get("signal") or {}
    risk = decision.get("risk") or {}
    adaptive = signal.get("adaptive") or {}
    return {
        "decision_strategy": decision.get("strategy"),
        "direction": signal.get("direction"),
        "confidence": signal.get("confidence"),
        "signal_evidence": signal.get("evidence") or [],
        "signal_rationale": signal.get("rationale") or [],
        "adaptive_regime": adaptive.get("regime"),
        "adaptive_selected_strategy": adaptive.get("selected_strategy"),
        "adaptive_preferred_direction": adaptive.get("preferred_direction"),
        "adaptive_readiness_pct": adaptive.get("readiness_pct"),
        "adaptive_reason": adaptive.get("reason"),
        "risk_approved": bool(risk.get("approved")),
        "risk_gates": risk.get("gates") or {},
        "risk_reasons": risk.get("reasons") or [],
        "market_state": ((decision.get("market") or {}).get("state") if isinstance(decision.get("market"), dict) else None),
    }


def _exit_reasons(decision: dict[str, Any], reason: str) -> dict[str, Any]:
    risk = decision.get("risk") or {}
    signal = decision.get("signal") or {}
    return {
        "exit_reason": reason,
        "risk_approved_at_exit": bool(risk.get("approved")),
        "risk_reasons_at_exit": risk.get("reasons") or [],
        "risk_gates_at_exit": risk.get("gates") or {},
        "direction_at_exit": signal.get("direction"),
        "confidence_at_exit": signal.get("confidence"),
        "signal_evidence_at_exit": signal.get("evidence") or [],
    }


class LivePaperManager:
    """One-at-a-time read-only paper lifecycle with durable Brain evidence."""

    def __init__(self) -> None:
        self.sequence = 0
        self.active: PaperTrade | None = None
        self.entry_price = 0.0
        self.entry_quantity = 1
        self.instrument: dict[str, Any] | None = None
        self.entry_reasons: dict[str, Any] = {}
        self.entry_decision: dict[str, Any] = {}
        self._recover()

    def _recover(self) -> None:
        latest: dict[str, Any] | None = None
        today = datetime.now(IST).date().isoformat()
        for event in load_events("outcomes"):
            outcome = event.get("outcome") if isinstance(event, dict) else None
            if not isinstance(outcome, dict):
                continue
            if outcome.get("status") == "OPEN":
                if str(outcome.get("day") or trading_day(outcome.get("entry_timestamp")) or "") == today:
                    latest = outcome
                else:
                    latest = None
            elif outcome.get("status") == "CLOSED" and latest and outcome.get("trade_id") == latest.get("trade_id"):
                latest = None
        if not latest:
            return
        try:
            self.active = PaperTrade(**{k: latest[k] for k in PaperTrade.__dataclass_fields__ if k in latest})
            self.entry_price = _f(latest.get("entry_price"))
            self.entry_quantity = max(1, int(latest.get("quantity", 1)))
            self.instrument = latest.get("instrument") if isinstance(latest.get("instrument"), dict) else None
            self.entry_reasons = latest.get("entry_reasons") if isinstance(latest.get("entry_reasons"), dict) else {}
            self.entry_decision = latest.get("entry_decision") if isinstance(latest.get("entry_decision"), dict) else {}
        except (TypeError, ValueError):
            self.active = None

    def _open(self, snapshot: dict[str, Any], decision: dict[str, Any]) -> None:
        signal = decision.get("signal") or {}; plan = decision.get("execution_plan") or {}; instrument = plan.get("instrument")
        leg = _leg(snapshot, instrument)
        timestamp = str(snapshot.get("timestamp") or "")
        spot = _f(snapshot.get("spot")); direction = str(signal.get("direction") or "NEUTRAL")
        price = _price(leg, "BUY")
        if not timestamp or spot <= 0 or direction not in {"BULLISH", "BEARISH"} or price <= 0:
            return
        self.sequence += 1
        strategy = str((signal.get("adaptive") or {}).get("selected_strategy") or decision.get("strategy") or "adaptive")
        quantity = _quantity(plan, instrument)
        self.active = PaperTrade(make_trade_id(timestamp, self.sequence), strategy, direction, timestamp, spot)
        self.entry_price = price
        self.entry_quantity = quantity
        self.instrument = instrument if isinstance(instrument, dict) else None
        self.entry_reasons = _entry_reasons(decision)
        self.entry_decision = decision
        record_outcome({
            **asdict(self.active),
            "day": trading_day(timestamp),
            "lifecycle": "OPEN",
            "entry_price": round(price, 6),
            "entry_price_source": "ASK_THEN_LAST_THEN_BID",
            "quantity": quantity,
            "instrument": self.instrument,
            "entry_reasons": self.entry_reasons,
            "entry_decision": self.entry_decision,
            "read_only": True,
            "execution": "NONE",
        })

    def _close(self, snapshot: dict[str, Any], decision: dict[str, Any], reason: str) -> dict[str, Any] | None:
        if self.active is None:
            return None
        timestamp = str(snapshot.get("timestamp") or "")
        spot = _f(snapshot.get("spot")); leg = _leg(snapshot, self.instrument)
        exit_price = _price(leg, "SELL")
        if not timestamp or spot <= 0:
            return None
        outcome = self.active.close(timestamp, spot, reason)
        gross = (exit_price - self.entry_price) * self.entry_quantity if exit_price > 0 and self.entry_price > 0 else outcome["spot_move_proxy"] * self.entry_quantity
        outcome.update({
            "day": trading_day(self.active.entry_timestamp),
            "entry_price": round(self.entry_price, 6),
            "exit_price": round(exit_price, 6),
            "exit_price_source": "BID_THEN_LAST_THEN_ASK" if exit_price > 0 else "UNAVAILABLE_SPOT_PROXY",
            "quantity": self.entry_quantity,
            "instrument": self.instrument,
            "entry_reasons": self.entry_reasons,
            "entry_decision": self.entry_decision,
            "exit_reasons": _exit_reasons(decision, reason),
            "exit_decision": decision,
            "gross_pnl_proxy": round(gross, 4),
            "realized_pnl": round(gross, 4),
            "pnl_basis": "OPTION_PREMIUM_WHEN_AVAILABLE_ELSE_SPOT_PROXY",
            "lifecycle": "CLOSED",
            "read_only": True,
            "execution": "NONE",
        })
        record_outcome(outcome)
        self.active = None; self.entry_price = 0.0; self.entry_quantity = 1; self.instrument = None; self.entry_reasons = {}; self.entry_decision = {}
        return outcome

    def process(self, snapshot: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        timestamp = str(snapshot.get("timestamp") or "")
        plan = decision.get("execution_plan") or {}
        if self.active is not None:
            self.active.update(timestamp, _f(snapshot.get("spot")))
            same_day = same_trading_day(self.active.entry_timestamp, timestamp)
            should_close = session_close_required(timestamp) or not same_day or not bool((decision.get("risk") or {}).get("approved"))
            if should_close:
                reason = "SESSION_CLOSE" if session_close_required(timestamp) else "OVERNIGHT_GUARD" if not same_day else "SIGNAL_INVALIDATION"
                outcome = self._close(snapshot, decision, reason)
                return {"status": "CLOSED", "outcome": outcome}
            return {"status": "OPEN", "trade": {**asdict(self.active), "entry_price": self.entry_price, "quantity": self.entry_quantity, "instrument": self.instrument, "entry_reasons": self.entry_reasons}}
        if bool((decision.get("risk") or {}).get("approved")) and plan.get("instrument"):
            self._open(snapshot, decision)
            if self.active is not None:
                return {"status": "OPEN", "trade": {**asdict(self.active), "entry_price": self.entry_price, "quantity": self.entry_quantity, "instrument": self.instrument, "entry_reasons": self.entry_reasons}}
        return {"status": "IDLE"}
