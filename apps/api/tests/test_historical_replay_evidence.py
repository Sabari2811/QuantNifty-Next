from quantnifty.institutional_engine import institutional_signal
from quantnifty.recording_loader import _recorded_intelligence


def test_recorded_intelligence_preserves_directional_inputs():
    analytics = {
        "dealer": {"dealer_gamma": "LONG", "market_mode": "TRANSITION", "total_gex": 100.0},
        "dealer_flow": {"dealer_delta": "LONG", "dealer_vanna": "POSITIVE", "dealer_pressure": "NEUTRAL", "total_dex": 200.0, "total_vanna": 50.0},
        "gamma_flip": {"gamma_flip": 24400.0, "direction": "NEGATIVE_TO_POSITIVE"},
        "oi_flow": {"summary": {"market_bias": "NEUTRAL", "trend": "TRENDING"}},
        "iv_skew": {"average_call_iv": 0.10, "average_put_iv": 0.14, "iv_skew": -0.04, "iv_bias": "PUTS_EXPENSIVE"},
        "expected_move": {"expected_move": 100.0, "lower": 24300.0, "upper": 24500.0},
        "market_structure": {"bias": "NEUTRAL", "structure": "RANGING", "confidence": 50},
        "probability": {"bullish_probability": 85, "bearish_probability": 15, "confidence": 70},
        "pcr": {"bias": "BULLISH", "sentiment": "BULLISH"},
        "technical": {"ema": {"trend": "BULLISH"}, "rsi": {"state": "BULLISH"}, "vwap": {"position": "ABOVE"}},
        "volatility": {"volatility": "NORMAL"},
        "institutional_score": {"institutional": {"score": 40, "signal": "NO TRADE", "confidence": 40}},
        "smart_strike": {"strike": 24400, "option_type": "CE", "reasons": ["ATM Strike", "Good Liquidity"]},
    }
    result = _recorded_intelligence(analytics, [{"strike": 24400, "side": "CE", "security_id": "1"}])
    assert result["probability"]["bullish_probability"] == 85
    assert result["pcr"]["bias"] == "BULLISH"
    assert result["technical"]["ema"]["trend"] == "BULLISH"
    assert result["dealer_gamma"] == "LONG"
    assert result["recorded_institutional_score"]["signal"] == "NO TRADE"
    assert result["strike_selection"][0]["security_id"] == "1"


def test_historical_probability_can_supply_replay_direction_without_recorded_decision():
    data = {
        "spot": 24500,
        "bias": "NEUTRAL",
        "data_integrity": "RECORDED_HISTORICAL",
        "option_chain": [],
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
