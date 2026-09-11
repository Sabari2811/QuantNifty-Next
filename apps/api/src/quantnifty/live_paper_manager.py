from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.learning_store import load_events, load_snapshots, record_outcome
from quantnifty.paper_trade_tracker import PaperTrade, make_trade_id, same_trading_day, session_close_required, trading_day

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_NIFTY_LOT_SIZE = 65


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _quantity(plan: dict[str, Any], instrument: dict[str, Any] | None) -> int:
    candidates = [plan.get("quantity"), plan.get("qty"), plan.get("lot_quantity"), plan.get("lot_size"), (instrument or {}).get("quantity"), (instrument or {}).get("qty"), (instrument or {}).get("lot_size"), (instrument or {}).get("lotSize"), (instrument or {}).get("lot_size_quantity")]
    for value in candidates:
        try:
            value_int = int(float(value))
            if value_int > 0:
                return value_int
        except (TypeError, ValueError):
            continue
    # A NIFTY paper trade represents one lot when the provider/instrument
    # payload does not carry the lot quantity. Never silently model one unit.
    return DEFAULT_NIFTY_LOT_SIZE


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
    signal = decision.get("signal") or {}; risk = decision.get("risk") or {}; adaptive = signal.get("adaptive") or {}
    return {"decision_strategy": decision.get("strategy"), "direction": signal.get("direction"), "confidence": signal.get("confidence"), "signal_evidence": signal.get("evidence") or [], "signal_rationale": signal.get("rationale") or [], "adaptive_regime": adaptive.get("regime"), "adaptive_selected_strategy": adaptive.get("selected_strategy"), "adaptive_preferred_direction": adaptive.get("preferred_direction"), "adaptive_readiness_pct": adaptive.get("readiness_pct"), "adaptive_reason": adaptive.get("reason"), "risk_approved": bool(risk.get("approved")), "risk_gates": risk.get("gates") or {}, "risk_reasons": risk.get("reasons") or [], "market_state": ((decision.get("market") or {}).get("state") if isinstance(decision.get("market"), dict) else None)}


def _exit_reasons(decision: dict[str, Any], reason: str) -> dict[str, Any]:
    risk = decision.get("risk") or {}; signal = decision.get("signal") or {}
    return {"exit_reason": reason, "risk_approved_at_exit": bool(risk.get("approved")), "risk_reasons_at_exit": risk.get("reasons") or [], "risk_gates_at_exit": risk.get("gates") or {}, "direction_at_exit": signal.get("direction"), "confidence_at_exit": signal.get("confidence"), "signal_evidence_at_exit": signal.get("evidence") or []}


def _risk_levels(entry_spot: float, direction: str, plan: dict[str, Any]) -> dict[str, Any]:
    stop_points = _f(plan.get("stop_points")); target_points = _f(plan.get("target_points")); rr = _f(plan.get("risk_reward"))
    if stop_points <= 0:
        return {"stop_points": None, "target_points": None, "risk_reward": None, "stop_spot": None, "target_spot": None}
    if target_points <= 0:
        target_points = stop_points * (rr if rr > 0 else 2.0)
    rr = target_points / stop_points if stop_points > 0 else None
    if direction == "BEARISH":
        stop_spot = entry_spot + stop_points
        target_spot = entry_spot - target_points
    else:
        stop_spot = entry_spot - stop_points
        target_spot = entry_spot + target_points
    return {"stop_points": round(stop_points, 2), "target_points": round(target_points, 2), "risk_reward": round(rr, 2) if rr is not None else None, "stop_spot": round(stop_spot, 2), "target_spot": round(target_spot, 2)}


class LivePaperManager:
    """One-at-a-time read-only paper lifecycle with durable Brain evidence."""

    def __init__(self) -> None:
        self.sequence = 0; self.active: PaperTrade | None = None; self.entry_price = 0.0; self.entry_quantity = DEFAULT_NIFTY_LOT_SIZE; self.instrument: dict[str, Any] | None = None; self.entry_reasons: dict[str, Any] = {}; self.entry_decision: dict[str, Any] = {}
        self.entry_risk: dict[str, Any] = {}; self.entry_trigger: str | None = None; self.entry_mode: str | None = None; self.exit_policy: dict[str, Any] = {}
        self._recover()

    def _restore(self, outcome: dict[str, Any]) -> None:
        self.active = PaperTrade(**{k: outcome[k] for k in PaperTrade.__dataclass_fields__ if k in outcome})
        self.entry_price = _f(outcome.get("entry_price")); self.entry_quantity = max(1, int(outcome.get("quantity", DEFAULT_NIFTY_LOT_SIZE))); self.instrument = outcome.get("instrument") if isinstance(outcome.get("instrument"), dict) else None; self.entry_reasons = outcome.get("entry_reasons") if isinstance(outcome.get("entry_reasons"), dict) else {}; self.entry_decision = outcome.get("entry_decision") if isinstance(outcome.get("entry_decision"), dict) else {}
        plan = self.entry_decision.get("execution_plan") if isinstance(self.entry_decision, dict) else {}
        plan = plan if isinstance(plan, dict) else {}
        self.entry_risk = outcome.get("entry_risk") if isinstance(outcome.get("entry_risk"), dict) else _risk_levels(_f(outcome.get("entry_spot")), str(outcome.get("direction") or ""), plan)
        self.entry_trigger = outcome.get("entry_trigger") or plan.get("entry")
        self.entry_mode = outcome.get("entry_mode") or plan.get("entry_mode")
        self.exit_policy = outcome.get("exit_policy") if isinstance(outcome.get("exit_policy"), dict) else (plan.get("exit_policy") if isinstance(plan.get("exit_policy"), dict) else {})

    def _recover(self) -> None:
        today = datetime.now(IST).date().isoformat()
        latest_by_trade: dict[str, dict[str, Any]] = {}
        for event in load_events("outcomes"):
            outcome = event.get("outcome") if isinstance(event, dict) else None
            if not isinstance(outcome, dict):
                continue
            trade_id = str(outcome.get("trade_id") or "")
            if not trade_id:
                continue
            if str(outcome.get("status") or "").upper() == "OPEN":
                latest_by_trade[trade_id] = outcome
            elif str(outcome.get("status") or "").upper() == "CLOSED":
                latest_by_trade.pop(trade_id, None)
        stale = [row for row in latest_by_trade.values() if trading_day(row.get("entry_timestamp")) != today]
        for stale_row in stale:
            entry_day = trading_day(stale_row.get("entry_timestamp"))
            if not entry_day:
                continue
            snapshots = load_snapshots(entry_day)
            if not snapshots:
                continue
            self._restore(stale_row)
            recovery_decision = {"strategy": "paper_recovery", "signal": {"direction": stale_row.get("direction"), "confidence": None, "evidence": [], "rationale": [], "adaptive": {}}, "risk": {"approved": False, "gates": {}, "reasons": ["SESSION_CLOSE_RECOVERY"]}, "execution_plan": {}, "mode": "RECOVERY"}
            self._close(snapshots[-1], recovery_decision, "SESSION_CLOSE_RECOVERY")
        current = [row for row in latest_by_trade.values() if trading_day(row.get("entry_timestamp")) == today]
        if current:
            try:
                self._restore(current[-1])
            except (TypeError, ValueError):
                self.active = None

    def _trade_view(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        spot = _f(snapshot.get("spot")); leg = _leg(snapshot, self.instrument); current_price = _price(leg, "SELL")
        if current_price <= 0:
            current_price = _price(leg, "BUY")
        pnl = (current_price - self.entry_price) * self.entry_quantity if current_price > 0 and self.entry_price > 0 else 0.0
        pnl_pct = ((current_price - self.entry_price) / self.entry_price * 100.0) if current_price > 0 and self.entry_price > 0 else 0.0
        movement = "UP" if current_price > self.entry_price else "DOWN" if current_price < self.entry_price else "FLAT"
        favorable = pnl_pct
        invested = self.entry_price * self.entry_quantity
        risk = self.entry_risk or {}
        return {**asdict(self.active), "entry_price": self.entry_price, "entry_spot": self.active.entry_spot, "quantity": self.entry_quantity, "lots": self.entry_quantity / DEFAULT_NIFTY_LOT_SIZE, "instrument": self.instrument, "entry_reasons": self.entry_reasons, "entry_trigger": self.entry_trigger, "entry_mode": self.entry_mode, "entry_risk": risk, "stop_points": risk.get("stop_points"), "target_points": risk.get("target_points"), "risk_reward": risk.get("risk_reward"), "sl_spot": risk.get("stop_spot"), "target_spot": risk.get("target_spot"), "exit_policy": self.exit_policy, "risk_anchor": "ENTRY_SPOT_IMMUTABLE", "current_price": round(current_price, 6), "current_spot": round(spot, 4), "pnl": round(pnl, 4), "pnl_pct": round(pnl_pct, 4), "movement": movement, "favorable_move_pct": round(favorable, 4), "invested_amount": round(invested, 4), "mark_source": "BID_THEN_LAST_THEN_ASK", "mark_timestamp": snapshot.get("timestamp")}

    def _open(self, snapshot: dict[str, Any], decision: dict[str, Any]) -> None:
        signal = decision.get("signal") or {}; plan = decision.get("execution_plan") or {}; instrument = plan.get("instrument"); leg = _leg(snapshot, instrument); timestamp = str(snapshot.get("timestamp") or ""); spot = _f(snapshot.get("spot")); direction = str(signal.get("direction") or "NEUTRAL"); price = _price(leg, "BUY")
        if not timestamp or spot <= 0 or direction not in {"BULLISH", "BEARISH"} or price <= 0:
            return
        self.sequence += 1; strategy = str((signal.get("adaptive") or {}).get("selected_strategy") or decision.get("strategy") or "adaptive"); quantity = _quantity(plan, instrument); self.entry_risk = _risk_levels(spot, direction, plan); self.entry_trigger = plan.get("entry"); self.entry_mode = plan.get("entry_mode"); self.exit_policy = plan.get("exit_policy") if isinstance(plan.get("exit_policy"), dict) else {}
        self.active = PaperTrade(make_trade_id(timestamp, self.sequence), strategy, direction, timestamp, spot); self.entry_price = price; self.entry_quantity = quantity; self.instrument = instrument if isinstance(instrument, dict) else None; self.entry_reasons = _entry_reasons(decision); self.entry_decision = decision
        record_outcome({**asdict(self.active), "day": trading_day(timestamp), "lifecycle": "OPEN", "entry_price": round(price, 6), "entry_price_source": "ASK_THEN_LAST_THEN_BID", "quantity": quantity, "instrument": self.instrument, "entry_reasons": self.entry_reasons, "entry_decision": self.entry_decision, "entry_risk": self.entry_risk, "entry_trigger": self.entry_trigger, "entry_mode": self.entry_mode, "exit_policy": self.exit_policy, "risk_anchor": "ENTRY_SPOT_IMMUTABLE", "read_only": True, "execution": "NONE"})

    def _close(self, snapshot: dict[str, Any], decision: dict[str, Any], reason: str) -> dict[str, Any] | None:
        if self.active is None:
            return None
        timestamp = str(snapshot.get("timestamp") or ""); spot = _f(snapshot.get("spot")); leg = _leg(snapshot, self.instrument); exit_price = _price(leg, "SELL")
        if not timestamp or spot <= 0:
            return None
        outcome = self.active.close(timestamp, spot, reason); gross = (exit_price - self.entry_price) * self.entry_quantity if exit_price > 0 and self.entry_price > 0 else outcome["spot_move_proxy"] * self.entry_quantity
        outcome.update({"day": trading_day(self.active.entry_timestamp), "entry_price": round(self.entry_price, 6), "exit_price": round(exit_price, 6), "exit_price_source": "BID_THEN_LAST_THEN_ASK" if exit_price > 0 else "UNAVAILABLE_SPOT_PROXY", "quantity": self.entry_quantity, "instrument": self.instrument, "entry_reasons": self.entry_reasons, "entry_decision": self.entry_decision, "entry_risk": self.entry_risk, "entry_trigger": self.entry_trigger, "entry_mode": self.entry_mode, "exit_policy": self.exit_policy, "risk_anchor": "ENTRY_SPOT_IMMUTABLE", "exit_spot": round(spot, 4), "exit_reasons": _exit_reasons(decision, reason), "exit_decision": decision, "gross_pnl_proxy": round(gross, 4), "realized_pnl": round(gross, 4), "pnl_basis": "OPTION_PREMIUM_WHEN_AVAILABLE_ELSE_SPOT_PROXY", "lifecycle": "CLOSED", "read_only": True, "execution": "NONE"})
        record_outcome(outcome)
        self.active = None; self.entry_price = 0.0; self.entry_quantity = DEFAULT_NIFTY_LOT_SIZE; self.instrument = None; self.entry_reasons = {}; self.entry_decision = {}; self.entry_risk = {}; self.entry_trigger = None; self.entry_mode = None; self.exit_policy = {}
        return outcome

    def process(self, snapshot: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        timestamp = str(snapshot.get("timestamp") or ""); plan = decision.get("execution_plan") or {}
        if self.active is not None:
            self.active.update(timestamp, _f(snapshot.get("spot"))); same_day = same_trading_day(self.active.entry_timestamp, timestamp); should_close = session_close_required(timestamp) or not same_day or not bool((decision.get("risk") or {}).get("approved"))
            if should_close:
                reason = "SESSION_CLOSE" if session_close_required(timestamp) else "OVERNIGHT_GUARD" if not same_day else "SIGNAL_INVALIDATION"; outcome = self._close(snapshot, decision, reason); return {"status": "CLOSED", "outcome": outcome}
            return {"status": "OPEN", "trade": self._trade_view(snapshot)}
        if bool((decision.get("risk") or {}).get("approved")) and plan.get("instrument"):
            self._open(snapshot, decision)
            if self.active is not None:
                return {"status": "OPEN", "trade": self._trade_view(snapshot)}
        return {"status": "IDLE"}
