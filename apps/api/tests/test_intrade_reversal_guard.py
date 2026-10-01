from quantnifty.intrade_reversal_guard import evaluate_intrade_reversal


def _decision(direction="BULLISH", confidence=80, aligned=2, gamma_flip=None):
    return {
        "signal": {
            "direction": direction,
            "confidence": confidence,
            "context_alignment": {
                "aligned": aligned,
                "conflicting": 0,
                "transition_context": True,
            },
            "gamma": {"regime": "NEGATIVE", **({"gamma_flip": gamma_flip} if gamma_flip is not None else {})},
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
        "BEARISH", current, _decision("BULLISH", gamma_flip=current["gamma_flip"]), previous, opposite_confirmations=1
    )
    assert result["action"] == "WARN_REVERSAL"


def test_opposite_signal_plus_adverse_price_shock_exits_immediately():
    previous = {"spot": 23300, "gamma_flip": 23200, "option_chain": [{"volume": 100}]}
    current = {"spot": 23350, "gamma_flip": 23200, "option_chain": [{"volume": 300}]}
    result = evaluate_intrade_reversal(
        "BEARISH", current, _decision("BULLISH", gamma_flip=current["gamma_flip"]), previous, opposite_confirmations=1
    )
    assert result["action"] == "EXIT_REVERSAL"
    assert result["price_shock"] is True


def test_gamma_flip_cross_without_opposite_direction_holds():
    # A gamma-flip cross alone is not a directional reversal. This protects
    # the behavior observed on 2026-09-30, where the bearish thesis remained
    # bearish while gamma transitioned from negative to positive.
    previous = {"spot": 22697.8, "gamma_flip": 22716.27}
    current = {"spot": 22723.75, "gamma_flip": 22719.76}
    result = evaluate_intrade_reversal(
        "BEARISH", current, _decision("BEARISH", gamma_flip=current["gamma_flip"]), previous, opposite_confirmations=0
    )
    assert result["gamma_flip_crossed"] is True
    assert result["action"] == "HOLD"
    assert result["severe_reversal"] is False


def test_opposite_direction_plus_gamma_flip_cross_exits():
    previous = {"spot": 22697.8, "gamma_flip": 22716.27}
    current = {"spot": 22723.75, "gamma_flip": 22719.76}
    result = evaluate_intrade_reversal(
        "BEARISH", current, _decision("BULLISH"), previous, opposite_confirmations=1
    )
    assert result["gamma_flip_crossed"] is True
    assert result["action"] == "EXIT_REVERSAL"
    assert result["severe_reversal"] is True
