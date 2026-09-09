"""QuantNifty runtime observability bootstrap.

Python imports sitecustomize during interpreter startup when the repository root
is on sys.path. This installs a small, explicit observability hook without
changing the existing uvicorn start command on the manually-managed Render
service. It never changes trading behavior or submits orders.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone

try:
    from fastapi import FastAPI
except Exception:
    FastAPI = None  # type: ignore[assignment,misc]


def _safe_db_diagnostic() -> dict[str, object]:
    url = (os.getenv("QUANTNIFTY_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return {"configured": False, "error": "DATABASE_URL is empty"}
    try:
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        port = parsed.port or 5432
        user = parsed.username or ""
        import psycopg
        with psycopg.connect(url, connect_timeout=5, sslmode="require") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user")
                database, current_user = cur.fetchone()
        return {"configured": True, "reachable": True, "host": host, "port": port, "user": user, "database": database, "current_user": current_user, "sslmode": "require"}
    except Exception as exc:
        message = str(exc)
        message = re.sub(r"(postgres(?:ql)?://[^:/@]+:)[^@]+(@)", r"\1***\2", message, flags=re.IGNORECASE)
        return {"configured": True, "reachable": False, "error": message[:500], "sslmode": "require"}


if FastAPI is not None:
    _original_init = FastAPI.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        if getattr(self, "title", None) != "QuantNifty Next":
            return

        try:
            from quantnifty.paper_ledger_api import router as paper_ledger_router
            self.include_router(paper_ledger_router)
        except Exception as exc:
            print(f"QUANTNIFTY_PAPER_LEDGER_ROUTE_ERROR {exc}", flush=True)

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
                        "database_diagnostic": _safe_db_diagnostic(),
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
