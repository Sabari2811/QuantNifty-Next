from __future__ import annotations

import os
from collections import Counter
from dataclasses import fields
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse

from quantnifty.backtest import BacktestConfig, validation_report
from quantnifty.institutional_engine import final_decision
from quantnifty.recording_loader import load_recording

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


def _replay_diagnostics(snapshots: list[dict[str, Any]], strategy: str) -> dict[str, Any]:
    """Explain the authoritative replay gates without changing their behavior."""
    blocked_reasons: Counter[str] = Counter()
    replay_directions: Counter[str] = Counter()
    recorded_directions: Counter[str] = Counter()
    confidences: list[float] = []
    previous = None
    decisions = 0
    approved = 0
    for snapshot in snapshots[:-1]:
        decision = final_decision(snapshot, previous, strategy, "BACKTEST")
        previous = snapshot
        decisions += 1
        signal = decision.get("signal") or {}
        direction = str(signal.get("direction") or "NEUTRAL")
        replay_directions[direction] += 1
        try:
            confidences.append(float(signal.get("confidence") or 0.0))
        except (TypeError, ValueError):
            pass
        risk = decision.get("risk") or {}
        if risk.get("approved"):
            approved += 1
        else:
            for reason in risk.get("reasons") or []:
                blocked_reasons[str(reason)] += 1
        recorded = snapshot.get("recorded_analytics") or {}
        recorded_signal = recorded.get("signal") or {}
        raw = str(recorded_signal.get("signal") or "").upper()
        if "CALL" in raw:
            recorded_directions["BULLISH"] += 1
        elif "PUT" in raw:
            recorded_directions["BEARISH"] += 1
        else:
            recorded_directions["NEUTRAL"] += 1
    return {
        "decision_observations": decisions,
        "approved": approved,
        "blocked": decisions - approved,
        "blocked_by_reason": dict(sorted(blocked_reasons.items(), key=lambda item: (-item[1], item[0]))),
        "replay_signal_distribution": dict(sorted(replay_directions.items())),
        "recorded_signal_distribution": dict(sorted(recorded_directions.items())),
        "replay_confidence": {
            "min": round(min(confidences), 2) if confidences else 0.0,
            "max": round(max(confidences), 2) if confidences else 0.0,
            "avg": round(sum(confidences) / len(confidences), 2) if confidences else 0.0,
        },
        "note": "Diagnostics describe the same BACKTEST FinalDecision/Risk path used by validation; they do not alter gates or create trades.",
    }


def _validated_result(snapshots: list[dict[str, Any]], strategy: str, config: BacktestConfig, source: str, root: str) -> dict[str, Any]:
    result = validation_report(snapshots, strategy, config)
    overall = result.get("overall") or {}
    risk_gate = result.get("risk_gate") or {}
    # Keep the compact validation response compatible with the existing UI,
    # while retaining the canonical validation_report fields.
    result.update({
        "source": source,
        "recording_root": root,
        "observations": overall.get("observations", 0),
        "approved": risk_gate.get("approved", 0),
        "blocked": risk_gate.get("blocked", 0),
        "split": {"out_of_sample": result.get("oos") or {}},
        "empirical": result.get("status") == "OK" and result.get("historical_data", {}).get("status") == "VALID_HISTORICAL",
        "replay_diagnostics": _replay_diagnostics(snapshots, strategy),
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
async def recording_upload_validation(file: UploadFile = File(...), strategy: str = "directional", config: str = "{}"):
    """Run read-only historical validation from an uploaded data_Review export."""
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
