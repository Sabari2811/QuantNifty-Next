from quantnifty.institutional_engine import final_decision


def _snapshot(direction_probability="BEARISH"):
    probability = {"bullish_probability": 15, "bearish_probability": 90, "confidence": 80}
    return {
        "timestamp": "2026-09-18T05:35:00+00:00",
        "spot": 23300,
        "bias": "BULLISH",
        "liquidity_score": 85,
        "data_integrity": "LIVE_PROVIDER",
        "expected_move": {"move": 120},
        "atm_iv": 18,
        "gex": 10,
        "dex": 25,
        "gamma_flip": 23250,
        "recorded_oi_flow_bias": "BULLISH",
        "probability": probability,
        "option_chain": [
            {"strike": 23300, "side": "CE", "oi": 1200, "previous_oi": 1100, "last_price": 100, "previous_close": 98, "volume": 1000},
            {"strike": 23300, "side": "PE", "oi": 1400, "previous_oi": 1300, "last_price": 100, "previous_close": 102, "volume": 1000},
        ],
        "strike_selection": {
            "candidates": [
                {"strike": 23300, "side": "CE", "security_id": "CE1"},
                {"strike": 23300, "side": "PE", "security_id": "PE1"},
            ]
        },
        "intelligence": {"market_state": {"state": "GAMMA_TRANSITION"}},
    }


def test_gamma_transition_blocks_directional_context_conflict():
    result = final_decision(_snapshot(), None, "directional", "LIVE")
    alignment = result["signal"]["context_alignment"]
    assert result["signal"]["direction"] == "BEARISH"
    assert alignment["transition_context"] is True
    assert alignment["conflicting"] >= 3
    assert result["risk"]["approved"] is False
    assert "context_alignment" in result["risk"]["reasons"]


def test_gamma_transition_allows_aligned_directional_context():
    data = _snapshot()
    data["probability"] = {"bullish_probability": 90, "bearish_probability": 15, "confidence": 80}
    data["recorded_oi_flow_bias"] = "BULLISH"
    result = final_decision(data, None, "directional", "LIVE")
    alignment = result["signal"]["context_alignment"]
    assert result["signal"]["direction"] == "BULLISH"
    assert alignment["aligned"] >= 2
    assert alignment["conflicting"] < 2
    assert result["risk"]["approved"] is True
