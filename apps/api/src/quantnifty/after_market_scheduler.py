from __future__ import annotations

import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo

from quantnifty.after_market_lab import run_after_market_lab

IST = ZoneInfo("Asia/Kolkata")
RUN_AT = time(15, 35)


def _day(now: datetime) -> str:
    return now.astimezone(IST).date().isoformat()


async def after_market_loop() -> None:
    last_run_day: str | None = None
    while True:
        now = datetime.now(IST)
        day = _day(now)
        if now.weekday() < 5 and now.time() >= RUN_AT and last_run_day != day:
            try:
                await asyncio.to_thread(run_after_market_lab, day)
            except Exception:
                pass
            last_run_day = day
        await asyncio.sleep(30)
