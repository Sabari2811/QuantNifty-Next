from __future__ import annotations

from typing import Any


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(a: float, b: float) -> float:
    return (a - b) / abs(b) * 100.0 if b else 0.0


def gamma_flip_detector(data: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    spot = _f(data.get("spot")); flip = data.get("gamma_flip")
    prev = previous or {}; prev_spot = _f(prev.get("spot")); prev_flip = prev.get("gamma_flip")
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
    counts: dict[str, int] = {}; notional: dict[str, float] = {}; by_side: dict[str, dict[str, float]] = {"CE": {}, "PE": {}}
    for r in data.get("option_chain") or []:
        flow = _flow_label(r); counts[flow] = counts.get(flow, 0) + 1
        side = str(r.get("side") or "").upper(); doi = _f(r.get("oi")) - _f(r.get("previous_oi")); weight = abs(doi) * max(_f(r.get("last_price")), 1.0)
        notional[flow] = notional.get(flow, 0.0) + weight
        if side in by_side: by_side[side][flow] = by_side[side].get(flow, 0.0) + weight
    recorded = str(data.get("recorded_oi_flow_bias") or "").upper()
    if recorded in {"BULLISH", "BEARISH", "NEUTRAL"}: bias = recorded
    else:
        bull = notional.get("SHORT_COVERING", 0) + notional.get("LONG_BUILDUP", 0); bear = notional.get("SHORT_BUILDUP", 0) + notional.get("LONG_UNWINDING", 0)
        bias = "BULLISH" if bull > bear * 1.15 else "BEARISH" if bear > bull * 1.15 else "NEUTRAL"
    return {"dominant_flow": max(notional, key=notional.get) if notional else "NEUTRAL", "bias": bias, "counts": counts, "notional": {k: round(v, 2) for k, v in notional.items()}, "by_side": by_side}


def volatility_engine(data: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    prev = previous or {}; iv = _f(data.get("atm_iv")); piv = _f(prev.get("atm_iv")); skew = data.get("iv_skew"); pskew = prev.get("iv_skew")
    em = _f((data.get("expected_move") or {}).get("move")); pem = _f((prev.get("expected_move") or {}).get("move"))
    iv_change = _pct(iv, piv) if piv else 0.0; em_change = _pct(em, pem) if pem else 0.0
    regime = "VOL_EXPANSION" if iv_change >= 8 or em_change >= 8 else "VOL_CONTRACTION" if iv_change <= -8 or em_change <= -8 else "VOL_STABLE"
    return {"regime": regime, "atm_iv": iv, "iv_change_pct": round(iv_change, 2), "iv_skew": skew, "skew_change": None if skew is None or pskew is None else round(_f(skew)-_f(pskew), 3), "expected_move": em, "expected_move_change_pct": round(em_change, 2)}


def dealer_position_engine(data: dict[str, Any], oi: dict[str, Any], volatility: dict[str, Any]) -> dict[str, Any]:
    gex = _f(data.get("gex")); dex = _f(data.get("dex")); vanna = _f(data.get("vanna_proxy")); flow = oi.get("bias", "NEUTRAL")
    gamma_regime = "POSITIVE" if gex > 0 else "NEGATIVE" if gex < 0 else "NEUTRAL"; pressure = "BULLISH" if dex > 0 else "BEARISH" if dex < 0 else "NEUTRAL"
    alignment = "CONFIRMED" if flow == pressure and flow != "NEUTRAL" else "MIXED" if flow == "NEUTRAL" or pressure == "NEUTRAL" else "CONFLICTING"
    return {"gex": gex, "dex": dex, "vanna_proxy": vanna, "gamma_regime": gamma_regime, "delta_pressure": pressure, "oi_flow_bias": flow, "alignment": alignment, "volatility_regime": volatility.get("regime")}


def _canonical_evidence(data: dict[str, Any]) -> dict[str, Any]:
    """Read optional evidence preserved from historical analytics without using recorded decisions as authority."""
    probability = data.get("probability") or {}; technical = data.get("technical") or {}; ema = technical.get("ema") or {}; rsi = technical.get("rsi") or {}; vwap = technical.get("vwap") or {}
    pcr = data.get("pcr") or {}; iv = data.get("iv_skew_details") or {}; institutional = data.get("recorded_institutional_score") or {}
    return {"bullish_probability": _f(probability.get("bullish_probability")), "bearish_probability": _f(probability.get("bearish_probability")), "probability_confidence": _f(probability.get("confidence")), "ema_trend": str(ema.get("trend") or "").upper(), "rsi_state": str(rsi.get("state") or "").upper(), "vwap_position": str(vwap.get("position") or vwap.get("status") or "").upper(), "pcr_bias": str(pcr.get("bias") or "").upper(), "pcr_sentiment": str(pcr.get("sentiment") or "").upper(), "iv_bias": str(iv.get("iv_bias") or data.get("recorded_iv_bias") or "").upper(), "institutional": institutional}


def institutional_signal(data: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    oi = oi_flow_analyzer(data); vol = volatility_engine(data, previous); gamma = gamma_flip_detector(data, previous); dealer = dealer_position_engine(data, oi, vol); ev = _canonical_evidence(data)
    raw = {"BULLISH": 0.0, "BEARISH": 0.0, "NEUTRAL": 0.0}; evidence: list[str] = []
    base = str(data.get("bias") or "NEUTRAL").upper()
    if base in raw and base != "NEUTRAL": raw[base] += 20; evidence.append(f"market structure {base}")
    if oi["bias"] in raw and oi["bias"] != "NEUTRAL": raw[oi["bias"]] += 20; evidence.append(f"OI flow {oi['bias']}")
    if dealer["delta_pressure"] in raw and dealer["delta_pressure"] != "NEUTRAL": raw[dealer["delta_pressure"]] += 15; evidence.append(f"dealer delta {dealer['delta_pressure']}")
    if dealer["alignment"] == "CONFIRMED": raw[oi["bias"]] += 10
    elif dealer["alignment"] == "CONFLICTING": raw["NEUTRAL"] += 10
    # Historical recorder analytics include probability/technical evidence. These are inputs, not recorded decisions.
    if ev["bullish_probability"] or ev["bearish_probability"]:
        if ev["bullish_probability"] - ev["bearish_probability"] >= 20: raw["BULLISH"] += min(25.0, (ev["bullish_probability"]-50.0) * 0.35); evidence.append("historical bullish probability")
        elif ev["bearish_probability"] - ev["bullish_probability"] >= 20: raw["BEARISH"] += min(25.0, (ev["bearish_probability"]-50.0) * 0.35); evidence.append("historical bearish probability")
    trend = ev["ema_trend"]
    if "BULLISH" in trend: raw["BULLISH"] += 10; evidence.append("EMA trend bullish")
    elif "BEARISH" in trend: raw["BEARISH"] += 10; evidence.append("EMA trend bearish")
    if ev["vwap_position"] == "ABOVE": raw["BULLISH"] += 5
    elif ev["vwap_position"] == "BELOW": raw["BEARISH"] += 5
    if ev["pcr_bias"] in {"BULLISH", "BEARISH"}: raw[ev["pcr_bias"]] += 5; evidence.append(f"PCR {ev['pcr_bias']}")
    if ev["iv_bias"] in {"BULLISH", "BEARISH"}: raw[ev["iv_bias"]] += 5
    if gamma["regime"] == "NEGATIVE":
        if base in {"BULLISH", "BEARISH"}: raw[base] += 5
    winner = max((k for k in raw if k != "NEUTRAL"), key=lambda k: raw[k]); edge = raw[winner] - raw["NEUTRAL"]
    confidence = min(99.0, max(0.0, 50.0 + edge * 0.55))
    direction = winner if raw[winner] >= 50 and edge >= 15 else "NEUTRAL"
    if ev["probability_confidence"] >= 70 and ((ev["bullish_probability"]-ev["bearish_probability"] >= 35) or (ev["bearish_probability"]-ev["bullish_probability"] >= 35)):
        direction = "BULLISH" if ev["bullish_probability"] > ev["bearish_probability"] else "BEARISH"
        confidence = max(confidence, ev["probability_confidence"])
    return {"direction": direction, "confidence": round(confidence, 1), "scores": {k: round(v, 1) for k, v in raw.items()}, "evidence": evidence, "gamma": gamma, "oi_flow": oi, "volatility": vol, "dealer": dealer, "historical_evidence": ev}


def risk_engine(data: dict[str, Any], signal: dict[str, Any], strategy: str = "directional", mode: str = "LIVE") -> dict[str, Any]:
    state = ((data.get("intelligence") or {}).get("market_state") or {}).get("state") or ""; replay = mode.upper() in {"BACKTEST", "REPLAY"}
    gates = {"direction": signal.get("direction") in {"BULLISH", "BEARISH"}, "confidence": _f(signal.get("confidence")) >= 60, "liquidity": _f(data.get("liquidity_score")) >= 50, "market_state": state not in {"LIQUIDITY_RISK", "COMPRESSION"}, "data_integrity": data.get("data_integrity") == "LIVE_PROVIDER" or (replay and data.get("data_integrity") == "RECORDED_HISTORICAL")}
    if strategy == "gamma_blast": gates["gamma_regime"] = signal.get("gamma", {}).get("regime") == "NEGATIVE"; gates["volatility"] = signal.get("volatility", {}).get("regime") == "VOL_EXPANSION"
    reasons = [k for k, ok in gates.items() if not ok]
    return {"strategy": strategy, "mode": mode.upper(), "gates": gates, "approved": not reasons, "reasons": reasons, "max_risk_pct": 0.5 if strategy == "gamma_blast" else 1.0}


def execution_plan(data: dict[str, Any], signal: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
    approved = bool(risk.get("approved")); direction = signal.get("direction", "NEUTRAL"); selections = data.get("strike_selection") or []
    if isinstance(selections, dict): selections = selections.get("candidates") or selections.get("strikes") or []
    chosen = selections[0] if selections else None; spot = _f(data.get("spot")); em = _f((data.get("expected_move") or {}).get("move")); stop = max(em * .35, spot * .002) if em else spot * .002
    return {"status": "APPROVED_READ_ONLY" if approved else "BLOCKED", "execution_enabled": False, "direction": direction, "instrument": chosen, "entry": "WAIT_FOR_TRIGGER" if approved else None, "stop_points": round(stop,2) if approved else None, "target_points": round(stop*2,2) if approved else None, "risk_reward": 2.0 if approved else None, "order_action": "DISABLED", "note": "Plan only. No broker order can be submitted by this engine."}


def final_decision(data: dict[str, Any], previous: dict[str, Any] | None = None, strategy: str = "directional", mode: str = "LIVE") -> dict[str, Any]:
    signal = institutional_signal(data, previous); risk = risk_engine(data, signal, strategy, mode); plan = execution_plan(data, signal, risk)
    return {"signal": signal, "risk": risk, "execution_plan": plan, "status": "TRADE_CANDIDATE" if risk["approved"] else "NO_TRADE", "authoritative": "FINAL_DECISION", "trading": "DISABLED", "mode": mode.upper()}


def replay_signal_stack(snapshots: list[dict[str, Any]], mode: str = "REPLAY") -> dict[str, Any]:
    results = []; previous = None
    for snap in snapshots:
        result = final_decision(snap, previous, "directional", mode); results.append({"timestamp": snap.get("timestamp"), "spot": snap.get("spot"), "decision": result}); previous = snap
    candidates = sum(r["decision"]["status"] == "TRADE_CANDIDATE" for r in results)
    return {"count": len(results), "trade_candidates": candidates, "no_trade": len(results)-candidates, "results": results, "signal_neutral": False, "orders_placed": 0}
