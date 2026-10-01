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
        "support": 23300, "resistance": 23350,
        "recorded_oi_flow_bias": "BULLISH",
        "probability": probability,
        "option_chain": [
            {"strike": 23300, "side": "CE", "oi": 1300, "previous_oi": 1200, "last_price": 100, "previous_close": 98, "volume": 2000},
            {"strike": 23300, "side": "PE", "oi": 1500, "previous_oi": 1400, "last_price": 102, "previous_close": 104, "volume": 2000},
        ],
        "strike_selection": {
            "candidates": [
                {"strike": 23300, "side": "CE", "security_id": "CE1"},
                {"strike": 23300, "side": "PE", "security_id": "PE1"},
            ]
        },
        "intelligence": {"market_state": {"state": "GAMMA_TRANSITION"}},
    }


def _previous(data):
    previous = dict(data)
    previous["timestamp"] = "2026-09-18T05:34:00+00:00"
    previous["spot"] = 23290
    previous["resistance"] = 23295
    previous["support"] = 23250
    previous["option_chain"] = [dict(row, last_price=(row.get("last_price") or 100) - (2 if row.get("side") == "CE" else 0), volume=1000, oi=(row.get("oi") or 0) - 100, previous_oi=(row.get("previous_oi") or 0) - 100) for row in data["option_chain"]]
    return previous


def test_gamma_transition_blocks_directional_context_conflict():
    result = final_decision(_snapshot(), _previous(_snapshot()), "directional", "LIVE")
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
    result = final_decision(data, _previous(data), "directional", "LIVE")
    alignment = result["signal"]["context_alignment"]
    assert result["signal"]["direction"] == "BULLISH"
    assert alignment["aligned"] >= 2
    assert alignment["conflicting"] < 2
    assert result["risk"]["approved"] is True

def test_adaptive_brain_converts_context_conflict_to_transition():
    result = final_decision(_snapshot(), _previous(_snapshot()), "adaptive", "LIVE")
    assert result["signal"]["direction"] == "NEUTRAL"
    assert result["signal"]["adaptive"]["selected_strategy"] == "transition"
    assert result["risk"]["approved"] is False
    assert "direction" in result["risk"]["reasons"]

