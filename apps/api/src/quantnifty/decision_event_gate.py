from __future__ import annotations

from typing import Any


class DecisionEventGate:
    """Emit decision events only when the actionable state changes.

    Every live snapshot remains persisted separately. This gate only reduces
    duplicate *decision-event* records; it never suppresses the live decision
    pipeline or paper-position management.
    """

    def __init__(self) -> None:
        self._last_signature: tuple[Any, ...] | None = None

    @staticmethod
    def signature(decision: dict[str, Any]) -> tuple[Any, ...]:
        risk = decision.get("risk") or {}
        session = risk.get("session") or {}
        return (
            str(decision.get("direction") or "NEUTRAL").upper(),
            str(decision.get("strategy") or "").lower(),
            bool(risk.get("approved")),
            str(risk.get("selected_strategy") or decision.get("selected_strategy") or "").lower(),
            str(session.get("phase") or "").upper(),
        )

    def should_emit(self, decision: dict[str, Any]) -> bool:
        signature = self.signature(decision)
        if signature == self._last_signature:
            return False
        self._last_signature = signature
        return True

    def reset(self) -> None:
        self._last_signature = None


__all__ = ["DecisionEventGate"]
