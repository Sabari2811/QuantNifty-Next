from quantnifty.research_brain import accumulation_detector, adaptive_exit_state, strategy_selector


def snap(spot=24500, iv=15, gex=10, side="CE", oi=1000, prev_oi=950, price=18, prev_price=18, volume=500):
    return {
        "spot": spot,
        "bias": "NEUTRAL",
        "liquidity_score": 80,
        "expected_move": {"move": 100},
        "atm_iv": iv,
        "gex": gex,
        "option_chain": [{"strike": 24500, "side": side, "oi": oi, "previous_oi": prev_oi, "last_price": price, "previous_close": prev_price, "volume": volume}],
    }


def test_detects_early_call_accumulation_before_spot_breakout():
    previous = snap(spot=24495, oi=950, prev_oi=900, price=17, prev_price=17, volume=250)
    current = snap(spot=24505, oi=1020, prev_oi=950, price=17.2, prev_price=17, volume=700)
    result = accumulation_detector(current, previous)
    assert result["state"] == "EARLY_ACCUMULATION"
    assert result["direction"] == "BULLISH"
    assert result["score"] >= 70


def test_selector_switches_to_early_accumulation_regime():
    previous = snap(spot=24495, oi=950, prev_oi=900, price=17, prev_price=17, volume=250)
    current = snap(spot=24505, oi=1020, prev_oi=950, price=17.2, prev_price=17, volume=700)
    selection = strategy_selector(current, previous)
    assert selection["regime"] == "EARLY_ACCUMULATION"
    assert selection["selected_strategy"] == "early_accumulation"
    assert selection["preferred_direction"] == "BULLISH"


def test_adaptive_exit_trails_after_exhaustion():
    previous = snap(spot=24700, oi=1020, prev_oi=1010, price=25, prev_price=24, volume=1000)
    current = snap(spot=24720, oi=1010, prev_oi=1020, price=24.5, prev_price=25, volume=700)
    result = adaptive_exit_state(current, previous, "BULLISH", 24500)
    assert result["action"] in {"TRAIL", "EXIT"}
    assert result["trailing_stop_pct"] > 0
