from __future__ import annotations

from typing import Any

from quantnifty.learning_store import load_events, trading_day


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
        if not isinstance(row, dict): continue
        doi = _f(row.get("oi")) - _f(row.get("previous_oi")); price_change = _f(row.get("last_price")) - _f(row.get("previous_close")); weight = abs(doi) * max(_f(row.get("last_price")), 1.0)
        if doi > 0 and price_change > 0: bull += weight
        elif doi < 0 and price_change > 0: bull += weight * 0.75
        elif doi > 0 and price_change < 0: bear += weight
        elif doi < 0 and price_change < 0: bear += weight * 0.75
    return bull, bear


def pre_move_state(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = previous or {}; spot = _spot(snapshot); prev_spot = _spot(previous); em = _f((snapshot.get("expected_move") or {}).get("move")); prev_em = _f((previous.get("expected_move") or {}).get("move")); vol = _volume(snapshot); prev_vol = _volume(previous); iv = _f(snapshot.get("atm_iv")); prev_iv = _f(previous.get("atm_iv")); gex = _f(snapshot.get("gex")); prev_gex = _f(previous.get("gex")); move_pct = abs(_pct(spot, prev_spot)) if prev_spot else 0.0; volume_change = _pct(vol, prev_vol) if prev_vol else 0.0; em_change = _pct(em, prev_em) if prev_em else 0.0; iv_change = _pct(iv, prev_iv) if prev_iv else 0.0; bull_oi, bear_oi = _oi_pressure(snapshot); pressure_total = bull_oi + bear_oi; pressure_bias = "BULLISH" if bull_oi > bear_oi * 1.20 else "BEARISH" if bear_oi > bull_oi * 1.20 else "NEUTRAL"; compression = (em_change <= -3.0 if prev_em else False) or (iv_change <= -3.0 if prev_iv else False); pressure = pressure_total > 0 and abs(bull_oi - bear_oi) / pressure_total >= 0.15; trigger = volume_change >= 20.0 and move_pct >= 0.05; gamma_shift = prev_gex != 0 and ((gex > 0) != (prev_gex > 0)); stage = "TRIGGER" if trigger else "PRESSURE" if pressure else "COMPRESSION" if compression else "BASE"; readiness = 30.0 if compression else 0.0; readiness += 35.0 if pressure else 0.0; readiness += 35.0 if trigger else 0.0; readiness += 10.0 if gamma_shift else 0.0
    return {"stage": stage, "readiness_pct": round(min(100.0, readiness), 1), "pressure_bias": pressure_bias, "compression": compression, "pressure": pressure, "trigger": trigger, "gamma_shift": gamma_shift, "volume_change_pct": round(volume_change, 2), "expected_move_change_pct": round(em_change, 2), "iv_change_pct": round(iv_change, 2), "spot_move_pct": round(move_pct, 4), "bull_pressure": round(bull_oi, 2), "bear_pressure": round(bear_oi, 2)}


def _near_atm_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    spot = _spot(snapshot)
    if spot <= 0: return []
    return [r for r in snapshot.get("option_chain") or [] if isinstance(r, dict) and _f(r.get("strike")) > 0 and abs(_f(r.get("strike")) - spot) / spot <= .02 and str(r.get("side") or r.get("option_type") or "").upper() in {"CE", "PE"}]


def accumulation_detector(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = previous or {}; spot = _spot(snapshot); prev_spot = _spot(previous); em = _f((snapshot.get("expected_move") or {}).get("move")); iv = _f(snapshot.get("atm_iv")); piv = _f(previous.get("atm_iv")); best = None; candidates = []
    for row in _near_atm_rows(snapshot):
        side = str(row.get("side") or row.get("option_type") or "").upper(); price = _f(row.get("last_price")); prev_price = _f(row.get("previous_close")); oi = _f(row.get("oi")); prev_oi = _f(row.get("previous_oi")); volume = _f(row.get("volume")); doi_pct = _pct(oi, prev_oi) if prev_oi else 0.0; dpct = _pct(price, prev_price) if prev_price else 0.0; premium_ratio = price / em if em > 0 else 999.0; score = (25 if doi_pct >= 2.0 else 0) + (20 if dpct >= -1.5 else 0) + (15 if volume > 0 else 0) + (20 if 0.0 < premium_ratio <= .20 else 0) + (10 if (abs(_pct(spot, prev_spot)) <= .35 if prev_spot else True) else 0) + (10 if (True if not piv else _pct(iv, piv) <= 5.0) else 0); candidate = {"side": side, "strike": _f(row.get("strike")), "premium": price, "premium_to_expected_move": round(premium_ratio, 4), "oi_change_pct": round(doi_pct, 2), "premium_change_pct": round(dpct, 2), "volume": volume, "score": round(score, 1)}; candidates.append(candidate); best = candidate if best is None or score > best["score"] else best
    if best and best["score"] >= 70: direction, state = ("BULLISH" if best["side"] == "CE" else "BEARISH"), "EARLY_ACCUMULATION"
    elif best and best["score"] >= 50: direction, state = ("BULLISH" if best["side"] == "CE" else "BEARISH"), "WATCH_ACCUMULATION"
    else: direction, state = "NEUTRAL", "NO_CLEAR_ACCUMULATION"
    return {"state": state, "direction": direction, "score": round(best["score"], 1) if best else 0.0, "candidate": best, "candidates": candidates, "spot_change_pct": round(_pct(spot, prev_spot), 4) if prev_spot else 0.0, "iv_change_pct": round(_pct(iv, piv), 2) if piv else 0.0, "method": "near_atm_OI+premium+volume+IV+expected_move"}


def adaptive_exit_state(snapshot: dict[str, Any], previous: dict[str, Any] | None, direction: str, entry_spot: float) -> dict[str, Any]:
    previous = previous or {}; spot = _spot(snapshot); entry = _f(entry_spot)
    if spot <= 0 or entry <= 0 or direction not in {"BULLISH", "BEARISH"}: return {"action": "HOLD", "reason": "insufficient_exit_context", "move_pct": 0.0, "trailing_stop_pct": 0.0}
    move = (spot - entry) / entry * 100.0 if direction == "BULLISH" else (entry - spot) / entry * 100.0; pre = pre_move_state(snapshot, previous); vol = _volume(snapshot); pvol = _volume(previous); volume_change = _pct(vol, pvol) if pvol else 0.0; gamma = _f(snapshot.get("gex")); pgamma = _f(previous.get("gex")); gamma_reversal = pgamma != 0 and ((gamma > 0) != (pgamma > 0)); pressure = pre["pressure_bias"]; aligned = pressure == direction; exhaustion = move >= .8 and volume_change <= -20 and not aligned; hard_exit = move <= -.5; take_profit = move >= 1.8 and (exhaustion or gamma_reversal); trailing = max(.35, min(1.0, move * .45)) if move > 0 else .35
    if hard_exit: action, reason = "EXIT", "protect_capital"
    elif take_profit: action, reason = "EXIT", "profit_exhaustion_or_gamma_reversal"
    elif move >= .8 and (exhaustion or gamma_reversal): action, reason = "TRAIL", "lock_profit_before_exhaustion"
    else: action, reason = "HOLD", "trend_or_accumulation_still_supported"
    return {"action": action, "reason": reason, "move_pct": round(move, 3), "volume_change_pct": round(volume_change, 2), "gamma_reversal": gamma_reversal, "pressure_bias": pressure, "trailing_stop_pct": round(trailing, 3)}


def market_regime(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = previous or {}; bias = str(snapshot.get("bias") or "NEUTRAL").upper(); liquidity = _f(snapshot.get("liquidity_score")); gex = _f(snapshot.get("gex")); flip = snapshot.get("gamma_flip"); spot = _spot(snapshot); prev_spot = _spot(previous); em = _f((snapshot.get("expected_move") or {}).get("move")); pre = pre_move_state(snapshot, previous); accumulation = accumulation_detector(snapshot, previous); signed_spot_move = _pct(spot, prev_spot) if prev_spot else 0.0
    if liquidity < 35: regime = "LIQUIDITY_RISK"
    elif accumulation["state"] == "EARLY_ACCUMULATION": regime = "EARLY_ACCUMULATION"
    elif pre["trigger"] and pre["pressure_bias"] == "BULLISH" and bias != "BEARISH" and signed_spot_move >= 0: regime = "BREAKOUT_UP"
    elif pre["trigger"] and (pre["pressure_bias"] == "BEARISH" or bias == "BEARISH") and signed_spot_move <= 0: regime = "BREAKDOWN_DOWN"
    elif flip is not None and abs(spot - _f(flip)) <= max(25.0, em * .10): regime = "GAMMA_TRANSITION"
    elif gex < 0 and (not previous or abs(gex) >= abs(_f(previous.get("gex")))): regime = "NEGATIVE_GAMMA_EXPANSION"
    elif gex > 0 and bias == "NEUTRAL": regime = "POSITIVE_GAMMA_RANGE"
    elif bias == "BULLISH": regime = "TREND_UP"
    elif bias == "BEARISH": regime = "TREND_DOWN"
    elif pre["compression"]: regime = "COMPRESSION"
    else: regime = "TRANSITION"
    return {"regime": regime, "bias": bias, "pre_move": pre, "accumulation": accumulation, "liquidity": round(liquidity, 1)}


def _base_strategy_selection(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    regime = market_regime(snapshot, previous); r = regime["regime"]
    if r == "EARLY_ACCUMULATION": selected, direction = "early_accumulation", regime["accumulation"]["direction"]
    elif r in {"BREAKOUT_UP", "TREND_UP"}: selected, direction = "directional", "BULLISH"
    elif r in {"BREAKDOWN_DOWN", "TREND_DOWN"}: selected, direction = "directional", "BEARISH"
    elif r == "NEGATIVE_GAMMA_EXPANSION": selected, direction = "gamma_blast", regime["pre_move"]["pressure_bias"]
    elif r == "GAMMA_TRANSITION": selected, direction = "transition", regime["pre_move"]["pressure_bias"]
    elif r == "POSITIVE_GAMMA_RANGE": selected, direction = "range", "NEUTRAL"
    elif r == "COMPRESSION": selected, direction = "breakout_watch", regime["pre_move"]["pressure_bias"]
    else: selected, direction = "standby", "NEUTRAL"
    return {"regime": r, "selected_strategy": selected, "preferred_direction": direction, "confidence": regime["pre_move"]["readiness_pct"] if r != "EARLY_ACCUMULATION" else regime["accumulation"]["score"], "reason": f"regime={r}; stage={regime['pre_move']['stage']}"}


def adaptive_day_policy(snapshot: dict[str, Any], previous: dict[str, Any] | None = None, memory: dict[str, Any] | None = None) -> dict[str, Any]:
    base = _base_strategy_selection(snapshot, previous); memory = memory or {}; regime = base["regime"]; strategies = ["directional", "gamma_blast", "transition", "early_accumulation"]; by_regime = memory.get("by_regime") or {}; stats = by_regime.get(regime) or {}; global_stats = memory.get("global") or {}; candidates = []
    for strategy in strategies:
        s = stats.get(strategy) or {}; n = int(s.get("trades", 0)); wins = int(s.get("wins", 0)); pnl = _f(s.get("net_pnl")); g = global_stats.get(strategy) or {}; gn = int(g.get("trades", 0)); gp = _f(g.get("net_pnl")); win_rate = (wins + 1.0) / (n + 2.0); avg_pnl = pnl / n if n else 0.0; global_avg = gp / gn if gn else 0.0; evidence = min(1.0, n / 5.0); score = .55 * win_rate + .45 * (.5 + max(-.5, min(.5, (avg_pnl + global_avg) / 400.0))); score = score * (.35 + .65 * evidence) + .5 * (.65 - .65 * evidence); candidates.append((score, strategy, n, win_rate, avg_pnl))
    anchor = base["selected_strategy"] if base["selected_strategy"] in strategies else "directional"; ranked = sorted(candidates, reverse=True); chosen = anchor; reason = "regime anchor; insufficient prior evidence to override"; anchor_row = next(c for c in candidates if c[1] == anchor)
    for row in ranked:
        if row[1] == anchor: continue
        if row[2] >= 3 and row[0] >= anchor_row[0] + .08: chosen = row[1]; reason = f"learned override: {row[1]} outscored {anchor} for {regime}"; break
    if regime in {"LIQUIDITY_RISK", "POSITIVE_GAMMA_RANGE"}: chosen = "standby"; reason = f"risk-preserving regime policy: {regime}"
    if regime == "COMPRESSION": chosen = "breakout_watch"; reason = "compression: wait for release rather than chase"
    direction = base["preferred_direction"]
    if chosen in {"gamma_blast", "transition"} and direction not in {"BULLISH", "BEARISH"}: direction = str((memory.get("last_direction") or "NEUTRAL")).upper()
    recent = memory.get("recent_days") or []; loss_days = sum(_f(d.get("net_pnl")) < 0 for d in recent[-2:]); risk_profile = "DEFENSIVE" if loss_days >= 2 or _f((recent[-1] if recent else {}).get("net_pnl")) <= -1000 else "NORMAL"; readiness = _f(base.get("confidence")) - (10 if risk_profile == "DEFENSIVE" else 0); same_day_trades = int(memory.get("same_day_trades") or 0)
    return {**base, "selected_strategy": chosen, "preferred_direction": direction, "confidence": round(max(0.0, readiness), 1), "risk_profile": risk_profile, "reason": reason, "learning": {"regime": regime, "candidate_scores": {s: round(sc, 4) for sc, s, *_ in candidates}, "regime_samples": {s: int((stats.get(s) or {}).get("trades", 0)) for s in strategies}, "global_samples": {s: int((global_stats.get(s) or {}).get("trades", 0)) for s in strategies}, "same_day_trades": same_day_trades}}


def update_adaptive_memory(memory: dict[str, Any], trade: dict[str, Any], day: str, regime: str, selected_strategy: str) -> dict[str, Any]:
    state = {"by_regime": dict(memory.get("by_regime") or {}), "global": dict(memory.get("global") or {}), "recent_days": list(memory.get("recent_days") or []), "last_direction": memory.get("last_direction"), "same_day_trades": int(memory.get("same_day_trades") or 0)}; pnl = _f(trade.get("net_pnl")); won = pnl > 0
    for bucket in (state["global"], state["by_regime"].setdefault(regime, {})):
        s = bucket.setdefault(selected_strategy, {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0}); s["trades"] = int(s.get("trades", 0)) + 1; s["wins"] = int(s.get("wins", 0)) + int(won); s["losses"] = int(s.get("losses", 0)) + int(not won); s["net_pnl"] = round(_f(s.get("net_pnl")) + pnl, 4)
    state["same_day_trades"] += 1; state["last_direction"] = str(trade.get("direction") or state.get("last_direction") or "NEUTRAL").upper(); days = {str(d.get("day")): dict(d) for d in state["recent_days"] if isinstance(d, dict) and d.get("day")}; entry = days.setdefault(day, {"day": day, "net_pnl": 0.0, "trades": 0}); entry["net_pnl"] = round(_f(entry.get("net_pnl")) + pnl, 4); entry["trades"] = int(entry.get("trades", 0)) + 1; state["recent_days"] = list(days.values())[-20:]
    return state


def _same_day_memory(snapshot: dict[str, Any]) -> dict[str, Any]:
    day = trading_day(snapshot.get("timestamp"))
    if not day:
        return {}
    memory: dict[str, Any] = {"same_day_trades": 0}
    for event in load_events("outcomes", day):
        outcome = event.get("outcome") if isinstance(event, dict) else None
        if not isinstance(outcome, dict) or str(outcome.get("status") or outcome.get("lifecycle") or "").upper() != "CLOSED":
            continue
        reasons = outcome.get("entry_reasons") if isinstance(outcome.get("entry_reasons"), dict) else {}
        regime = str(reasons.get("adaptive_regime") or outcome.get("regime") or "UNKNOWN").upper()
        strategy = str(outcome.get("strategy") or reasons.get("adaptive_selected_strategy") or "").strip().lower()
        if not strategy or strategy == "standby":
            continue
        trade = {"net_pnl": outcome.get("realized_pnl", outcome.get("net_pnl", 0.0)), "direction": outcome.get("direction")}
        memory = update_adaptive_memory(memory, trade, day, regime, strategy)
    return memory


def strategy_selector(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    runtime_memory = _same_day_memory(snapshot) if snapshot.get("_learning_runtime") is True else {}
    if runtime_memory.get("same_day_trades"):
        snapshot = dict(snapshot)
        snapshot["_adaptive_memory"] = runtime_memory
    memory = snapshot.get("_adaptive_memory"); selected = adaptive_day_policy(snapshot, previous, memory) if isinstance(memory, dict) else _base_strategy_selection(snapshot, previous)
    research_strategy = str(snapshot.get("_research_strategy") or "").strip().lower()
    if research_strategy in {"directional", "gamma_blast", "early_accumulation", "transition", "range", "breakout_watch", "standby"}:
        base = _base_strategy_selection(snapshot, previous); selected = {**base, "selected_strategy": research_strategy, "reason": f"explicit research strategy={research_strategy}", "learning": {"research_override": True}}
        if research_strategy in {"directional", "gamma_blast", "transition", "early_accumulation"} and selected["preferred_direction"] == "NEUTRAL": selected["preferred_direction"] = str((snapshot.get("recorded_bias") or snapshot.get("bias") or "NEUTRAL")).upper()
        if research_strategy == "standby": selected["preferred_direction"] = "NEUTRAL"
    policy = snapshot.get("_adaptive_policy")
    same_day_trades = int((runtime_memory or {}).get("same_day_trades") or 0)
    if isinstance(policy, dict) and same_day_trades == 0:
        p = policy.get("policy") or {}
        strategy = str(p.get("strategy") or "").lower()
        if p.get("created_day") and str(p.get("created_day")) < str(snapshot.get("policy_target_day") or "9999-99-99") and p.get("status") in {"VALIDATED", "FALLBACK"} and strategy in {"directional", "gamma_blast", "early_accumulation", "transition", "range", "breakout_watch", "standby", "adaptive"}:
            selected = {**selected, "selected_strategy": strategy if strategy != "adaptive" else selected.get("selected_strategy", "standby"), "reason": f"validated future-safe policy v{p.get('version')}; same-day learning not yet available", "policy_version": p.get("version")}
    return selected


def _spot_outcome(snapshots: list[dict[str, Any]], entry_index: int, direction: str, stop_pct: float, target_pct: float, max_hold_bars: int) -> dict[str, Any]:
    entry = _spot(snapshots[entry_index])
    if entry <= 0: return {"status": "INVALID", "direction": direction}
    end = min(len(snapshots) - 1, entry_index + max(1, max_hold_bars))
    for j in range(entry_index + 1, end + 1):
        spot = _spot(snapshots[j]); move = (spot - entry) / entry if direction == "BULLISH" else (entry - spot) / entry
        if move <= -abs(stop_pct): return {"status": "LOSS", "direction": direction, "exit_index": j, "reason": "STOP", "mfe_pct": round(max(0.0, move) * 100, 4), "mae_pct": round(move * 100, 4)}
        if move >= abs(target_pct): return {"status": "WIN", "direction": direction, "exit_index": j, "reason": "TARGET", "mfe_pct": round(move * 100, 4), "mae_pct": round(min(0.0, move) * 100, 4)}
    final = _spot(snapshots[end]); move = (final - entry) / entry if direction == "BULLISH" else (entry - final) / entry
    return {"status": "WIN" if move > 0 else "LOSS" if move < 0 else "FLAT", "direction": direction, "exit_index": end, "reason": "TIME", "mfe_pct": round(max(0.0, move) * 100, 4), "mae_pct": round(min(0.0, move) * 100, 4)}


def counterfactual_gate_analysis(snapshots: list[dict[str, Any]], observation_rows: list[dict[str, Any]], stop_pct: float = 0.0125, target_pct: float = 0.025, max_hold_bars: int = 12) -> dict[str, Any]:
    blocked = [r for r in observation_rows if not r.get("risk", {}).get("approved")]; by_reason: dict[str, list[dict[str, Any]]] = {}; results: list[dict[str, Any]] = []
    for row in blocked:
        i = int(row["index"]); direction = str(row.get("replay", {}).get("direction") or "NEUTRAL"); directions = [direction] if direction in {"BULLISH", "BEARISH"} else ["BULLISH", "BEARISH"]; outcomes = {d: _spot_outcome(snapshots, i + 1, d, stop_pct, target_pct, max_hold_bars) for d in directions if i + 1 < len(snapshots)}; item = {"index": i, "timestamp": row.get("timestamp"), "blocked_reasons": row.get("risk", {}).get("blocked_reasons", []), "replay_direction": direction, "outcomes": outcomes, "regime": market_regime(snapshots[i], snapshots[i - 1] if i else None), "pre_move": pre_move_state(snapshots[i], snapshots[i - 1] if i else None), "accumulation": accumulation_detector(snapshots[i], snapshots[i - 1] if i else None)}; results.append(item)
        for reason in item["blocked_reasons"]: by_reason.setdefault(str(reason), []).append(item)
    def summarize(items: list[dict[str, Any]], direction: str | None = None) -> dict[str, Any]:
        outcomes = [o for item in items for d, o in item.get("outcomes", {}).items() if direction is None or d == direction]; wins = sum(o.get("status") == "WIN" for o in outcomes); losses = sum(o.get("status") == "LOSS" for o in outcomes); flat = sum(o.get("status") == "FLAT" for o in outcomes); total = wins + losses + flat
        return {"evaluated": total, "wins": wins, "losses": losses, "flat": flat, "win_rate_pct": round(wins / total * 100, 2) if total else 0.0}
    return {"method": "SPOT_DIRECTIONAL_COUNTERFACTUAL", "research_only": True, "blocked_observations": len(blocked), "all_blocked_summary": summarize(results), "bullish_summary": summarize(results, "BULLISH"), "bearish_summary": summarize(results, "BEARISH"), "by_block_reason": {k: summarize(v) for k, v in sorted(by_reason.items())}, "observations": results, "warning": "Counterfactual outcomes are not executed trades and use future spot movement only; they must not be mixed into empirical option P&L."}
