from quantnifty.intrade_reversal_guard import evaluate_intrade_reversal


def _decision(direction="BULLISH", confidence=72, aligned=2):
    return {
        "signal": {
            "direction": direction,
            "confidence": confidence,
            "context_alignment": {"aligned": aligned},
        }
    }


def test_two_confirmed_opposite_readings_exit():
    previous = {"spot": 23300.0}
    current = {"spot": 23305.0}
    result = evaluate_intrade_reversal("BULLISH", current, _decision("BEARISH"), previous, 2)
    assert result["action"] == "EXIT_REVERSAL"
    assert result["current_direction"] == "BEARISH"


def test_single_opposite_reading_warns():
    result = evaluate_intrade_reversal("BULLISH", {"spot": 23300.0}, _decision("BEARISH"), {"spot": 23298.0}, 1)
    assert result["action"] == "WARN_REVERSAL"


def test_adverse_shock_escalates_confirmed_reversal():
    result = evaluate_intrade_reversal(
        "BULLISH",
        {"spot": 23240.0, "intelligence": {}},
        _decision("BEARISH"),
        {"spot": 23300.0},
        1,
    )
    assert result["action"] == "EXIT_REVERSAL"
    assert result["price_shock"] is True
