from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse

from quantnifty.backtest import BacktestConfig, validation_report
from quantnifty.recording_loader import load_recording

# Mounted once by main.py. Keep the browser compatibility route here so the
# public UI works with both /backtest and the commonly used /backtest.html URL.
router = APIRouter(tags=["historical-validation"])
MAX_REPORT_BYTES = 25 * 1024 * 1024


def _root() -> Path | None:
    value = (os.getenv("QUANTNIFTY_RECORDING_ROOT") or os.getenv("RECORDING_ROOT") or "").strip()
    return Path(value) if value else None


def _cfg(raw: dict[str, Any]) -> BacktestConfig:
    allowed = {f.name for f in fields(BacktestConfig)}
    try:
        return BacktestConfig(**{k: raw[k] for k in raw if k in allowed})
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"invalid backtest configuration: {exc}") from exc


def _strategy(payload: dict[str, Any]) -> str:
    strategy = str(payload.get("strategy") or "directional").strip().lower()
    if strategy not in {"directional", "gamma_blast"}:
        raise HTTPException(400, "strategy must be directional or gamma_blast")
    return strategy


def _validated_result(snapshots: list[dict[str, Any]], strategy: str, config: BacktestConfig, source: str, root: str) -> dict[str, Any]:
    result = validation_report(snapshots, strategy, config)
    result.update({
        "source": source,
        "recording_root": root,
        "empirical": result.get("status") == "OK" and result.get("historical_data", {}).get("status") == "VALID_HISTORICAL",
    })
    return result


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
    try:
        result = _validated_result(load_recording(root), _strategy(payload), _cfg(payload.get("config") or {}), "RECORDED_HISTORICAL", str(root))
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, f"historical validation unavailable: {exc}") from exc
    return result


@router.post("/api/v1/recording/upload-validation")
async def recording_upload_validation(
    file: UploadFile = File(...),
    strategy: str = "directional",
    config: str = "{}",
):
    """Run read-only historical validation from an uploaded data_Review export.

    The upload is streamed to an ephemeral temporary file and removed after
    validation. It is never persisted as application data.
    """
    if Path(file.filename or "").name.lower() != "data_review.txt":
        raise HTTPException(400, "only data_Review.txt recorder exports are accepted")
    try:
        import json
        raw_config = json.loads(config or "{}")
        if not isinstance(raw_config, dict):
            raise ValueError("config must be a JSON object")
        selected_strategy = _strategy({"strategy": strategy})
        cfg = _cfg(raw_config)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(400, f"invalid upload configuration: {exc}") from exc

    total = 0
    try:
        with NamedTemporaryFile(prefix="quantnifty-report-", suffix=".txt") as temp:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_REPORT_BYTES:
                    raise HTTPException(413, f"report exceeds {MAX_REPORT_BYTES // (1024 * 1024)} MiB limit")
                temp.write(chunk)
            temp.flush()
            snapshots = load_recording(temp.name)
            result = _validated_result(snapshots, selected_strategy, cfg, "UPLOADED_RECORDED_HISTORICAL", "ephemeral-upload")
            result["uploaded_bytes"] = total
            return result
    except HTTPException:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(422, f"historical report could not be validated: {exc}") from exc
    finally:
        await file.close()
