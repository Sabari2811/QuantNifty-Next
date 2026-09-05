from __future__ import annotations

from quantnifty.institutional_engine import final_decision


def test_recorded_historical_requires_explicit_replay_mode():
    data = {
        "data_integrity": "RECORDED_HISTORICAL",
        "spot": 25000,
        "bias": "BULLISH",
        "recorded_oi_flow_bias": "BULLISH",
        "liquidity_score": 90,
        "gamma_flip": 24900,
        "gex": 100,
        "dex": 100,
        "vanna_proxy": 10,
        "atm_iv": 10,
        "iv_skew": 0,
        "expected_move": {"move": 100},
        "intelligence": {"market_state": {"state": "TREND"}},
        "strike_selection": [{"strike": 25000, "side": "CE", "security_id": "CE1"}],
        "option_chain": [{
            "strike": 25000,
            "side": "CE",
            "security_id": "CE1",
            "last_price": 100,
            "oi": 1000,
            "volume": 5000,
        }],
    }
    live_like = final_decision(data)
    replay = final_decision(data, mode="REPLAY")
    assert live_like["risk"]["gates"]["data_integrity"] is False
    assert replay["risk"]["gates"]["data_integrity"] is True
    assert replay["risk"]["approved"] is True
    assert replay["execution_plan"]["execution_enabled"] is False
