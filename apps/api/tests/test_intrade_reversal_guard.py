from quantnifty.intrade_reversal_guard import evaluate_intrade_reversal


def _decision(direction="BULLISH", confidence=80, aligned=2):
    return {
        "signal": {
            "direction": direction,
            "confidence": confidence,
            "context_alignment": {
                "aligned": aligned,
                "conflicting": 0,
                "transition_context": True,
            },
            "gamma": {"regime": "NEGATIVE"},
        },
        "market": {"state": "TREND_UP"},
    }


def test_two_confirmed_opposite_snapshots_exit_active_trade():
    previous = {"spot": 23300, "gamma_flip": 23200, "option_chain": [{"volume": 100}]}
    current = {"spot": 23320, "gamma_flip": 23200, "option_chain": [{"volume": 130}]}
    result = evaluate_intrade_reversal(
        "BEARISH", current, _decision("BULLISH"), previous, opposite_confirmations=2
    )
    assert result["action"] == "EXIT_REVERSAL"
    assert result["normal_reversal"] is True


def test_single_opposite_tick_only_warns():
    previous = {"spot": 23300, "gamma_flip": 23200, "option_chain": [{"volume": 100}]}
    current = {"spot": 23305, "gamma_flip": 23200, "option_chain": [{"volume": 102}]}
    result = evaluate_intrade_reversal(
        "BEARISH", current, _decision("BULLISH"), previous, opposite_confirmations=1
    )
    assert result["action"] == "WARN_REVERSAL"


def test_opposite_signal_plus_adverse_price_shock_exits_immediately():
    previous = {"spot": 23300, "gamma_flip": 23200, "option_chain": [{"volume": 100}]}
    current = {"spot": 23350, "gamma_flip": 23200, "option_chain": [{"volume": 300}]}
    result = evaluate_intrade_reversal(
        "BEARISH", current, _decision("BULLISH"), previous, opposite_confirmations=1
    )
    assert result["action"] == "EXIT_REVERSAL"
    assert result["price_shock"] is True
