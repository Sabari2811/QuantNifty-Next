from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from quantnifty.backtest import BacktestConfig, validation_report
from quantnifty.recording_loader import load_recording

# Mounted once by main.py. Keep the browser compatibility route here so the
# public UI works with both /backtest and the commonly used /backtest.html URL.
router = APIRouter(tags=["historical-validation"])


def _root() -> Path | None:
    value = (os.getenv("QUANTNIFTY_RECORDING_ROOT") or os.getenv("RECORDING_ROOT") or "").strip()
    return Path(value) if value else None


def _cfg(raw: dict[str, Any]) -> BacktestConfig:
    allowed = {f.name for f in fields(BacktestConfig)}
    try:
        return BacktestConfig(**{k: raw[k] for k in raw if k in allowed})
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"invalid backtest configuration: {exc}") from exc


@router.get("/backtest.html", include_in_schema=False)
def backtest_html_compat():
    return RedirectResponse(url="/backtest", status_code=307)


@router.get("/api/v1/recording/status")
def recording_status():
    root = _root()
    if root is None:
        return {"status": "NOT_CONFIGURED", "configured": False, "root": None, "bundles": 0}
    if not root.exists():
        return {"status": "PATH_UNAVAILABLE", "configured": True, "root": str(root), "bundles": 0}
    bundles = sorted({p.parent for p in root.rglob("runtime.json")})
    return {"status": "AVAILABLE" if bundles else "NO_BUNDLES", "configured": True, "root": str(root), "bundles": len(bundles)}


@router.get("/api/v1/recording/snapshots")
def recording_snapshots():
    root = _root()
    if root is None:
        raise HTTPException(503, "historical recording root is not configured")
    try:
        snapshots = load_recording(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, f"historical recording unavailable: {exc}") from exc
    return {"status": "OK", "mode": "READ_ONLY_RECORDED_HISTORICAL", "observations": len(snapshots), "snapshots": snapshots}


@router.post("/api/v1/recording/validation")
def recording_validation(payload: dict[str, Any]):
    root = _root()
    if root is None:
        raise HTTPException(503, "historical recording root is not configured")
    strategy = str(payload.get("strategy") or "directional").strip().lower()
    if strategy not in {"directional", "gamma_blast"}:
        raise HTTPException(400, "strategy must be directional or gamma_blast")
    try:
        result = validation_report(load_recording(root), strategy, _cfg(payload.get("config") or {}))
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, f"historical validation unavailable: {exc}") from exc
    result.update({
        "source": "RECORDED_HISTORICAL",
        "recording_root": str(root),
        "empirical": result.get("status") == "OK" and result.get("historical_data", {}).get("status") == "VALID_HISTORICAL",
    })
    return result
