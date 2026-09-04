from __future__ import annotations

from typing import Any
import math


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(a: float, b: float) -> float:
    return (a - b) / abs(b) * 100.0 if b else 0.0


def gamma_flip_detector(data: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    spot = _f(data.get("spot")); flip = data.get("gamma_flip")
    prev_spot = _f((previous or {}).get("spot")); prev_flip = (previous or {}).get("gamma_flip")
    distance = None if flip is None else spot - _f(flip)
    prev_distance = None if prev_flip is None else prev_spot - _f(prev_flip)
    regime = "POSITIVE_GAMMA" if distance is not None and distance > 0 else "NEGATIVE_GAMMA" if distance is not None else "UNKNOWN"
    crossed = bool(distance is not None and prev_distance is not None and distance * prev_distance < 0)
    return {"gamma_flip": flip, "distance_points": None if distance is None else round(distance, 2), "regime": regime, "crossed": crossed, "transition": "NEGATIVE_TO_POSITIVE" if crossed and distance > 0 else "POSITIVE_TO_NEGATIVE" if crossed else None}


def _flow_label(row: dict[str, Any]) -> str:
    oi = _f(row.get("oi")); prev_oi = _f(row.get("previous_oi")); price = _f(row.get("last_price")); prev_price = _f(row.get("previous_close"))
    doi = oi - prev_oi; dp = price - prev_price
    if abs(doi) < max(1.0, abs(oi) * 0.002): return "NEUTRAL"
    if dp > 0 and doi > 0: return "LONG_BUILDUP"
    if dp < 0 and doi > 0: return "SHORT_BUILDUP"
    if dp > 0 and doi < 0: return "SHORT_COVERING"
    if dp < 0 and doi < 0: return "LONG_UNWINDING"
    return "NEUTRAL"


def oi_flow_analyzer(data: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}; notional: dict[str, float] = {}
    by_side: dict[str, dict[str, float]] = {"CE": {}, "PE": {}}
    rows = data.get("option_chain") or []
    classified = []
    for r in rows:
        flow = _flow_label(r); counts[flow] = counts.get(flow, 0) + 1
        side = str(r.get("side") or "").upper(); doi = _f(r.get("oi")) - _f(r.get("previous_oi")); weight = abs(doi) * max(_f(r.get("last_price")), 1.0)
        notional[flow] = notional.get(flow, 0.0) + weight
        if side in by_side: by_side[side][flow] = by_side[side].get(flow, 0.0) + weight
        classified.append({"strike": r.get("strike"), "side": side, "flow": flow, "oi_change": round(doi, 2), "price_change": round(_f(r.get("last_price")) - _f(r.get("previous_close")), 4)})
    dominant = max(notional, key=notional.get) if notional else "NEUTRAL"
    directional = {"BULLISH": notional.get("SHORT_COVERING", 0) + notional.get("LONG_BUILDUP", 0), "BEARISH": notional.get("SHORT_BUILDUP", 0) + notional.get("LONG_UNWINDING", 0)}
    bias = "BULLISH" if directional["BULLISH"] > directional["BEARISH"] * 1.15 else "BEARISH" if directional["BEARISH"] > directional["BULLISH"] * 1.15 else "NEUTRAL"
    return {"dominant_flow": dominant, "bias": bias, "counts": counts, "notional": {k: round(v, 2) for k, v in notional.items()}, "by_side": by_side, "rows": classified}


def volatility_engine(data: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = previous or {}; iv = _f(data.get("atm_iv")); piv = _f(previous.get("atm_iv")); skew = data.get("iv_skew"); pskew = previous.get("iv_skew")
    em = _f((data.get("expected_move") or {}).get("move")); pem = _f((previous.get("expected_move") or {}).get("move"))
    iv_change = _pct(iv, piv) if piv else 0.0; em_change = _pct(em, pem) if pem else 0.0
    if iv_change >= 8 or em_change >= 8: regime = "VOL_EXPANSION"
    elif iv_change <= -8 or em_change <= -8: regime = "VOL_CONTRACTION"
    else: regime = "VOL_STABLE"
    consumption = None
    if em > 0 and data.get("gamma_flip") is not None:
        consumption = min(200.0, abs(_f(data.get("spot")) - _f(data.get("gamma_flip"))) / em * 100.0)
    return {"regime": regime, "atm_iv": iv, "iv_change_pct": round(iv_change, 2), "iv_skew": skew, "skew_change": None if skew is None or pskew is None else round(_f(skew) - _f(pskew), 3), "expected_move": em, "expected_move_change_pct": round(em_change, 2), "expected_move_consumption_pct": None if consumption is None else round(consumption, 1)}


def dealer_position_engine(data: dict[str, Any], oi: dict[str, Any], volatility: dict[str, Any]) -> dict[str, Any]:
    gex = _f(data.get("gex")); dex = _f(data.get("dex")); vanna = _f(data.get("vanna_proxy")); flow = oi.get("bias", "NEUTRAL")
    gamma_regime = "POSITIVE" if gex > 0 else "NEGATIVE" if gex < 0 else "NEUTRAL"
    pressure = "BULLISH" if dex > 0 else "BEARISH" if dex < 0 else "NEUTRAL"
    if flow == pressure and flow != "NEUTRAL": alignment = "CONFIRMED"
    elif flow == "NEUTRAL" or pressure == "NEUTRAL": alignment = "MIXED"
    else: alignment = "CONFLICTING"
    return {"gex": gex, "dex": dex, "vanna_proxy": vanna, "gamma_regime": gamma_regime, "delta_pressure": pressure, "oi_flow_bias": flow, "alignment": alignment, "volatility_regime": volatility.get("regime")}


def institutional_signal(data: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    oi = oi_flow_analyzer(data); vol = volatility_engine(data, previous); gamma = gamma_flip_detector(data, previous); dealer = dealer_position_engine(data, oi, vol)
    raw = {"BULLISH": 0.0, "BEARISH": 0.0, "NEUTRAL": 0.0}
    base = str(data.get("bias") or "NEUTRAL")
    if base in raw: raw[base] += 25
    raw[oi["bias"]] += 25
    raw[dealer["delta_pressure"]] += 20
    if dealer["alignment"] == "CONFIRMED": raw[oi["bias"]] += 15
    elif dealer["alignment"] == "CONFLICTING": raw["NEUTRAL"] += 10
    if gamma["regime"] == "NEGATIVE_GAMMA": raw[base] += 5 if base != "NEUTRAL" else 0
    if vol["regime"] == "VOL_EXPANSION" and base != "NEUTRAL": raw[base] += 5
    winner = max((k for k in raw if k != "NEUTRAL"), key=lambda k: raw[k])
    edge = raw[winner] - raw["NEUTRAL"]
    confidence = min(99.0, max(0.0, 50.0 + edge * 0.55))
    if raw[winner] < 50 or edge < 15: direction = "NEUTRAL"
    else: direction = winner
    evidence = []
    if base != "NEUTRAL": evidence.append(f"base analytics bias {base}")
    if oi["bias"] != "NEUTRAL": evidence.append(f"OI flow {oi['bias']}")
    if dealer["alignment"] == "CONFIRMED": evidence.append("dealer and OI pressure aligned")
    if gamma["crossed"]: evidence.append(f"gamma flip transition {gamma['transition']}")
    if vol["regime"] == "VOL_EXPANSION": evidence.append("volatility expansion")
    return {"direction": direction, "confidence": round(confidence, 1), "scores": {k: round(v, 1) for k, v in raw.items()}, "evidence": evidence, "gamma": gamma, "oi_flow": oi, "volatility": vol, "dealer": dealer}


def risk_engine(data: dict[str, Any], signal: dict[str, Any], strategy: str = "directional") -> dict[str, Any]:
    state = ((data.get("intelligence") or {}).get("market_state") or {}).get("state") or ""
    gates = {
        "direction": signal.get("direction") in {"BULLISH", "BEARISH"},
        "confidence": _f(signal.get("confidence")) >= 60,
        "liquidity": _f(data.get("liquidity_score")) >= 50,
        "market_state": state not in {"LIQUIDITY_RISK", "COMPRESSION"},
        "data_integrity": data.get("data_integrity") == "LIVE_PROVIDER",
    }
    if strategy == "gamma_blast":
        gates["gamma_regime"] = signal.get("gamma", {}).get("regime") == "NEGATIVE_GAMMA"
        gates["volatility"] = signal.get("volatility", {}).get("regime") == "VOL_EXPANSION"
    reasons = [k for k, ok in gates.items() if not ok]
    return {"strategy": strategy, "gates": gates, "approved": not reasons, "reasons": reasons, "max_risk_pct": 0.5 if strategy == "gamma_blast" else 1.0}


def execution_plan(data: dict[str, Any], signal: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
    approved = bool(risk.get("approved")); direction = signal.get("direction", "NEUTRAL"); selections = data.get("strike_selection") or []
    if isinstance(selections, dict): selections = selections.get("candidates") or selections.get("strikes") or []
    chosen = selections[0] if selections else None
    spot = _f(data.get("spot")); em = _f((data.get("expected_move") or {}).get("move")); stop_distance = max(em * 0.35, spot * 0.002) if em else spot * 0.002; target_distance = stop_distance * 2
    return {"status": "APPROVED_READ_ONLY" if approved else "BLOCKED", "execution_enabled": False, "direction": direction, "instrument": chosen, "entry": "WAIT_FOR_TRIGGER" if approved else None, "stop_points": round(stop_distance, 2) if approved else None, "target_points": round(target_distance, 2) if approved else None, "risk_reward": 2.0 if approved else None, "order_action": "DISABLED", "note": "Plan only. No broker order can be submitted by this engine."}


def final_decision(data: dict[str, Any], previous: dict[str, Any] | None = None, strategy: str = "directional") -> dict[str, Any]:
    signal = institutional_signal(data, previous); risk = risk_engine(data, signal, strategy); plan = execution_plan(data, signal, risk)
    return {"signal": signal, "risk": risk, "execution_plan": plan, "status": "TRADE_CANDIDATE" if risk["approved"] else "NO_TRADE", "authoritative": "FINAL_DECISION", "trading": "DISABLED"}


def replay_signal_stack(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    results = []; previous = None
    for snap in snapshots:
        result = final_decision(snap, previous, "directional"); results.append({"timestamp": snap.get("timestamp"), "spot": snap.get("spot"), "decision": result})
        previous = snap
    candidates = sum(r["decision"]["status"] == "TRADE_CANDIDATE" for r in results)
    return {"count": len(results), "trade_candidates": candidates, "no_trade": len(results) - candidates, "results": results, "signal_neutral": True, "orders_placed": 0}
