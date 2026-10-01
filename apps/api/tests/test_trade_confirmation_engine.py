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


def test_level_break_uses_previous_frozen_level_not_moving_current_level():
    previous = _snapshot(spot=22660.0, premium=175.0, volume=1000000, support=22650.0)
    # Current support moved down after price moved. The break must still be
    # evaluated against the previous 22650 level.
    current = _snapshot(spot=22645.0, premium=182.0, volume=1100000, support=22630.0)
    result = trade_confirmation(current, previous, _signal(), "early_accumulation")
    assert result["level"] == 22650.0
    assert result["gates"]["key_level_break"]
    assert result["take_trade"]


def test_level_does_not_count_as_new_break_if_price_was_already_beyond_it():
    previous = _snapshot(spot=22640.0, premium=175.0, volume=1000000, support=22650.0)
    current = _snapshot(spot=22635.0, premium=182.0, volume=1100000, support=22630.0)
    result = trade_confirmation(current, previous, _signal(), "early_accumulation")
    assert not result["gates"]["key_level_break"]
    assert "KEY_LEVEL_NOT_BROKEN" in result["reasons"]


def test_volume_confirmation_uses_selected_directional_contract():
    previous = _snapshot(spot=22660.0, premium=175.0, volume=1000000, support=22650.0)
    current = _snapshot(spot=22645.0, premium=175.0, volume=1005000, support=22630.0)
    # Aggregate chain volume is irrelevant; the selected PE contract is what
    # confirms participation.
    result = trade_confirmation(current, previous, _signal(), "early_accumulation")
    assert result["gates"]["volume_expansion"]


def test_insufficient_displacement_cannot_release_trade_even_with_other_confirmations():
    previous = _snapshot(spot=22660.0, premium=175.0, volume=1000000, support=22650.0)
    # The move breaks the frozen support, but 11 points is below the
    # expected-move-derived minimum (~24.85 points). All other confirmation
    # signals are positive, so this specifically proves displacement is a
    # mandatory gate rather than merely one item in the 4-of-6 score.
    current = _snapshot(spot=22649.0, premium=182.0, volume=1100000, support=22630.0)
    result = trade_confirmation(current, previous, _signal(), "early_accumulation")
    assert result["gates"]["key_level_break"]
    assert not result["gates"]["displacement"]
    assert result["score"] >= 4
    assert result["status"] == "SETUP"
    assert not result["confirmed"]
    assert not result["take_trade"]
    assert "INSUFFICIENT_DISPLACEMENT" in result["reasons"]
