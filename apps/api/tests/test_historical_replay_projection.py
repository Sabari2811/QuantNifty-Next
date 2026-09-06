from quantnifty.institutional_engine import institutional_signal
from quantnifty.recording_loader import _recorded_intelligence


def test_recorded_analytics_projects_iv_skew_and_expected_move_into_replay_fields():
    analytics = {
        "dealer": {"dealer_gamma": "LONG", "market_mode": "TRANSITION", "total_gex": 100.0},
        "dealer_flow": {"total_dex": 200.0, "total_vanna": 50.0},
        "gamma_flip": {"gamma_flip": 24400.0, "direction": "NEGATIVE_TO_POSITIVE"},
        "oi_flow": {"summary": {"market_bias": "NEUTRAL", "trend": "TRENDING"}},
        "iv_skew": {"average_call_iv": 12.0, "average_put_iv": 14.0, "iv_skew": 2.0, "iv_bias": "PUTS_EXPENSIVE"},
        "expected_move": {"expected_move": 100.0, "lower": 24300.0, "upper": 24500.0},
        "market_structure": {"bias": "NEUTRAL", "structure": "RANGING", "confidence": 50},
        "probability": {"bullish_probability": 85, "bearish_probability": 15, "confidence": 70},
        "pcr": {"bias": "BULLISH", "sentiment": "BULLISH"},
        "technical": {"ema": {"trend": "BULLISH"}, "rsi": {"state": "BULLISH"}, "vwap": {"position": "ABOVE"}},
        "volatility": {"volatility": "NORMAL"},
        "institutional_score": {"institutional": {"score": 40, "signal": "NO TRADE", "confidence": 40}},
        "smart_strike": {"strike": 24400, "option_type": "CE", "reasons": ["ATM Strike"]},
    }
    result = _recorded_intelligence(analytics, [{"strike": 24400, "side": "CE", "security_id": "1"}])
    assert result["atm_iv"] == 13.0
    assert result["iv_skew_details"]["iv_skew"] == 2.0
    assert result["expected_move"]["move"] == 100.0
    assert result["volatility_snapshot"] == analytics["volatility"]


def test_projected_historical_probability_drives_canonical_direction_without_recorded_decision():
    data = {
        "spot": 24500,
        "bias": "NEUTRAL",
        "data_integrity": "RECORDED_HISTORICAL",
        "option_chain": [{"strike": 24400, "side": "CE", "security_id": "1", "last_price": 100, "oi": 1000, "volume": 5000}],
        "liquidity_score": 100,
        "intelligence": {"market_state": {"state": "TRANSITION"}},
        "probability": {"bullish_probability": 85, "bearish_probability": 15, "confidence": 70},
        "technical": {"ema": {"trend": "BULLISH"}, "vwap": {"position": "ABOVE"}},
        "pcr": {"bias": "BULLISH"},
        "dealer_gamma": "LONG",
        "gex": 100,
        "dex": 100,
        "vanna_proxy": 10,
        "recorded_oi_flow_bias": "NEUTRAL",
        "expected_move": {"move": 100},
    }
    result = institutional_signal(data)
    assert result["direction"] == "BULLISH"
    assert result["confidence"] >= 70
    assert result["historical_evidence"]["bullish_probability"] == 85
