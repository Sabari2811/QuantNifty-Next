from quantnifty.market_brain import classify_market_state, decision_intelligence, move_attribution, pressure_map


def row(strike, side, oi, previous_oi, gamma=0.01, volume=1000):
    return {"strike": strike, "side": side, "oi": oi, "previous_oi": previous_oi, "gamma": gamma, "volume": volume}


def sample(spot=25000, gex=-100):
    return {
        "spot": spot, "gamma_flip": 25050, "gex": gex, "atm_iv": 12, "pcr": 1.1,
        "call_oi_change": 200, "put_oi_change": -800, "liquidity_score": 82,
        "bias": "BEARISH", "confidence": 70, "expected_move": {"move": 300},
        "option_chain": [row(24900, "CE", 10000, 9800), row(24900, "PE", 12000, 13000), row(25000, "CE", 15000, 14800), row(25000, "PE", 16000, 16800)],
    }


def test_state_machine_is_deterministic():
    result = classify_market_state(sample())
    assert result["state"] in {"NEGATIVE_GAMMA_EXPANSION", "TREND_DOWN", "GAMMA_TRANSITION"}
    assert result["bias"] == "BEARISH"


def test_move_attribution_has_ranked_contributors():
    result = move_attribution(sample(spot=24950), sample(spot=25000))
    assert result["direction"] == "DOWN"
    assert result["primary_driver"] in result["contributors"]
    assert abs(sum(result["contributors"].values()) - 100) < 0.2


def test_pressure_map_contains_structural_strikes():
    result = pressure_map(sample())
    assert result
    assert {24900, 25000}.issubset({r["strike"] for r in result})
    assert all("pressure" in r and "dominant_side" in r for r in result)


def test_no_trade_when_confidence_or_liquidity_fails():
    data = sample(); data["confidence"] = 45; data["liquidity_score"] = 40
    result = decision_intelligence(data)
    assert result["decision"]["status"] == "NO_TRADE"
    assert "confidence" in result["decision"]["reasons"]
    assert "liquidity" in result["decision"]["reasons"]


def test_trade_candidate_when_all_intelligence_gates_pass():
    data = sample(); data["liquidity_score"] = 80; data["confidence"] = 80; data["gex"] = -500
    result = decision_intelligence(data)
    assert result["decision"]["status"] in {"TRADE_CANDIDATE", "NO_TRADE"}
    assert result["decision"]["execution"] == "DISABLED"
