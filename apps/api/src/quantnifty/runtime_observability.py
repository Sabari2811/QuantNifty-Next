from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from quantnifty.learning_store import learning_status
from quantnifty.main import app, cache, live_paper

_EVIDENCE_INTERVAL_SECONDS = 30.0
_task: asyncio.Task | None = None


def _evidence() -> dict[str, Any]:
    snapshot = cache.get("snapshot")
    updated_at = cache.get("updated_at")
    learning = learning_status()
    paper = live_paper.active
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trading": "DISABLED",
        "live_provider": {
            "cached_snapshot": isinstance(snapshot, dict),
            "snapshot_timestamp": snapshot.get("timestamp") if isinstance(snapshot, dict) else None,
            "spot": snapshot.get("spot") if isinstance(snapshot, dict) else None,
            "rows": snapshot.get("rows") if isinstance(snapshot, dict) else None,
            "data_integrity": snapshot.get("data_integrity") if isinstance(snapshot, dict) else None,
            "cache_updated_epoch": updated_at,
        },
        "learning": learning,
        "paper_trade": {
            "status": "OPEN" if paper is not None else "IDLE",
            "active": isinstance(paper, dict),
        },
    }
    return evidence


def runtime_evidence() -> dict[str, Any]:
    return _evidence()


@app.get("/api/v1/runtime-evidence")
def runtime_evidence_api() -> dict[str, Any]:
    return _evidence()


async def _evidence_loop() -> None:
    while True:
        try:
            print("QUANTNIFTY_RUNTIME_EVIDENCE " + json.dumps(_evidence(), separators=(",", ":"), sort_keys=True, default=str), flush=True)
        except Exception as exc:
            print(f"QUANTNIFTY_RUNTIME_EVIDENCE_ERROR {exc}", flush=True)
        await asyncio.sleep(_EVIDENCE_INTERVAL_SECONDS)


@app.on_event("startup")
async def start_runtime_observability() -> None:
    global _task
    _task = asyncio.create_task(_evidence_loop())


@app.on_event("shutdown")
async def stop_runtime_observability() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
