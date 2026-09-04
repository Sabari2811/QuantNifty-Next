from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from quantnifty.backtest import BacktestConfig, validation_report
from quantnifty.recording_loader import load_recording

router = APIRouter(prefix="/api/v1/recording", tags=["historical-validation"])


def _root() -> Path | None:
    value = (os.getenv("QUANTNIFTY_RECORDING_ROOT") or os.getenv("RECORDING_ROOT") or "").strip()
    return Path(value) if value else None


def _config(raw: dict[str, Any]) -> BacktestConfig:
    allowed = {field.name for field in fields(BacktestConfig)}
    try:
        return BacktestConfig(**{key: raw[key] for key in raw if key in allowed})
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"invalid backtest configuration: {exc}") from exc


@router.get("/status")
def recording_status() -> dict[str, Any]:
    root = _root()
    if root is None:
        return {"status": "NOT_CONFIGURED", "configured": False, "root": None}
    if not root.exists():
        return {"status": "PATH_UNAVAILABLE", "configured": True, "root": str(root)}
    bundles = sorted({path.parent for path in root.rglob("runtime.json")})
    return {
        "status": "AVAILABLE" if bundles else "NO_BUNDLES",
        "configured": True,
        "root": str(root),
        "bundles": len(bundles),
    }


@router.get("/snapshots")
def recording_snapshots() -> dict[str, Any]:
    root = _root()
    if root is None:
        raise HTTPException(503, "historical recording root is not configured")
    try:
        snapshots = load_recording(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, f"historical recording unavailable: {exc}") from exc
    return {
        "status": "OK",
        "mode": "READ_ONLY_RECORDED_HISTORICAL",
        "observations": len(snapshots),
        "snapshots": snapshots,
    }


@router.post("/validation")
def recording_validation(payload: dict[str, Any]) -> dict[str, Any]:
    root = _root()
    if root is None:
        raise HTTPException(503, "historical recording root is not configured")
    strategy = str(payload.get("strategy") or "directional").strip().lower()
    if strategy not in {"directional", "gamma_blast"}:
        raise HTTPException(400, "strategy must be directional or gamma_blast")
    try:
        snapshots = load_recording(root)
        result = validation_report(snapshots, strategy, _config(payload.get("config") or {}))
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, f"historical validation unavailable: {exc}") from exc
    result["source"] = "RECORDED_HISTORICAL"
    result["recording_root"] = str(root)
    result["empirical"] = result.get("status") == "OK" and result.get("historical_data", {}).get("status") == "VALID_HISTORICAL"
    return result
