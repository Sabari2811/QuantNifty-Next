from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from quantnifty.after_market_lab import latest_research, run_after_market_lab
from quantnifty.live_paper_manager import LivePaperManager
from quantnifty.learning_store import load_snapshots

IST = ZoneInfo("Asia/Kolkata")
# Post-market research starts as soon as the NIFTY live-provider window closes.
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


def _reconcile_overdue_paper_position(day: str) -> None:
    """Fail closed on a persisted OPEN paper trade after the 15:29 cutoff.

    The normal live snapshot path is responsible for closing positions by the
    15:29 IST cash-session deadline. This recovery guard handles a restart or
    deploy occurring after that deadline so a durable OPEN lifecycle can never
    survive into the post-market window.
    """
    try:
        manager = LivePaperManager()
        if manager.active is None:
            return
        snapshots = load_snapshots(day)
        if not snapshots:
            logger.warning("Overdue paper position found for %s but no stored snapshot is available", day)
            return
        latest = snapshots[-1]
        manager._close(latest, {
            "strategy": "paper_recovery",
            "signal": {"direction": manager.active.direction, "confidence": None, "evidence": [], "rationale": [], "adaptive": {}},
            "risk": {"approved": False, "gates": {}, "reasons": ["POST_MARKET_OVERDUE_POSITION_GUARD"]},
            "execution_plan": {},
            "mode": "RECOVERY",
        }, "POST_MARKET_OVERDUE_POSITION_GUARD")
        logger.warning("Closed overdue persisted paper position for %s before post-market research", day)
    except Exception:
        logger.exception("Unable to reconcile overdue paper position for %s", day)


async def after_market_loop() -> None:
    last_run_day: str | None = None
    while True:
        now = datetime.now(IST)
        day = _day(now)
        if now.weekday() < 5 and now.time() >= RUN_AT and last_run_day != day:
            _reconcile_overdue_paper_position(day)
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
                    # Do not mark the day complete. The next scheduler tick retries so
                    # a transient provider/storage failure cannot silently skip training.
                    logger.exception("After-market training failed for %s; will retry", day)
        await asyncio.sleep(30)
