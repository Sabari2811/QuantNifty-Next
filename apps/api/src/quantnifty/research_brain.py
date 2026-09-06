from __future__ import annotations

from collections import Counter
from typing import Any


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(a: float, b: float) -> float:
    return (a - b) / abs(b) * 100.0 if b else 0.0


def _spot(snapshot: dict[str, Any]) -> float:
    return _f(snapshot.get("spot"))


def _volume(snapshot: dict[str, Any]) -> float:
    return sum(_f(r.get("volume")) for r in snapshot.get("option_chain") or [] if isinstance(r, dict))


def _oi_pressure(snapshot: dict[str, Any]) -> tuple[float, float]:
    bull = bear = 0.0
    for row in snapshot.get("option_chain") or []:
        if not isinstance(row, dict):
            continue
        doi = _f(row.get("oi")) - _f(row.get("previous_oi"))
        price_change = _f(row.get("last_price")) - _f(row.get("previous_close"))
        weight = abs(doi) * max(_f(row.get("last_price")), 1.0)
        if doi > 0 and price_change > 0:
            bull += weight
        elif doi < 0 and price_change > 0:
            bull += weight * 0.75
        elif doi > 0 and price_change < 0:
            bear += weight
        elif doi < 0 and price_change < 0:
            bear += weight * 0.75
    return bull, bear


def pre_move_state(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Detect compression -> pressure -> trigger transitions without future data."""
    previous = previous or {}
    spot = _spot(snapshot)
    prev_spot = _spot(previous)
    em = _f((snapshot.get("expected_move") or {}).get("move"))
    prev_em = _f((previous.get("expected_move") or {}).get("move"))
    vol = _volume(snapshot)
    prev_vol = _volume(previous)
    iv = _f(snapshot.get("atm_iv"))
    prev_iv = _f(previous.get("atm_iv"))
    gex = _f(snapshot.get("gex"))
    prev_gex = _f(previous.get("gex"))
    move_pct = abs(_pct(spot, prev_spot)) if prev_spot else 0.0
    volume_change = _pct(vol, prev_vol) if prev_vol else 0.0
    em_change = _pct(em, prev_em) if prev_em else 0.0
    iv_change = _pct(iv, prev_iv) if prev_iv else 0.0
    bull_oi, bear_oi = _oi_pressure(snapshot)
    pressure_total = bull_oi + bear_oi
    pressure_bias = "BULLISH" if bull_oi > bear_oi * 1.20 else "BEARISH" if bear_oi > bull_oi * 1.20 else "NEUTRAL"
    compression = (em_change <= -3.0 if prev_em else False) or (iv_change <= -3.0 if prev_iv else False)
    pressure = pressure_total > 0 and abs(bull_oi - bear_oi) / pressure_total >= 0.15
    trigger = volume_change >= 20.0 and move_pct >= 0.05
    gamma_shift = prev_gex != 0 and ((gex > 0) != (prev_gex > 0))
    stage = "TRIGGER" if trigger else "PRESSURE" if pressure else "COMPRESSION" if compression else "BASE"
    readiness = 0.0
    readiness += 30.0 if compression else 0.0
    readiness += 35.0 if pressure else 0.0
    readiness += 35.0 if trigger else 0.0
    if gamma_shift:
        readiness += 10.0
    return {
        "stage": stage,
        "readiness_pct": round(min(100.0, readiness), 1),
        "pressure_bias": pressure_bias,
        "compression": compression,
        "pressure": pressure,
        "trigger": trigger,
        "gamma_shift": gamma_shift,
        "volume_change_pct": round(volume_change, 2),
        "expected_move_change_pct": round(em_change, 2),
        "iv_change_pct": round(iv_change, 2),
        "spot_move_pct": round(move_pct, 4),
        "bull_pressure": round(bull_oi, 2),
        "bear_pressure": round(bear_oi, 2),
    }


def market_regime(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = previous or {}
    bias = str(snapshot.get("bias") or "NEUTRAL").upper()
    liquidity = _f(snapshot.get("liquidity_score"))
    gex = _f(snapshot.get("gex"))
    flip = snapshot.get("gamma_flip")
    spot = _spot(snapshot)
    em = _f((snapshot.get("expected_move") or {}).get("move"))
    pre = pre_move_state(snapshot, previous)
    if liquidity < 35:
        regime = "LIQUIDITY_RISK"
    elif pre["trigger"] and pre["pressure_bias"] == "BULLISH":
        regime = "BREAKOUT_UP"
    elif pre["trigger"] and pre["pressure_bias"] == "BEARISH":
        regime = "BREAKDOWN_DOWN"
    elif flip is not None and abs(spot - _f(flip)) <= max(25.0, em * 0.10):
        regime = "GAMMA_TRANSITION"
    elif gex < 0 and (not previous or abs(gex) >= abs(_f(previous.get("gex")))):
        regime = "NEGATIVE_GAMMA_EXPANSION"
    elif gex > 0 and bias == "NEUTRAL":
        regime = "POSITIVE_GAMMA_RANGE"
    elif bias == "BULLISH":
        regime = "TREND_UP"
    elif bias == "BEARISH":
        regime = "TREND_DOWN"
    elif pre["compression"]:
        regime = "COMPRESSION"
    else:
        regime = "TRANSITION"
    return {"regime": regime, "bias": bias, "pre_move": pre, "liquidity": round(liquidity, 1)}


def strategy_selector(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Select the research strategy from regime, not from a hard-coded direction."""
    regime = market_regime(snapshot, previous)
    r = regime["regime"]
    if r in {"BREAKOUT_UP", "TREND_UP"}:
        selected, direction = "directional", "BULLISH"
    elif r in {"BREAKDOWN_DOWN", "TREND_DOWN"}:
        selected, direction = "directional", "BEARISH"
    elif r == "NEGATIVE_GAMMA_EXPANSION":
        selected, direction = "gamma_blast", regime["pre_move"]["pressure_bias"]
    elif r == "GAMMA_TRANSITION":
        selected, direction = "transition", regime["pre_move"]["pressure_bias"]
    elif r == "POSITIVE_GAMMA_RANGE":
        selected, direction = "range", "NEUTRAL"
    elif r == "COMPRESSION":
        selected, direction = "breakout_watch", regime["pre_move"]["pressure_bias"]
    else:
        selected, direction = "standby", "NEUTRAL"
    return {"regime": r, "selected_strategy": selected, "preferred_direction": direction, "confidence": regime["pre_move"]["readiness_pct"], "reason": f"regime={r}; stage={regime['pre_move']['stage']}"}


def _spot_outcome(snapshots: list[dict[str, Any]], entry_index: int, direction: str, stop_pct: float, target_pct: float, max_hold_bars: int) -> dict[str, Any]:
    entry = _spot(snapshots[entry_index])
    if entry <= 0:
        return {"status": "INVALID", "direction": direction}
    end = min(len(snapshots) - 1, entry_index + max(1, max_hold_bars))
    for j in range(entry_index + 1, end + 1):
        spot = _spot(snapshots[j])
        move = (spot - entry) / entry if direction == "BULLISH" else (entry - spot) / entry
        if move <= -abs(stop_pct):
            return {"status": "LOSS", "direction": direction, "exit_index": j, "reason": "STOP", "mfe_pct": round(max(0.0, move) * 100, 4), "mae_pct": round(move * 100, 4)}
        if move >= abs(target_pct):
            return {"status": "WIN", "direction": direction, "exit_index": j, "reason": "TARGET", "mfe_pct": round(move * 100, 4), "mae_pct": round(min(0.0, move) * 100, 4)}
    final = _spot(snapshots[end])
    move = (final - entry) / entry if direction == "BULLISH" else (entry - final) / entry
    return {"status": "WIN" if move > 0 else "LOSS" if move < 0 else "FLAT", "direction": direction, "exit_index": end, "reason": "TIME", "mfe_pct": round(max(0.0, move) * 100, 4), "mae_pct": round(min(0.0, move) * 100, 4)}


def counterfactual_gate_analysis(snapshots: list[dict[str, Any]], observation_rows: list[dict[str, Any]], stop_pct: float = 0.0125, target_pct: float = 0.025, max_hold_bars: int = 12) -> dict[str, Any]:
    """Evaluate blocked observations as research-only spot-direction counterfactuals."""
    blocked = [r for r in observation_rows if not r.get("risk", {}).get("approved")]
    by_reason: dict[str, list[dict[str, Any]]] = {}
    results: list[dict[str, Any]] = []
    for row in blocked:
        i = int(row["index"])
        direction = str(row.get("replay", {}).get("direction") or "NEUTRAL")
        directions = [direction] if direction in {"BULLISH", "BEARISH"} else ["BULLISH", "BEARISH"]
        outcomes = {d: _spot_outcome(snapshots, i + 1, d, stop_pct, target_pct, max_hold_bars) for d in directions if i + 1 < len(snapshots)}
        item = {"index": i, "timestamp": row.get("timestamp"), "blocked_reasons": row.get("risk", {}).get("blocked_reasons", []), "replay_direction": direction, "outcomes": outcomes, "regime": market_regime(snapshots[i], snapshots[i - 1] if i else None), "pre_move": pre_move_state(snapshots[i], snapshots[i - 1] if i else None)}
        results.append(item)
        for reason in item["blocked_reasons"]:
            by_reason.setdefault(str(reason), []).append(item)
    def summarize(items: list[dict[str, Any]], direction: str | None = None) -> dict[str, Any]:
        outcomes = []
        for item in items:
            for d, outcome in item["outcomes"].items():
                if direction is None or d == direction:
                    outcomes.append(outcome)
        wins = sum(o.get("status") == "WIN" for o in outcomes)
        losses = sum(o.get("status") == "LOSS" for o in outcomes)
        flat = sum(o.get("status") == "FLAT" for o in outcomes)
        total = wins + losses + flat
        return {"evaluated": total, "wins": wins, "losses": losses, "flat": flat, "win_rate_pct": round(wins / total * 100, 2) if total else 0.0}
    return {"method": "SPOT_DIRECTIONAL_COUNTERFACTUAL", "research_only": True, "blocked_observations": len(blocked), "all_blocked_summary": summarize(blocked), "bullish_summary": summarize(blocked, "BULLISH"), "bearish_summary": summarize(blocked, "BEARISH"), "by_block_reason": {k: summarize(v) for k, v in sorted(by_reason.items())}, "observations": results, "warning": "Counterfactual outcomes are not executed trades and use future spot movement only; they must not be mixed into empirical option P&L."}
