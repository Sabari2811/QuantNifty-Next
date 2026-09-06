from __future__ import annotations

import os
from collections import Counter
from dataclasses import fields
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse

from quantnifty.backtest import BacktestConfig, _is_market_session, validation_report
from quantnifty.institutional_engine import final_decision
from quantnifty.recording_loader import load_recording
from quantnifty.research_brain import counterfactual_gate_analysis, market_regime, pre_move_state, strategy_selector

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


def _recorded_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    recorded = snapshot.get("recorded_analytics") or {}
    recorded_signal = recorded.get("signal") or {}
    raw_signal = str(recorded_signal.get("signal") or "").upper()
    recorded_decision = snapshot.get("recorded_decision") or {}
    validation = recorded_decision.get("validation") or {}
    return {"signal": raw_signal or "UNKNOWN", "signal_confidence": recorded_signal.get("confidence"), "direction": "BULLISH" if "CALL" in raw_signal else "BEARISH" if "PUT" in raw_signal else "NEUTRAL", "decision": str((recorded_decision.get("signal") or {}).get("name") or "UNKNOWN").upper(), "validation": "VALID" if validation.get("valid") is True else "INVALID" if validation.get("valid") is False else "UNKNOWN", "strike_selection": recorded.get("strike_selection") or [], "institutional_score": recorded.get("recorded_institutional_score") or {}}


def _observation_diagnostics(snapshots: list[dict[str, Any]], strategy: str) -> list[dict[str, Any]]:
    ordered = [snapshot for snapshot in snapshots if _is_market_session(snapshot)]
    rows: list[dict[str, Any]] = []
    previous = None
    for index, snapshot in enumerate(ordered[:-1]):
        decision = final_decision(snapshot, previous, strategy, "BACKTEST"); previous = snapshot
        signal = decision.get("signal") or {}; risk = decision.get("risk") or {}; plan = decision.get("execution_plan") or {}; prev = ordered[index - 1] if index else None
        rows.append({"index": index, "timestamp": snapshot.get("timestamp"), "spot": snapshot.get("spot"), "replay": {"direction": str(signal.get("direction") or "NEUTRAL"), "confidence": signal.get("confidence"), "scores": signal.get("scores") or {}, "evidence": signal.get("evidence") or []}, "risk": {"approved": bool(risk.get("approved")), "gates": risk.get("gates") or {}, "blocked_reasons": risk.get("reasons") or []}, "execution": {"status": plan.get("status"), "instrument": plan.get("instrument"), "execution_enabled": False}, "recorded": _recorded_evidence(snapshot), "market_brain": {"regime": market_regime(snapshot, prev), "pre_move": pre_move_state(snapshot, prev), "strategy_selection": strategy_selector(snapshot, prev)}})
    return rows


def _replay_diagnostics(snapshots: list[dict[str, Any]], strategy: str) -> dict[str, Any]:
    blocked_reasons: Counter[str] = Counter(); replay_directions: Counter[str] = Counter(); recorded_directions: Counter[str] = Counter(); recorded_decisions: Counter[str] = Counter(); recorded_valid: Counter[str] = Counter(); confidences: list[float] = []
    observations = _observation_diagnostics(snapshots, strategy)
    for row in observations:
        replay_directions[row["replay"]["direction"]] += 1
        try: confidences.append(float(row["replay"].get("confidence") or 0.0))
        except (TypeError, ValueError): pass
        if not row["risk"]["approved"]:
            for reason in row["risk"]["blocked_reasons"]: blocked_reasons[str(reason)] += 1
        recorded = row["recorded"]; recorded_directions[recorded["direction"]] += 1; recorded_decisions[recorded["decision"]] += 1; recorded_valid[recorded["validation"]] += 1
    approved = sum(1 for row in observations if row["risk"]["approved"])
    counterfactual = counterfactual_gate_analysis(snapshots, observations)
    strategy_counts = Counter(row["market_brain"]["strategy_selection"]["selected_strategy"] for row in observations); regime_counts = Counter(row["market_brain"]["regime"]["regime"] for row in observations); pre_move_counts = Counter(row["market_brain"]["pre_move"]["stage"] for row in observations)
    return {"decision_observations": len(observations), "approved": approved, "blocked": len(observations) - approved, "blocked_by_reason": dict(sorted(blocked_reasons.items(), key=lambda item: (-item[1], item[0]))), "replay_signal_distribution": dict(sorted(replay_directions.items())), "recorded_signal_distribution": dict(sorted(recorded_directions.items())), "recorded_decision_distribution": dict(sorted(recorded_decisions.items())), "recorded_validation_distribution": dict(sorted(recorded_valid.items())), "replay_confidence": {"min": round(min(confidences), 2) if confidences else 0.0, "max": round(max(confidences), 2) if confidences else 0.0, "avg": round(sum(confidences) / len(confidences), 2) if confidences else 0.0}, "market_brain": {"regime_distribution": dict(sorted(regime_counts.items())), "pre_move_stage_distribution": dict(sorted(pre_move_counts.items())), "strategy_selection_distribution": dict(sorted(strategy_counts.items())), "adaptive_strategy": "RESEARCH_ONLY_NOT_EXECUTION_SWITCHED"}, "counterfactual": counterfactual, "observations": observations, "note": "Diagnostics use the same market-session BACKTEST FinalDecision/Risk path as validation. Counterfactuals use future spot movement only and are research evidence; recorded decisions never override replay gates."}


def _validated_result(snapshots: list[dict[str, Any]], strategy: str, config: BacktestConfig, source: str, root: str) -> dict[str, Any]:
    result = validation_report(snapshots, strategy, config); overall = result.get("overall") or {}; execution_gate = dict(result.get("risk_gate") or {}); trades = int(overall.get("trades") or 0); historical_valid = result.get("status") == "OK" and result.get("historical_data", {}).get("status") == "VALID_HISTORICAL"; replay_diagnostics = _replay_diagnostics(snapshots, strategy)
    decision_gate = {"approved": int(replay_diagnostics.get("approved") or 0), "blocked": int(replay_diagnostics.get("blocked") or 0)}; total_decisions = decision_gate["approved"] + decision_gate["blocked"]; decision_gate["block_rate_pct"] = round(decision_gate["blocked"] / total_decisions * 100, 2) if total_decisions else 0.0
    result.update({"source": source, "recording_root": root, "observations": overall.get("observations", 0), "approved": decision_gate["approved"], "blocked": decision_gate["blocked"], "risk_gate": decision_gate, "execution_gate": execution_gate, "split": {"out_of_sample": result.get("oos") or {}}, "empirical": historical_valid and trades > 0, "historical_evidence_status": "VALID_HISTORICAL" if historical_valid else str((result.get("historical_data") or {}).get("status") or "UNKNOWN"), "replay_diagnostics": replay_diagnostics})
    result["tradeability"] = "TRADEABLE_SAMPLE" if trades > 0 else "NO_EXECUTABLE_TRADES"; result["empirical_status"] = "EMPIRICAL_TRADES" if trades > 0 else "NO_EXECUTABLE_TRADES"; result["performance_status"] = "PERFORMANCE_VALIDATED" if historical_valid and trades > 0 else "NOT_VALIDATED"
    return result


@router.get("/backtest.html", include_in_schema=False)
def backtest_html_compat(): return RedirectResponse(url="/backtest", status_code=307)

@router.get("/api/v1/recording/status")
def recording_status():
    root = _root()
    if root is None: return {"status": "NOT_CONFIGURED", "configured": False, "root": None, "bundles": 0}
    if not root.exists(): return {"status": "PATH_UNAVAILABLE", "configured": True, "root": str(root), "bundles": 0}
    bundles = sorted({p.parent for p in root.rglob("runtime.json")}); return {"status": "AVAILABLE" if bundles else "NO_BUNDLES", "configured": True, "root": str(root), "bundles": len(bundles)}

@router.get("/api/v1/recording/snapshots")
def recording_snapshots():
    root = _root()
    if root is None: raise HTTPException(503, "historical recording root is not configured")
    try: snapshots = load_recording(root)
    except (OSError, RuntimeError, ValueError) as exc: raise HTTPException(503, f"historical recording unavailable: {exc}") from exc
    return {"status": "OK", "mode": "READ_ONLY_RECORDED_HISTORICAL", "observations": len(snapshots), "snapshots": snapshots}

@router.post("/api/v1/recording/validation")
def recording_validation(payload: dict[str, Any]):
    root = _root()
    if root is None: raise HTTPException(503, "historical recording root is not configured")
    try: result = _validated_result(load_recording(root), _strategy(payload), _cfg(payload.get("config") or {}), "RECORDED_HISTORICAL", str(root))
    except (OSError, RuntimeError, ValueError) as exc: raise HTTPException(503, f"historical validation unavailable: {exc}") from exc
    return result

@router.post("/api/v1/recording/upload-validation")
async def recording_upload_validation(file: UploadFile = File(...), strategy: str = "directional", config: str = "{}"):
    if Path(file.filename or "").name.lower() != "data_review.txt": raise HTTPException(400, "only data_Review.txt recorder exports are accepted")
    try:
        import json
        raw_config = json.loads(config or "{}");
        if not isinstance(raw_config, dict): raise ValueError("config must be a JSON object")
        selected_strategy = _strategy({"strategy": strategy}); cfg = _cfg(raw_config)
    except (json.JSONDecodeError, TypeError, ValueError) as exc: raise HTTPException(400, f"invalid upload configuration: {exc}") from exc
    total = 0
    try:
        with NamedTemporaryFile(prefix="quantnifty-report-", suffix=".txt") as temp:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk: break
                total += len(chunk)
                if total > MAX_REPORT_BYTES: raise HTTPException(413, f"report exceeds {MAX_REPORT_BYTES // (1024 * 1024)} MiB limit")
                temp.write(chunk)
            temp.flush(); snapshots = load_recording(temp.name); result = _validated_result(snapshots, selected_strategy, cfg, "UPLOADED_RECORDED_HISTORICAL", "ephemeral-upload"); result["uploaded_bytes"] = total; return result
    except HTTPException: raise
    except (OSError, RuntimeError, ValueError) as exc: raise HTTPException(422, f"historical report could not be validated: {exc}") from exc
    finally: await file.close()
