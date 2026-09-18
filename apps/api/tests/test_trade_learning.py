from quantnifty.trade_learning import analyze_trade_lesson, summarize_trade_lessons


def _outcome():
    return {
        "trade_id": "T1",
        "day": "2026-09-18",
        "strategy": "transition",
        "direction": "BEARISH",
        "entry_spot": 23298.5,
        "exit_spot": 23363.6,
        "entry_price": 155.9,
        "exit_price": 108.7,
        "entry_delta": -0.64,
        "exit_reason": "DELTA_PREMIUM_STOP",
        "entry_risk": {"stop_spot": 23380.6, "target_spot": 23134.3},
        "entry_reasons": {"adaptive_regime": "GAMMA_TRANSITION"},
        "entry_decision": {
            "signal": {"oi_flow": "BULLISH", "gamma": "POSITIVE_GAMMA"},
            "market": {"bias": "BULLISH"},
        },
    }


def test_trade_lesson_captures_directional_conflict_and_premium_stop():
    lesson = analyze_trade_lesson(_outcome())
    assert "DIRECTIONAL_CONTEXT_CONFLICT" in lesson["patterns"]
    assert "PREMIUM_STOP_BEFORE_SPOT_INVALIDATION" in lesson["patterns"]
    assert lesson["adverse_spot_points"] == 65.1
    assert lesson["premium_change"] == -47.2
    assert lesson["spot_stop_hit"] is False


def test_trade_lesson_requires_multiple_observations_before_parameter_change():
    summary = summarize_trade_lessons([analyze_trade_lesson(_outcome())])
    assert summary["observations"] == 1
    assert ">=3 comparable observations" in summary["promotion_rule"]
