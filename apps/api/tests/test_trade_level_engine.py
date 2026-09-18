from quantnifty.trade_level_engine import derive_trade_levels


def _row(strike, side, oi, volume):
    return {
        "strike": strike,
        "side": side,
        "oi": oi,
        "volume": volume,
        "bid": 10.0,
        "ask": 10.5,
    }


def test_bullish_uses_pe_support_and_ce_resistance():
    data = {
        "spot": 23300.0,
        "expected_move": {"move": 100.0},
        "option_chain": [
            _row(23250, "PE", 900000, 200000),
            _row(23200, "PE", 500000, 100000),
            _row(23400, "CE", 800000, 180000),
            _row(23500, "CE", 400000, 90000),
        ],
    }
    result = derive_trade_levels(data, "BULLISH")
    assert result["source"] == "NSE_OPTION_CHAIN_OI_LIQUIDITY"
    assert result["support"]["strike"] == 23250
    assert result["resistance"]["strike"] == 23400
    assert result["stop_spot"] < 23300
    assert result["target_spot"] > 23300


def test_bearish_uses_ce_resistance_and_pe_support():
    data = {
        "spot": 23300.0,
        "expected_move": {"move": 100.0},
        "option_chain": [
            _row(23250, "PE", 900000, 200000),
            _row(23400, "CE", 800000, 180000),
        ],
    }
    result = derive_trade_levels(data, "BEARISH")
    assert result["stop_spot"] > 23300
    assert result["target_spot"] < 23300
    assert result["stop_points"] > 0
    assert result["target_points"] > 0


def test_invalid_direction_returns_unavailable():
    result = derive_trade_levels({"spot": 23300.0, "option_chain": []}, "NEUTRAL")
    assert result["source"] == "UNAVAILABLE"
