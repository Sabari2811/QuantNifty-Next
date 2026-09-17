from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from quantnifty.after_market_lab import latest_research, run_after_market_lab
from quantnifty.live_paper_manager import LivePaperManager
from quantnifty.learning_store import load_snapshots

IST = ZoneInfo("Asia/Kolkata")
RUN_AT = time(15, 30)
logger = logging.getLogger(__name__)


def _day(now: datetime) -> str:
    return now.astimezone(IST).date().isoformat()


def _training_already_completed(day: str) -> bool:
    """Return True only for a durable, completed daily after-market run."""
    try:
        events = latest_research(day)
    except Exception:
        logger.exception("Unable to inspect persisted after-market state for %s", day)
        return False
    for event in events:
        research = event.get("research") if isinstance(event, dict) else None
        if not isinstance(research, dict):
            continue
        if research.get("type") == "after_market" and research.get("status") == "COMPLETED" and research.get("training_source") == "STORED_DAY":
            return True
    return False


def _reconcile_overdue_paper_position(day: str, manager: LivePaperManager | None = None) -> None:
    """Fail closed on an OPEN paper trade after the 15:29 cutoff.

    Use the API's singleton manager when supplied. A second manager can close
    the durable row but leave the API's original in-memory position OPEN.
    """
    try:
        active_manager = manager or LivePaperManager()
        if active_manager.active is None:
            return
        snapshots = load_snapshots(day)
        if not snapshots:
            logger.warning("Overdue paper position found for %s but no stored snapshot is available", day)
            return
        latest = snapshots[-1]
        active_manager._close(latest, {
            "strategy": "paper_recovery",
            "signal": {"direction": active_manager.active.direction, "confidence": None, "evidence": [], "rationale": [], "adaptive": {}},
            "risk": {"approved": False, "gates": {}, "reasons": ["POST_MARKET_OVERDUE_POSITION_GUARD"]},
            "execution_plan": {},
            "mode": "RECOVERY",
        }, "POST_MARKET_OVERDUE_POSITION_GUARD")
        logger.warning("Closed overdue persisted paper position for %s before post-market research", day)
    except Exception:
        logger.exception("Unable to reconcile overdue paper position for %s", day)


async def after_market_loop(manager: LivePaperManager | None = None) -> None:
    last_run_day: str | None = None
    while True:
        now = datetime.now(IST)
        day = _day(now)
        if now.weekday() < 5 and now.time() >= RUN_AT and last_run_day != day:
            _reconcile_overdue_paper_position(day, manager)
            if _training_already_completed(day):
                last_run_day = day
            else:
                try:
                    result = await asyncio.to_thread(run_after_market_lab, day)
                    if isinstance(result, dict) and result.get("status") == "COMPLETED":
                        last_run_day = day
                    else:
                        logger.warning("After-market training not completed for %s: %s", day, result)
                except Exception:
                    logger.exception("After-market training failed for %s; will retry", day)
        await asyncio.sleep(30)
