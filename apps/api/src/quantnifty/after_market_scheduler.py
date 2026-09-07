from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from quantnifty.after_market_lab import latest_research, run_after_market_lab

IST = ZoneInfo("Asia/Kolkata")
RUN_AT = time(15, 35)
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


async def after_market_loop() -> None:
    last_run_day: str | None = None
    while True:
        now = datetime.now(IST)
        day = _day(now)
        if now.weekday() < 5 and now.time() >= RUN_AT and last_run_day != day:
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
