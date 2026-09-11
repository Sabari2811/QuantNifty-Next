from __future__ import annotations

import os
from collections import Counter
from dataclasses import fields
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from quantnifty.backtest import BacktestConfig, _is_market_session, validation_report
from quantnifty.historical import historical_data_status
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
    if strategy not in {"directional", "gamma_blast", "adaptive"}:
        raise HTTPException(400, "strategy must be directional, gamma_blast, or adaptive")
    return strategy


@router.get("/backtest", include_in_schema=False)
def backtest_page():
    path = Path(__file__).resolve().parent / "web" / "backtest.html"
    html = path.read_text(encoding="utf-8")
    marker = '<option value="gamma_blast">Gamma Blast</option>'
    adaptive = '<option value="adaptive">Adaptive Brain</option>'
    if adaptive not in html:
        html = html.replace(marker, marker + adaptive, 1)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"})


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
        rows.append({"index": index, "timestamp": snapshot.get("timestamp"), "spot": snapshot.get("spot"), "replay": {"direction": str(signal.get("direction") or "NEUTRAL"), "confidence": signal.get("confidence"), "scores": signal.get("scores") or {}, "evidence": signal.get("evidence") or []}, "risk": {"approved": bool(risk.get("approved")), "gates": risk.get("gates") or {}, "blocked_reasons": risk.get("reasons") or []}, "execution": {"status": plan.get("status"), "instrument": plan.get("instrument"), "execution_enabled": False}, "recorded": _recorded_evidence(snapshot), "market_brain": {"regime": market_regime(snapshot, prev), "pre_move": pre_move_state(snapshot, prev), "strategy_selection": strategy_selector(snapshot, prev)}, "validation": decision.get("validation") or {}})
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
    valid_decisions = sum(1 for row in observations if (row.get("validation") or {}).get("valid") is True)
    return {"decision_observations": len(observations), "approved": approved, "blocked": len(observations) - approved, "blocked_by_reason": dict(sorted(blocked_reasons.items(), key=lambda item: (-item[1], item[0]))), "replay_signal_distribution": dict(sorted(replay_directions.items())), "recorded_signal_distribution": dict(sorted(recorded_directions.items())), "recorded_decision_distribution": dict(sorted(recorded_decisions.items())), "recorded_validation_distribution": dict(sorted(recorded_valid.items())), "replay_confidence": {"min": round(min(confidences), 2) if confidences else 0.0, "max": round(max(confidences), 2) if confidences else 0.0, "avg": round(sum(confidences) / len(confidences), 2) if confidences else 0.0}, "validation": {"valid": valid_decisions, "invalid": len(observations) - valid_decisions}, "market_brain": {"regime_distribution": dict(sorted(regime_counts.items())), "pre_move_stage_distribution": dict(sorted(pre_move_counts.items())), "strategy_selection_distribution": dict(sorted(strategy_counts.items())), "adaptive_strategy": "EXECUTION_SWITCHED" if strategy == "adaptive" else "NOT_SELECTED"}, "counterfactual": counterfactual, "observations": observations, "note": "Diagnostics use the same market-session BACKTEST FinalDecision/Risk path as validation. Counterfactuals use future spot movement only and are research evidence; recorded decisions never override replay gates."}


def _validated_result(snapshots: list[dict[str, Any]], strategy: str, config: BacktestConfig, source: str, root: str) -> dict[str, Any]:
    result = validation_report(snapshots, strategy, config)
    if str(result.get("strategy") or "").lower() != strategy:
        raise RuntimeError(f"backtest strategy mismatch: requested={strategy}, engine={result.get('strategy')}")
    overall = result.get("overall") or {}; execution_gate = dict(result.get("risk_gate") or {}); trades = int(overall.get("trades") or 0); historical_valid = result.get("status") == "OK" and result.get("historical_data", {}).get("status") == "VALID_HISTORICAL"; replay_diagnostics = _replay_diagnostics(snapshots, strategy)
    decision_gate = {"approved": int(replay_diagnostics.get("approved") or 0), "blocked": int(replay_diagnostics.get("blocked") or 0)}; total_decisions = decision_gate["approved"] + decision_gate["blocked"]; decision_gate["block_rate_pct"] = round(decision_gate["blocked"] / total_decisions * 100, 2) if total_decisions else 0.0
    result.update({"source": source, "recording_root": root, "observations": overall.get("observations", 0), "approved": decision_gate["approved"], "blocked": decision_gate["blocked"], "risk_gate": decision_gate, "execution_gate": execution_gate, "split": {"out_of_sample": result.get("oos") or {}}, "empirical": historical_valid and trades > 0, "historical_evidence_status": "VALID_HISTORICAL" if historical_valid else str((result.get("historical_data") or {}).get("status") or "UNKNOWN"), "replay_diagnostics": replay_diagnostics, "requested_strategy": strategy, "engine_strategy": result.get("strategy")})
    result["tradeability"] = "TRADEABLE_SAMPLE" if trades > 0 else "NO_EXECUTABLE_TRADES"; result["empirical_status"] = "EMPIRICAL_TRADES" if trades > 0 else "NO_EXECUTABLE_TRADES"; result["performance_status"] = "PERFORMANCE_VALIDATED" if historical_valid and trades > 0 else "NOT_VALIDATED"
    return result


@router.get("/backtest.html", include_in_schema=False)
def backtest_html_compat(): return RedirectResponse(url="/backtest", status_code=307)


def _paper_leg(snapshot: dict[str, Any], instrument: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(instrument, dict): return None
    sid = str(instrument.get("security_id") or ""); symbol = str(instrument.get("trading_symbol") or ""); strike = float(instrument.get("strike") or 0); side = str(instrument.get("side") or instrument.get("option_type") or "").upper()
    for row in snapshot.get("option_chain") or []:
        if sid and str(row.get("security_id") or "") == sid: return row
        if symbol and str(row.get("trading_symbol") or "") == symbol: return row
        if strike and abs(float(row.get("strike") or 0) - strike) < .001 and (not side or str(row.get("side") or "").upper() == side): return row
    return None


def _paper_mark(row: dict[str, Any] | None) -> tuple[float, str]:
    if not row: return 0.0, "UNAVAILABLE"
    for key, source in (("bid", "BID"), ("last_price", "LAST"), ("ask", "ASK")):
        try:
            value = float(row.get(key) or 0)
        except (TypeError, ValueError): value = 0.0
        if value > 0: return value, source
    return 0.0, "UNAVAILABLE"


@router.get("/api/v1/paper/signal")
async def paper_signal():
    """Read-only live paper-trade telemetry for the Market Brain UI."""
    try:
        from quantnifty.main import cache, live_paper, snapshot
        data = cache.get("snapshot")
        if not isinstance(data, dict): data = await snapshot()
        today = data.get("timestamp")
        active = live_paper.active
        trade = None
        if active is not None:
            instrument = live_paper.instrument if isinstance(live_paper.instrument, dict) else None
            row = _paper_leg(data, instrument)
            mark, mark_source = _paper_mark(row)
            entry = float(live_paper.entry_price or 0)
            quantity = int(live_paper.entry_quantity or 1)
            direction = str(active.direction or "NEUTRAL")
            pnl = (mark - entry) * quantity if entry > 0 and mark > 0 else 0.0
            move_pct = (mark - entry) / entry * 100.0 if entry > 0 and mark > 0 else 0.0
            favorable = move_pct if direction == "BULLISH" else -move_pct if direction == "BEARISH" else 0.0
            decision = live_paper.entry_decision if isinstance(live_paper.entry_decision, dict) else {}
            plan = decision.get("execution_plan") or {}
            stop_points = float((live_paper.entry_risk or {}).get("stop_points") or plan.get("stop_points") or 0)
            target_points = float((live_paper.entry_risk or {}).get("target_points") or plan.get("target_points") or 0)
            entry_spot = float(active.entry_spot or 0)
            sl_spot = float((live_paper.entry_risk or {}).get("stop_spot") or (entry_spot - stop_points if direction == "BULLISH" else entry_spot + stop_points if direction == "BEARISH" else 0.0))
            target_spot = float((live_paper.entry_risk or {}).get("target_spot") or (entry_spot + target_points if direction == "BULLISH" else entry_spot - target_points if direction == "BEARISH" else 0.0))
            lot_size = int(float((instrument or {}).get("lot_size") or (instrument or {}).get("lotSize") or 0))
            lots = round(quantity / lot_size, 2) if lot_size > 0 else round(quantity / 65.0, 2)
            trade = {"trade_id": active.trade_id, "trade_number": None, "status": active.status, "strategy": active.strategy, "direction": direction, "entry_timestamp": active.entry_timestamp, "entry_spot": entry_spot, "strike": (instrument or {}).get("strike"), "option_side": (instrument or {}).get("side") or (instrument or {}).get("option_type"), "symbol": (instrument or {}).get("trading_symbol"), "entry_price": round(entry, 6), "current_price": round(mark, 6), "mark_source": mark_source, "mark_timestamp": today, "quantity": quantity, "lot_size": lot_size or 65, "lots": lots, "invested_amount": round(entry * quantity, 2), "pnl": round(pnl, 2), "pnl_pct": round(move_pct, 2), "favorable_move_pct": round(favorable, 2), "movement": "UP" if move_pct > 0.01 else "DOWN" if move_pct < -0.01 else "FLAT", "mfe_pct": round(active.peak_favorable_pct, 2), "mae_pct": round(active.worst_adverse_pct, 2), "sl_spot": round(sl_spot, 2) if sl_spot else None, "target_spot": round(target_spot, 2) if target_spot else None, "stop_points": round(stop_points, 2) if stop_points else None, "target_points": round(target_points, 2) if target_points else None, "risk_reward": (live_paper.entry_risk or {}).get("risk_reward"), "risk_anchor": "ENTRY_SPOT_IMMUTABLE", "read_only": True, "execution": "NONE"}
        events = []
        try:
            from quantnifty.learning_store import load_events, trading_day
            day = trading_day(today)
            seen = set()
            for event in load_events("outcomes"):
                outcome = event.get("outcome") if isinstance(event, dict) else None
                if not isinstance(outcome, dict) or trading_day(outcome.get("entry_timestamp")) != day: continue
                tid = str(outcome.get("trade_id") or "")
                if tid and tid not in seen: seen.add(tid); events.append(outcome)
            events.sort(key=lambda x: str(x.get("entry_timestamp") or ""))
        except Exception: pass
        if trade is not None:
            trade["trade_number"] = next((i + 1 for i, item in enumerate(events) if str(item.get("trade_id")) == trade["trade_id"]), len(events) + 1)
        realized = 0.0; closed = 0; winners = 0; losers = 0
        for item in events:
            if str(item.get("status") or item.get("lifecycle") or "").upper() == "CLOSED":
                closed += 1; value = float(item.get("realized_pnl") or item.get("gross_pnl_proxy") or 0); realized += value; winners += value > 0; losers += value < 0
        return {"timestamp": today, "day": today and str(today)[:10], "status": "OPEN" if trade else "IDLE", "trading": "DISABLED", "trade": trade, "trades_today": len(events), "closed_trades": closed, "realized_pnl": round(realized, 2), "winners": winners, "losers": losers}
    except Exception as exc:
        raise HTTPException(503, f"paper signal unavailable: {exc}") from exc


@router.get("/api/v1/recording/status")
def recording_status():
    root = _root()
    if root is None: return {"status": "NOT_CONFIGURED", "configured": False, "root": None, "bundles": 0}
    if not root.exists(): return {"status": "PATH_UNAVAILABLE", "configured": True, "root": str(root), "bundles": 0}
    bundles = sorted({p.parent for p in root.rglob("runtime.json")}); return {"status": "AVAILABLE" if bundles else "NO_BUNDLES", "configured": True, "root": str(root), "bundles": len(bundles)}

@router.get("/api/v1/recording/learning-status")
def recording_learning_status():
    root = _root()
    if root is None:
        return {"status": "NOT_CONFIGURED", "learning_ready": False, "minimum_trading_days": 252, "minimum_calendar_days": 365}
    if not root.exists():
        return {"status": "PATH_UNAVAILABLE", "learning_ready": False, "root": str(root), "minimum_trading_days": 252, "minimum_calendar_days": 365}
    try:
        snapshots = load_recording(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, f"historical recording unavailable: {exc}") from exc
    result = historical_data_status(snapshots)
    result.update({"status": "OK", "mode": "READ_ONLY_RECORDED_HISTORICAL", "root": str(root)})
    return result

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
async def recording_upload_validation(file: UploadFile = File(...), strategy: str = Form("directional"), config: str = Form("{}")):
    if Path(file.filename or "").name.lower() != "data_review.txt": raise HTTPException(400, "only data_Review.txt recorder exports are accepted")
    try:
        import json
        raw_config = json.loads(config or "{}")
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


@router.get("/api/v1/final-decision")
async def unified_final_decision(strategy: str = "adaptive"):
    """Canonical live decision route; all strategies use FinalDecision and stay read-only."""
    mode = str(strategy or "adaptive").strip().lower()
    if mode not in {"directional", "gamma_blast", "adaptive"}:
        raise HTTPException(400, "strategy must be directional, gamma_blast, or adaptive")
    try:
        from quantnifty.main import cache, snapshot
        data = await snapshot()
        result = final_decision(data, cache.get("previous_snapshot"), mode, "LIVE")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"mode": "READ_ONLY", "strategy": mode, "timestamp": data.get("timestamp"), "spot": data.get("spot"), "decision": result}


@router.get("/api/v1/decision")
async def unified_decision(strategy: str = "adaptive"):
    """Compatibility route for dashboard clients; adaptive is now a first-class strategy."""
    return await unified_final_decision(strategy)


def _paper_outcomes() -> list[dict[str, Any]]:
    from quantnifty.learning_store import load_events
    rows: list[dict[str, Any]] = []
    for event in load_events("outcomes"):
        outcome = event.get("outcome") if isinstance(event, dict) else None
        if not isinstance(outcome, dict):
            continue
        if str(outcome.get("trade_id") or "") and str(outcome.get("read_only", True)).lower() == "true":
            rows.append(dict(outcome))
    return rows


def _event_snapshot_map() -> dict[str, dict[str, Any]]:
    from quantnifty.learning_store import load_events
    rows: dict[str, dict[str, Any]] = {}
    for event in load_events("snapshots"):
        if not isinstance(event, dict):
            continue
        timestamp = str(event.get("timestamp") or "")
        snapshot = event.get("snapshot")
        if timestamp and isinstance(snapshot, dict):
            rows[timestamp] = snapshot
    return rows


def _event_decision_map() -> dict[str, dict[str, Any]]:
    from quantnifty.learning_store import load_events
    rows: dict[str, dict[str, Any]] = {}
    for event in load_events("decisions"):
        if not isinstance(event, dict):
            continue
        timestamp = str(event.get("timestamp") or "")
        decision = event.get("decision")
        if timestamp and isinstance(decision, dict):
            rows[timestamp] = decision
    return rows


def _checklist(decision: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    signal = decision.get("signal") or {}; risk = decision.get("risk") or {}; plan = decision.get("execution_plan") or {}; direction = str(signal.get("direction") or outcome.get("direction") or "NEUTRAL").upper()
    gates = risk.get("gates") or {}
    checklist: dict[str, Any] = {}
    for key, value in gates.items():
        checklist[str(key)] = {"passed": bool(value), "value": value}
    checklist["directional_signal"] = {"passed": direction in {"BULLISH", "BEARISH"}, "value": direction}
    try:
        confidence = float(signal.get("confidence"))
        checklist["confidence_threshold"] = {"passed": confidence >= 60.0, "value": confidence, "threshold": 60.0}
    except (TypeError, ValueError):
        checklist["confidence_threshold"] = {"passed": False, "value": None, "unavailable": True}
    checklist["risk_approved"] = {"passed": bool(risk.get("approved")), "value": risk.get("approved")}
    checklist["execution_enabled"] = {"passed": False, "value": False, "read_only": True}
    checklist["instrument_selected"] = {"passed": isinstance(plan.get("instrument"), dict), "value": plan.get("instrument")}
    return checklist


def _trade_audit(outcome: dict[str, Any], snapshots: dict[str, dict[str, Any]], decisions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entry_ts = str(outcome.get("entry_timestamp") or "")
    snapshot = snapshots.get(entry_ts)
    decision = outcome.get("entry_decision") if isinstance(outcome.get("entry_decision"), dict) else decisions.get(entry_ts)
    decision = decision if isinstance(decision, dict) else {}
    plan = decision.get("execution_plan") or {}
    signal = decision.get("signal") or {}
    risk = decision.get("risk") or {}
    instrument = outcome.get("instrument") if isinstance(outcome.get("instrument"), dict) else plan.get("instrument")
    market = {}
    if isinstance(snapshot, dict):
        for key in ("spot", "expiry", "pcr", "call_oi", "put_oi", "call_oi_change", "put_oi_change", "gex", "dex", "vanna_proxy", "iv_skew", "atm_iv", "gamma_flip", "gamma_walls", "max_pain", "expected_move", "support", "resistance", "structure", "dealer_flow", "liquidity_score", "bullish_score", "bearish_score", "bias", "confidence", "rationale", "data_integrity", "rows", "timestamp"):
            if key in snapshot: market[key] = snapshot[key]
        market["option_chain"] = snapshot.get("option_chain") or []
        market["strike_selection"] = snapshot.get("strike_selection") or []
    missing = []
    if snapshot is None: missing.append("decision_time_snapshot")
    if not decision: missing.append("decision_record")
    if not instrument: missing.append("selected_instrument")
    if not outcome.get("entry_price"): missing.append("entry_price")
    return {"trade_id": outcome.get("trade_id"), "status": outcome.get("status"), "audit_version": "trade-audit-v1", "read_only": True, "execution": "NONE", "entry": {"timestamp": entry_ts, "spot": outcome.get("entry_spot"), "premium": outcome.get("entry_price"), "premium_source": outcome.get("entry_price_source"), "direction": outcome.get("direction"), "strategy": outcome.get("strategy"), "trigger": outcome.get("entry_trigger"), "mode": outcome.get("entry_mode"), "instrument": instrument, "quantity": outcome.get("quantity"), "risk": outcome.get("entry_risk") or {}, "risk_anchor": outcome.get("risk_anchor") or "ENTRY_SPOT_IMMUTABLE", "exit_policy": outcome.get("exit_policy") or {}}, "decision": {"timestamp": entry_ts, "strategy": decision.get("strategy"), "mode": decision.get("mode"), "signal": signal, "risk": risk, "execution_plan": plan, "entry_reasons": outcome.get("entry_reasons") or {}, "checklist": _checklist(decision, outcome)}, "market_evidence": market, "exit": {"timestamp": outcome.get("exit_timestamp"), "spot": outcome.get("exit_spot"), "premium": outcome.get("exit_price"), "premium_source": outcome.get("exit_price_source"), "reason": outcome.get("exit_reason"), "reasons": outcome.get("exit_reasons") or {}, "decision": outcome.get("exit_decision") or {}, "realized_pnl": outcome.get("realized_pnl"), "pnl_basis": outcome.get("pnl_basis")}, "learning": {"same_day_learning_eligible": str(outcome.get("status") or "").upper() == "CLOSED", "historical_learning_used_for_entry": False, "source": "LIVE_PROVIDER_DECISION_TIME_SNAPSHOT" if snapshot is not None else "UNAVAILABLE"}, "completeness": {"complete": not missing, "missing": missing, "note": "Audit values are joined to the exact durable decision/snapshot timestamp. Missing legacy fields are reported as unavailable; later snapshots are never substituted."}}


@router.get("/trade-audit", include_in_schema=False)
def trade_audit_page():
    path = Path(__file__).resolve().parent / "web" / "trade_audit.html"
    return HTMLResponse(content=path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"})


@router.get("/api/v1/paper/trade-audit")
def paper_trade_audit(day: str | None = None, trade_id: str | None = None):
    from quantnifty.learning_store import trading_day
    snapshots = _event_snapshot_map(); decisions = _event_decision_map(); rows = []
    for outcome in _paper_outcomes():
        if day and trading_day(outcome.get("entry_timestamp")) != day:
            continue
        if trade_id and str(outcome.get("trade_id")) != trade_id:
            continue
        rows.append(_trade_audit(outcome, snapshots, decisions))
    rows.sort(key=lambda item: str((item.get("entry") or {}).get("timestamp") or ""))
    return {"status": "OK", "mode": "READ_ONLY_PAPER_AUDIT", "day": day, "trading": "DISABLED", "count": len(rows), "audits": rows}
