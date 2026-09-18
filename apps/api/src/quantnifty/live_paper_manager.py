from __future__ import annotations

from dataclasses import asdict
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.learning_store import claim_paper_trade_lock, load_events, load_snapshots, reconcile_paper_trade_lock, record_outcome, release_paper_trade_lock
from quantnifty.paper_control import activate_kill_switch, current_day, kill_switch_state
from quantnifty.paper_entry_gate import evaluate_paper_entry
from quantnifty.paper_trade_tracker import PaperTrade, make_trade_id, same_trading_day, session_close_required, trading_day
from quantnifty.intrade_reversal_guard import evaluate_intrade_reversal

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_NIFTY_LOT_SIZE = 65


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _quantity(plan: dict[str, Any], instrument: dict[str, Any] | None) -> int:
    # QuantNifty paper policy is exactly one NIFTY options lot. The plan may
    # contain a quantity for display/backward compatibility, but it cannot
    # increase paper exposure above one lot.
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


def _quote_telemetry(row: dict[str, Any] | None) -> dict[str, Any]:
    """Expose LTP and top-of-book separately so UI/P&L never conflates them."""
    if not isinstance(row, dict):
        return {
            "current_ltp": None,
            "current_bid": None,
            "current_ask": None,
            "current_spread": None,
            "quote_quality": "UNAVAILABLE",
        }
    ltp, bid, ask = _f(row.get("last_price")), _f(row.get("bid")), _f(row.get("ask"))
    spread = ask - bid if bid > 0 and ask > 0 and ask >= bid else None
    quality = "OK"
    if bid > 0 and ask > 0 and bid > ask:
        quality = "INVALID_BOOK"
    elif ltp <= 0:
        quality = "LTP_UNAVAILABLE"
    elif bid > 0 and ask > 0 and (ltp < bid or ltp > ask):
        quality = "LTP_OUTSIDE_TOP_OF_BOOK"
    return {
        "current_ltp": round(ltp, 6) if ltp > 0 else None,
        "current_bid": round(bid, 6) if bid > 0 else None,
        "current_ask": round(ask, 6) if ask > 0 else None,
        "current_spread": round(spread, 6) if spread is not None else None,
        "quote_quality": quality,
    }


def _delta(row: dict[str, Any] | None) -> float | None:
    if not isinstance(row, dict):
        return None
    greeks = row.get("greeks") if isinstance(row.get("greeks"), dict) else {}
    value = greeks.get("delta", row.get("delta"))
    try:
        delta = float(value)
    except (TypeError, ValueError):
        return None
    return delta if -1.0 <= delta <= 1.0 else None


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


def _delta_premium_levels(entry_price: float, delta: float | None, risk: dict[str, Any]) -> dict[str, Any]:
    if entry_price <= 0 or delta is None or not (0.0 < abs(delta) <= 1.0):
        return {"delta": None, "premium_stop": None, "premium_target": None, "premium_stop_distance": None, "premium_target_distance": None, "method": "DELTA_UNAVAILABLE"}
    stop_points = _f(risk.get("stop_points")); target_points = _f(risk.get("target_points"))
    if stop_points <= 0:
        return {"delta": round(abs(delta), 6), "premium_stop": None, "premium_target": None, "premium_stop_distance": None, "premium_target_distance": None, "method": "NO_SPOT_RISK_BUDGET"}
    stop_distance = abs(delta) * stop_points
    target_distance = abs(delta) * target_points
    return {"delta": round(abs(delta), 6), "premium_stop": round(max(0.0, entry_price - stop_distance), 6), "premium_target": round(entry_price + target_distance, 6), "premium_stop_distance": round(stop_distance, 6), "premium_target_distance": round(target_distance, 6), "method": "ENTRY_PREMIUM_PLUS_LIVE_ABS_DELTA_X_NIFTY_POINTS"}


def _entry_reasons(decision: dict[str, Any]) -> dict[str, Any]:
    signal = decision.get("signal") or {}; risk = decision.get("risk") or {}; adaptive = signal.get("adaptive") or {}
    return {"decision_strategy": decision.get("strategy"), "direction": signal.get("direction"), "confidence": signal.get("confidence"), "signal_evidence": signal.get("evidence") or [], "signal_rationale": signal.get("rationale") or [], "adaptive_regime": adaptive.get("regime"), "adaptive_selected_strategy": adaptive.get("selected_strategy"), "adaptive_preferred_direction": adaptive.get("preferred_direction"), "adaptive_readiness_pct": adaptive.get("readiness_pct"), "adaptive_reason": adaptive.get("reason"), "risk_approved": bool(risk.get("approved")), "risk_gates": risk.get("gates") or {}, "risk_reasons": risk.get("reasons") or [], "market_state": ((decision.get("market") or {}).get("state") if isinstance(decision.get("market"), dict) else None)}


def _exit_reasons(decision: dict[str, Any], reason: str) -> dict[str, Any]:
    risk = decision.get("risk") or {}; signal = decision.get("signal") or {}
    return {"exit_reason": reason, "risk_approved_at_exit": bool(risk.get("approved")), "risk_reasons_at_exit": risk.get("reasons") or [], "risk_gates_at_exit": risk.get("gates") or {}, "direction_at_exit": signal.get("direction"), "confidence_at_exit": signal.get("confidence"), "signal_evidence_at_exit": signal.get("evidence") or []}


class LivePaperManager:
    """Exactly-one-lot, exactly-one-position, read-only paper lifecycle."""

    def __init__(self) -> None:
        self.sequence = 0; self.active: PaperTrade | None = None; self.entry_price = 0.0; self.entry_quantity = DEFAULT_NIFTY_LOT_SIZE; self.instrument: dict[str, Any] | None = None; self.entry_reasons: dict[str, Any] = {}; self.entry_decision: dict[str, Any] = {}
        self.entry_risk: dict[str, Any] = {}; self.entry_trigger: str | None = None; self.entry_mode: str | None = None; self.exit_policy: dict[str, Any] = {}; self.entry_delta: float | None = None
        self.kill_switch_day = current_day(); self.kill_switch_active = bool(kill_switch_state(self.kill_switch_day).get("active")); self.monitor_previous_snapshot: dict[str, Any] | None = None; self.opposite_confirmations = 0; self.last_reversal_state: dict[str, Any] = {}
        self._recover()

    def _refresh_kill_switch(self) -> bool:
        day = current_day()
        if day != self.kill_switch_day:
            self.kill_switch_day = day
            self.kill_switch_active = False
        if not self.kill_switch_active:
            self.kill_switch_active = bool(kill_switch_state(day).get("active"))
        return self.kill_switch_active

    def _restore(self, outcome: dict[str, Any]) -> None:
        self.active = PaperTrade(**{k: outcome[k] for k in PaperTrade.__dataclass_fields__ if k in outcome})
        self.entry_price = _f(outcome.get("entry_price")); self.entry_quantity = DEFAULT_NIFTY_LOT_SIZE; self.instrument = outcome.get("instrument") if isinstance(outcome.get("instrument"), dict) else None; self.entry_reasons = outcome.get("entry_reasons") if isinstance(outcome.get("entry_reasons"), dict) else {}; self.entry_decision = outcome.get("entry_decision") if isinstance(outcome.get("entry_decision"), dict) else {}
        plan = self.entry_decision.get("execution_plan") if isinstance(self.entry_decision, dict) else {}; plan = plan if isinstance(plan, dict) else {}
        self.entry_risk = outcome.get("entry_risk") if isinstance(outcome.get("entry_risk"), dict) else _risk_levels(_f(outcome.get("entry_spot")), str(outcome.get("direction") or ""), plan)
        raw_delta = outcome.get("entry_delta")
        try: self.entry_delta = float(raw_delta) if raw_delta is not None else None
        except (TypeError, ValueError): self.entry_delta = None
        self.entry_trigger = outcome.get("entry_trigger") or plan.get("entry"); self.entry_mode = outcome.get("entry_mode") or plan.get("entry_mode"); self.exit_policy = outcome.get("exit_policy") if isinstance(outcome.get("exit_policy"), dict) else (plan.get("exit_policy") if isinstance(plan.get("exit_policy"), dict) else {})

    def _open_rows(self, day: str) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for event in load_events("outcomes", day):
            outcome = event.get("outcome") if isinstance(event, dict) else None
            if not isinstance(outcome, dict): continue
            trade_id = str(outcome.get("trade_id") or "")
            if not trade_id: continue
            status = str(outcome.get("status") or outcome.get("lifecycle") or "").upper()
            if status == "OPEN": rows[trade_id] = outcome
            elif status == "CLOSED": rows.pop(trade_id, None)
        return rows

    def _recover(self) -> None:
        today = current_day(); latest_by_trade: dict[str, dict[str, Any]] = {}
        all_events = load_events("outcomes")
        for event in all_events:
            outcome = event.get("outcome") if isinstance(event, dict) else None
            if not isinstance(outcome, dict): continue
            trade_id = str(outcome.get("trade_id") or "")
            if not trade_id: continue
            status = str(outcome.get("status") or outcome.get("lifecycle") or "").upper()
            if status == "OPEN": latest_by_trade[trade_id] = outcome
            elif status == "CLOSED": latest_by_trade.pop(trade_id, None)
        stale = [row for row in latest_by_trade.values() if trading_day(row.get("entry_timestamp")) != today]
        for stale_row in stale:
            entry_day = trading_day(stale_row.get("entry_timestamp"))
            if not entry_day: continue
            snapshots = load_snapshots(entry_day)
            if not snapshots: continue
            self._restore(stale_row)
            recovery_decision = {"strategy": "paper_recovery", "signal": {"direction": stale_row.get("direction"), "confidence": None, "evidence": [], "rationale": [], "adaptive": {}}, "risk": {"approved": False, "gates": {}, "reasons": ["SESSION_CLOSE_RECOVERY"]}, "execution_plan": {}, "mode": "RECOVERY"}
            self._close(snapshots[-1], recovery_decision, "SESSION_CLOSE_RECOVERY")
        current = [row for row in latest_by_trade.values() if trading_day(row.get("entry_timestamp")) == today]
        if len(current) > 1:
            snapshots = load_snapshots(today)
            keep = max(current, key=lambda row: str(row.get("entry_timestamp") or ""))
            if snapshots:
                guard_decision = {"strategy": "paper_recovery_guard", "signal": {"direction": None, "confidence": None, "evidence": [], "rationale": [], "adaptive": {}}, "risk": {"approved": False, "gates": {}, "reasons": ["MULTIPLE_ACTIVE_TRADE_GUARD"]}, "execution_plan": {}, "mode": "RECOVERY_GUARD"}
                for row in current:
                    if row.get("trade_id") == keep.get("trade_id"): continue
                    self._restore(row)
                    self._close(snapshots[-1], guard_decision, "MULTIPLE_ACTIVE_TRADE_GUARD")
                current = [keep]
            else:
                current = []
        open_ids = {str(row.get("trade_id")) for row in current if row.get("trade_id")}
        reconcile_paper_trade_lock(today, open_ids)
        if current:
            try: self._restore(current[-1])
            except (TypeError, ValueError): self.active = None

    def _trade_view(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        spot = _f(snapshot.get("spot")); leg = _leg(snapshot, self.instrument); current_price = _price(leg, "SELL")
        if current_price <= 0: current_price = _price(leg, "BUY")
        quote = _quote_telemetry(leg)
        current_delta = _delta(leg); pnl = (current_price - self.entry_price) * self.entry_quantity if current_price > 0 and self.entry_price > 0 else 0.0; pnl_pct = ((current_price - self.entry_price) / self.entry_price * 100.0) if current_price > 0 and self.entry_price > 0 else 0.0
        movement = "UP" if current_price > self.entry_price else "DOWN" if current_price < self.entry_price else "FLAT"; favorable = pnl_pct; invested = self.entry_price * self.entry_quantity; risk = self.entry_risk or {}; delta_risk = _delta_premium_levels(self.entry_price, current_delta, risk)
        return {**asdict(self.active), "entry_price": self.entry_price, "entry_spot": self.active.entry_spot, "quantity": self.entry_quantity, "lots": self.entry_quantity / DEFAULT_NIFTY_LOT_SIZE, "lots_label": "1 lot", "qty_label": str(self.entry_quantity), "instrument": self.instrument, "exit_price": round(current_price, 6) if current_price > 0 else None, "exit_price_source": "BID_THEN_LAST_THEN_ASK", "entry_reasons": self.entry_reasons, "entry_trigger": self.entry_trigger, "entry_mode": self.entry_mode, "entry_risk": risk, "stop_points": risk.get("stop_points"), "target_points": risk.get("target_points"), "risk_reward": risk.get("risk_reward"), "sl_spot": risk.get("stop_spot"), "target_spot": risk.get("target_spot"), "entry_delta": self.entry_delta, "current_delta": current_delta, "delta_risk": delta_risk, "premium_sl": delta_risk.get("premium_stop"), "premium_target": delta_risk.get("premium_target"), "premium_sl_distance": delta_risk.get("premium_stop_distance"), "premium_target_distance": delta_risk.get("premium_target_distance"), "delta_risk_method": delta_risk.get("method"), "exit_policy": self.exit_policy, "risk_anchor": "ENTRY_PREMIUM_WITH_LIVE_DELTA", "current_price": round(current_price, 6), "mark_price": round(current_price, 6) if current_price > 0 else None, "mark_timestamp": snapshot.get("timestamp"), "current_spot": round(spot, 4), "pnl": round(pnl, 4), "unrealized_pnl": round(pnl, 4), "pnl_pct": round(pnl_pct, 4), "unrealized_pnl_pct": round(pnl_pct, 4), "movement": movement, "favorable_move_pct": round(favorable, 4), "invested_amount": round(invested, 4), "mark_source": "BID_THEN_LAST_THEN_ASK", **quote}

    def _open(self, snapshot: dict[str, Any], decision: dict[str, Any]) -> bool:
        signal = decision.get("signal") or {}; plan = decision.get("execution_plan") or {}; instrument = plan.get("instrument"); leg = _leg(snapshot, instrument); timestamp = str(snapshot.get("timestamp") or ""); spot = _f(snapshot.get("spot")); direction = str(signal.get("direction") or "NEUTRAL"); price = _price(leg, "BUY"); delta = _delta(leg)
        if not timestamp or spot <= 0 or direction not in {"BULLISH", "BEARISH"} or price <= 0 or delta is None or abs(delta) <= 0: return False
        strategy = str((signal.get("adaptive") or {}).get("selected_strategy") or decision.get("strategy") or "adaptive")
        gate = evaluate_paper_entry(snapshot, direction, "LIVE", strategy)
        if not bool(gate.get("allowed")):
            return False
        day = trading_day(timestamp); next_sequence = self.sequence + 1; trade_id = make_trade_id(timestamp, next_sequence)
        if not day or not claim_paper_trade_lock(day, trade_id): return False
        try:
            self.sequence = next_sequence; quantity = DEFAULT_NIFTY_LOT_SIZE; self.entry_risk = _risk_levels(spot, direction, plan); self.entry_delta = delta; self.entry_trigger = plan.get("entry"); self.entry_mode = plan.get("entry_mode"); self.exit_policy = plan.get("exit_policy") if isinstance(plan.get("exit_policy"), dict) else {}
            self.active = PaperTrade(trade_id, strategy, direction, timestamp, spot); self.entry_price = price; self.entry_quantity = quantity; self.instrument = instrument if isinstance(instrument, dict) else None; self.entry_reasons = _entry_reasons(decision); self.entry_decision = decision; delta_risk = _delta_premium_levels(price, delta, self.entry_risk)
            record_outcome({**asdict(self.active), "day": trading_day(timestamp), "lifecycle": "OPEN", "entry_price": round(price, 6), "entry_price_source": "ASK_THEN_LAST_THEN_BID", "quantity": quantity, "instrument": self.instrument, "entry_reasons": self.entry_reasons, "entry_decision": self.entry_decision, "entry_risk": self.entry_risk, "entry_delta": round(delta, 6), "delta_risk_at_entry": delta_risk, "entry_trigger": self.entry_trigger, "entry_mode": self.entry_mode, "exit_policy": self.exit_policy, "risk_anchor": "ENTRY_PREMIUM_WITH_LIVE_DELTA", "position_policy": "ONE_POSITION_ONE_LOT", "read_only": True, "execution": "NONE"})
            return True
        except Exception:
            self.active = None; self.entry_price = 0.0; self.entry_quantity = DEFAULT_NIFTY_LOT_SIZE; self.instrument = None; self.entry_reasons = {}; self.entry_decision = {}; self.entry_risk = {}; self.entry_delta = None; self.entry_trigger = None; self.entry_mode = None; self.exit_policy = {}
            release_paper_trade_lock(day, trade_id)
            return False

    def _close(self, snapshot: dict[str, Any], decision: dict[str, Any], reason: str) -> dict[str, Any] | None:
        if self.active is None: return None
        timestamp = str(snapshot.get("timestamp") or ""); spot = _f(snapshot.get("spot")); leg = _leg(snapshot, self.instrument); exit_price = _price(leg, "SELL"); exit_delta = _delta(leg)
        if not timestamp or spot <= 0: return None
        trade_id = self.active.trade_id; trade_day = trading_day(self.active.entry_timestamp)
        outcome = self.active.close(timestamp, spot, reason); gross = (exit_price - self.entry_price) * self.entry_quantity if exit_price > 0 and self.entry_price > 0 else outcome["spot_move_proxy"] * self.entry_quantity
        outcome.update({"day": trade_day, "entry_price": round(self.entry_price, 6), "exit_price": round(exit_price, 6), "exit_price_source": "BID_THEN_LAST_THEN_ASK" if exit_price > 0 else "UNAVAILABLE_SPOT_PROXY", "quantity": self.entry_quantity, "instrument": self.instrument, "entry_reasons": self.entry_reasons, "entry_decision": self.entry_decision, "entry_risk": self.entry_risk, "entry_delta": self.entry_delta, "exit_delta": round(exit_delta, 6) if exit_delta is not None else None, "delta_risk_at_exit": _delta_premium_levels(self.entry_price, exit_delta, self.entry_risk), "entry_trigger": self.entry_trigger, "entry_mode": self.entry_mode, "exit_policy": self.exit_policy, "risk_anchor": "ENTRY_PREMIUM_WITH_LIVE_DELTA", "exit_spot": round(spot, 4), "exit_reasons": _exit_reasons(decision, reason), "exit_decision": decision, "gross_pnl_proxy": round(gross, 4), "realized_pnl": round(gross, 4), "pnl_basis": "OPTION_PREMIUM_WHEN_AVAILABLE_ELSE_SPOT_PROXY", "lifecycle": "CLOSED", "position_policy": "ONE_POSITION_ONE_LOT", "read_only": True, "execution": "NONE"})
        record_outcome(outcome)
        if trade_day:
            release_paper_trade_lock(trade_day, trade_id)
        self.active = None; self.entry_price = 0.0; self.entry_quantity = DEFAULT_NIFTY_LOT_SIZE; self.instrument = None; self.entry_reasons = {}; self.entry_decision = {}; self.entry_risk = {}; self.entry_delta = None; self.entry_trigger = None; self.entry_mode = None; self.exit_policy = {}
        return outcome

    def activate_daily_kill_switch(self, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        state = activate_kill_switch("MANUAL_KILL_SWITCH")
        self.kill_switch_day = str(state["day"]); self.kill_switch_active = True
        latest = snapshot
        if latest is None:
            snapshots = load_snapshots(self.kill_switch_day)
            latest = snapshots[-1] if snapshots else None
        if latest is not None:
            open_rows = self._open_rows(self.kill_switch_day)
            decision = {"strategy": "manual_kill_switch", "signal": {"direction": None, "confidence": None, "evidence": [], "rationale": [], "adaptive": {}}, "risk": {"approved": False, "gates": {"kill_switch": False}, "reasons": ["MANUAL_KILL_SWITCH"]}, "execution_plan": {}, "mode": "PAPER_CONTROL"}
            for row in sorted(open_rows.values(), key=lambda item: str(item.get("entry_timestamp") or "")):
                self._restore(row)
                self._close(latest, decision, "MANUAL_KILL_SWITCH")
        return {**state, "closed_open_positions": True if latest is not None else False}

    def _manage_active(self, snapshot: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        timestamp = str(snapshot.get("timestamp") or "")
        self.active.update(timestamp, _f(snapshot.get("spot")))
        same_day = same_trading_day(self.active.entry_timestamp, timestamp)
        trade_view = self._trade_view(snapshot)
        current_price = _f(trade_view.get("current_price")); premium_sl = _f(trade_view.get("premium_sl")); premium_target = _f(trade_view.get("premium_target"))
        hit_sl = premium_sl > 0 and current_price > 0 and current_price <= premium_sl
        hit_target = premium_target > 0 and current_price >= premium_target

        active_direction = str(self.active.direction or "").upper()
        opposite = "BEARISH" if active_direction == "BULLISH" else "BULLISH" if active_direction == "BEARISH" else "NEUTRAL"
        current_signal = str((decision.get("signal") or {}).get("direction") or "NEUTRAL").upper()
        if current_signal == opposite:
            self.opposite_confirmations += 1
        else:
            self.opposite_confirmations = 0

        # Re-evaluate the thesis on every live snapshot. Two consecutive opposite
        # confirmations normally exit; a confirmed opposite signal plus an adverse
        # price shock or gamma-flip cross exits immediately.
        reversal_snapshot = dict(snapshot)
        reversal_snapshot["_active_trade_entry_spot"] = self.active.entry_spot
        reversal = evaluate_intrade_reversal(
            active_direction, reversal_snapshot, decision,
            self.monitor_previous_snapshot, self.opposite_confirmations,
        )
        self.last_reversal_state = reversal
        self.monitor_previous_snapshot = dict(snapshot)

        should_close = session_close_required(timestamp) or not same_day or hit_sl or hit_target or reversal.get("action") == "EXIT_REVERSAL"
        if should_close:
            reason = (
                "SESSION_CLOSE" if session_close_required(timestamp) else
                "OVERNIGHT_GUARD" if not same_day else
                "DELTA_PREMIUM_STOP" if hit_sl else
                "DELTA_PREMIUM_TARGET" if hit_target else
                "OPPOSITE_REGIME_REVERSAL"
            )
            outcome = self._close(snapshot, decision, reason)
            if outcome is not None:
                outcome["reversal_guard"] = reversal
            self.opposite_confirmations = 0
            self.monitor_previous_snapshot = None
            return {"status": "CLOSED", "outcome": outcome, "reversal_guard": reversal}
        trade_view["reversal_guard"] = reversal
        return {"status": "OPEN", "trade": trade_view, "reversal_guard": reversal}

    def process(self, snapshot: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        if self._refresh_kill_switch():
            if self.active is not None:
                outcome = self._close(snapshot, decision, "MANUAL_KILL_SWITCH")
                return {"status": "CLOSED", "outcome": outcome, "kill_switch": True}
            return {"status": "KILL_SWITCH_ACTIVE", "kill_switch": True}
        if self.active is None:
            self._recover()
        if self.active is not None:
            return self._manage_active(snapshot, decision)
        plan = decision.get("execution_plan") or {}
        if bool((decision.get("risk") or {}).get("approved")) and plan.get("instrument") and str(decision.get("decision_action") or "") == "TAKE_TRADE":
            if self._open(snapshot, decision):
                self.monitor_previous_snapshot = dict(snapshot); self.opposite_confirmations = 0; self.last_reversal_state = {}
                return {"status": "OPEN", "trade": self._trade_view(snapshot)}
            return {"status": "NO_TRADE", "reason": "ENTRY_CAP_OR_ACTIVE_TRADE_LOCK_OR_ENTRY_DATA_INVALID"}
        return {"status": str(decision.get("decision_action") or "NO_TRADE"), "reason": ((decision.get("risk") or {}).get("reasons") or ["ENTRY_NOT_APPROVED"])[-1]}
