from __future__ import annotations

from typing import Any


class DecisionEventGate:
    """Emit decision events only when the actionable state changes.

    Every live snapshot remains persisted separately. This gate only reduces
    duplicate *decision-event* records; it never suppresses the live decision
    pipeline or paper-position management.

    The latest same-day persisted decision can be seeded after a process
    restart so a restart does not manufacture a duplicate event.
    """

    def __init__(self) -> None:
        self._last_signature: tuple[Any, ...] | None = None
        self.emitted = 0
        self.suppressed = 0

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

    def seed(self, decision: dict[str, Any] | None) -> None:
        """Restore the latest same-day signature without emitting an event."""
        self._last_signature = self.signature(decision) if isinstance(decision, dict) else None

    def should_emit(self, decision: dict[str, Any]) -> bool:
        signature = self.signature(decision)
        if signature == self._last_signature:
            self.suppressed += 1
            return False
        self._last_signature = signature
        self.emitted += 1
        return True

    def reset(self) -> None:
        self._last_signature = None
        self.emitted = 0
        self.suppressed = 0


__all__ = ["DecisionEventGate"]
