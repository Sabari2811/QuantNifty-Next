"""QuantNifty runtime observability bootstrap.

Python imports sitecustomize during interpreter startup when the repository root
is on sys.path. This installs a small, explicit observability hook without
changing the existing uvicorn start command on the manually-managed Render
service. It never changes trading behavior or submits orders.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

try:
    from fastapi import FastAPI
except Exception:
    FastAPI = None  # type: ignore[assignment,misc]


if FastAPI is not None:
    _original_init = FastAPI.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        if getattr(self, "title", None) != "QuantNifty Next":
            return

        async def _emit_runtime_evidence() -> None:
            while True:
                try:
                    from quantnifty.learning_store import learning_status
                    from quantnifty.main import cache, live_paper

                    snapshot = cache.get("snapshot")
                    evidence = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "trading": "DISABLED",
                        "live_provider": {
                            "cached_snapshot": isinstance(snapshot, dict),
                            "snapshot_timestamp": snapshot.get("timestamp") if isinstance(snapshot, dict) else None,
                            "spot": snapshot.get("spot") if isinstance(snapshot, dict) else None,
                            "rows": snapshot.get("rows") if isinstance(snapshot, dict) else None,
                            "data_integrity": snapshot.get("data_integrity") if isinstance(snapshot, dict) else None,
                        },
                        "learning": learning_status(),
                        "paper_trade_status": "OPEN" if live_paper.active is not None else "IDLE",
                    }
                    print("QUANTNIFTY_RUNTIME_EVIDENCE " + json.dumps(evidence, separators=(",", ":"), sort_keys=True, default=str), flush=True)
                except Exception as exc:
                    print(f"QUANTNIFTY_RUNTIME_EVIDENCE_ERROR {exc}", flush=True)
                await asyncio.sleep(30.0)

        @self.on_event("startup")
        async def _start_runtime_evidence() -> None:
            self.state.quantnifty_runtime_evidence_task = asyncio.create_task(_emit_runtime_evidence())

        @self.on_event("shutdown")
        async def _stop_runtime_evidence() -> None:
            task = getattr(self.state, "quantnifty_runtime_evidence_task", None)
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    FastAPI.__init__ = _patched_init
