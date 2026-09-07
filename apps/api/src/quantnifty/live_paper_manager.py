from __future__ import annotations

from dataclasses import asdict
from typing import Any

from quantnifty.learning_store import load_events, record_outcome
from quantnifty.paper_trade_tracker import PaperTrade, make_trade_id, session_close_required


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _leg(snapshot: dict[str, Any], instrument: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(instrument, dict):
        return None
    sid = str(instrument.get("security_id") or "")
    symbol = str(instrument.get("trading_symbol") or "")
    strike = _f(instrument.get("strike")); side = str(instrument.get("side") or "").upper()
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


class LivePaperManager:
    """One-at-a-time read-only paper lifecycle with restart recovery from learning events."""

    def __init__(self) -> None:
        self.sequence = 0
        self.active: PaperTrade | None = None
        self.entry_price = 0.0
        self.entry_quantity = 1
        self.instrument: dict[str, Any] | None = None
        self._recover()

    def _recover(self) -> None:
        latest: dict[str, Any] | None = None
        for event in load_events("outcomes"):
            outcome = event.get("outcome") if isinstance(event, dict) else None
            if isinstance(outcome, dict) and outcome.get("status") == "OPEN":
                latest = outcome
            elif isinstance(outcome, dict) and outcome.get("status") == "CLOSED" and latest and outcome.get("trade_id") == latest.get("trade_id"):
                latest = None
        if not latest:
            return
        try:
            self.active = PaperTrade(**{k: latest[k] for k in PaperTrade.__dataclass_fields__ if k in latest})
            self.entry_price = _f(latest.get("entry_price"))
            self.entry_quantity = max(1, int(latest.get("quantity", 1)))
            self.instrument = latest.get("instrument") if isinstance(latest.get("instrument"), dict) else None
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
        self.active = PaperTrade(make_trade_id(timestamp, self.sequence), strategy, direction, timestamp, spot)
        self.entry_price = price
        self.entry_quantity = 1
        self.instrument = instrument if isinstance(instrument, dict) else None
        record_outcome({**asdict(self.active), "lifecycle": "OPEN", "entry_price": price, "quantity": 1, "instrument": self.instrument, "read_only": True, "execution": "NONE"})

    def _close(self, snapshot: dict[str, Any], reason: str) -> dict[str, Any] | None:
        if self.active is None:
            return None
        timestamp = str(snapshot.get("timestamp") or "")
        spot = _f(snapshot.get("spot")); leg = _leg(snapshot, self.instrument)
        exit_price = _price(leg, "SELL")
        if not timestamp or spot <= 0:
            return None
        outcome = self.active.close(timestamp, spot, reason)
        gross = (exit_price - self.entry_price) * self.entry_quantity if exit_price > 0 and self.entry_price > 0 else outcome["spot_move_proxy"] * self.entry_quantity
        outcome.update({"entry_price": round(self.entry_price, 6), "exit_price": round(exit_price, 6), "quantity": self.entry_quantity, "instrument": self.instrument, "gross_pnl_proxy": round(gross, 4), "pnl_basis": "OPTION_PREMIUM_WHEN_AVAILABLE_ELSE_SPOT_PROXY", "lifecycle": "CLOSED"})
        record_outcome(outcome)
        self.active = None; self.entry_price = 0.0; self.entry_quantity = 1; self.instrument = None
        return outcome

    def process(self, snapshot: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        timestamp = str(snapshot.get("timestamp") or "")
        plan = decision.get("execution_plan") or {}
        if self.active is not None:
            self.active.update(timestamp, _f(snapshot.get("spot")))
            should_close = session_close_required(timestamp) or not bool((decision.get("risk") or {}).get("approved"))
            if should_close:
                reason = "SESSION_CLOSE" if session_close_required(timestamp) else "SIGNAL_INVALIDATION"
                outcome = self._close(snapshot, reason)
                return {"status": "CLOSED", "outcome": outcome}
            return {"status": "OPEN", "trade": {**asdict(self.active), "entry_price": self.entry_price, "quantity": self.entry_quantity}}
        if bool((decision.get("risk") or {}).get("approved")) and plan.get("instrument"):
            self._open(snapshot, decision)
            if self.active is not None:
                return {"status": "OPEN", "trade": {**asdict(self.active), "entry_price": self.entry_price, "quantity": self.entry_quantity}}
        return {"status": "IDLE"}
