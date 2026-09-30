from quantnifty.trade_confirmation_engine import trade_confirmation


def _snapshot(
    spot=22697.8,
    bias="BEARISH",
    support=22650.0,
    resistance=22700.0,
    premium=177.5,
    volume=1000000,
):
    return {
        "spot": spot,
        "bias": bias,
        "support": support,
        "resistance": resistance,
        "expected_move": {"move": 355.0},
        "strike_selection": [{"strike": 22800, "side": "PE", "security_id": "40716"}],
        "option_chain": [{
            "strike": 22800,
            "side": "PE",
            "security_id": "40716",
            "last_price": premium,
            "volume": volume,
        }],
    }


def _signal():
    return {
        "direction": "BEARISH",
        "oi_flow": {"bias": "BEARISH"},
        "dealer": {"delta_pressure": "BEARISH", "alignment": "CONFIRMED"},
    }


def test_early_accumulation_is_setup_before_key_level_break():
    current = _snapshot()
    previous = _snapshot(spot=22690.0, premium=176.0, volume=950000)
    result = trade_confirmation(current, previous, _signal(), "early_accumulation")
    assert result["status"] == "SETUP"
    assert not result["confirmed"]
    assert not result["take_trade"]
    assert "KEY_LEVEL_NOT_BROKEN" in result["reasons"]


def test_confirmation_requires_independent_follow_through():
    previous = _snapshot(spot=22680.0, premium=175.0, volume=950000)
    current = _snapshot(spot=22640.0, premium=182.0, volume=1100000)
    result = trade_confirmation(current, previous, _signal(), "early_accumulation")
    assert result["gates"]["key_level_break"]
    assert result["gates"]["displacement"]
    assert result["gates"]["direction_persistence"]
    assert result["gates"]["volume_expansion"]
    assert result["gates"]["oi_flow"]
    assert result["gates"]["dealer_pressure"]
    assert result["gates"]["option_premium_response"]
    assert result["status"] == "TAKE_TRADE"
    assert result["take_trade"]


def test_gamma_or_thesis_strength_cannot_bypass_level_break():
    previous = _snapshot(spot=22690.0, premium=175.0, volume=1000000)
    current = _snapshot(spot=22695.0, premium=190.0, volume=1500000)
    signal = _signal() | {"confidence": 99, "gamma": {"regime": "NEGATIVE"}}
    result = trade_confirmation(current, previous, signal, "gamma_blast")
    assert not result["take_trade"]
    assert not result["confirmed"]
    assert "KEY_LEVEL_NOT_BROKEN" in result["reasons"]


def test_cas_reentry_keeps_its_existing_authoritative_confirmation():
    result = trade_confirmation(
        _snapshot(),
        None,
        {"direction": "BEARISH"},
        "cas_reentry",
    )
    assert result["confirmed"]
    assert result["take_trade"]
    assert result["status"] == "CONFIRMED"
