from quantnifty.research_brain import counterfactual_gate_analysis, market_regime, pre_move_state, strategy_selector


def snap(spot, volume=100, em=100, iv=15, gex=1, bias="NEUTRAL"):
    return {"spot": spot, "bias": bias, "liquidity_score": 80, "expected_move": {"move": em}, "atm_iv": iv, "gex": gex, "option_chain": [{"volume": volume, "oi": 1000, "previous_oi": 900, "last_price": 100, "previous_close": 95, "side": "CE"}]}


def test_pre_move_detects_pressure_and_trigger():
    previous = snap(24500, volume=100, em=120, iv=16, gex=1)
    current = snap(24550, volume=140, em=115, iv=15, gex=-1)
    state = pre_move_state(current, previous)
    assert state["pressure"] is True
    assert state["trigger"] is True
    assert state["gamma_shift"] is True
    assert state["readiness_pct"] == 100.0


def test_market_regime_and_selector_can_produce_bearish_path():
    previous = snap(24500, volume=100, em=100, iv=15, gex=-10, bias="BEARISH")
    current = snap(24200, volume=130, em=110, iv=16, gex=-12, bias="BEARISH")
    regime = market_regime(current, previous)
    selection = strategy_selector(current, previous)
    assert regime["regime"] in {"BREAKDOWN_DOWN", "NEGATIVE_GAMMA_EXPANSION", "TREND_DOWN"}
    assert selection["preferred_direction"] == "BEARISH" or selection["selected_strategy"] == "gamma_blast"


def test_counterfactual_evaluates_both_sides_for_neutral_block():
    snapshots = []
    for i, spot in enumerate([100.0, 100.0, 103.0, 103.0, 103.0]):
        s = snap(spot)
        s["timestamp"] = f"2026-08-03T09:{15 + i:02d}:00+05:30"
        snapshots.append(s)
    rows = [{"index": 0, "timestamp": snapshots[0]["timestamp"], "replay": {"direction": "NEUTRAL"}, "risk": {"approved": False, "blocked_reasons": ["direction"]}}]
    result = counterfactual_gate_analysis(snapshots, rows, stop_pct=0.01, target_pct=0.02, max_hold_bars=3)
    assert result["research_only"] is True
    assert result["blocked_observations"] == 1
    assert result["bullish_summary"]["evaluated"] == 1
    assert result["bearish_summary"]["evaluated"] == 1
    assert result["bullish_summary"]["win_rate_pct"] == 100.0
