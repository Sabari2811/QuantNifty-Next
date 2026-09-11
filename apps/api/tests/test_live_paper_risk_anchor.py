from quantnifty.live_paper_manager import DEFAULT_NIFTY_LOT_SIZE, _quantity, _risk_levels


def test_nifty_paper_defaults_to_one_full_lot():
    assert DEFAULT_NIFTY_LOT_SIZE == 65
    assert _quantity({}, {}) == 65


def test_bearish_active_risk_is_anchored_to_entry_spot():
    levels = _risk_levels(23256.12, "BEARISH", {"stop_points": 80.23, "target_points": 160.46, "risk_reward": 2.0})
    assert levels["stop_spot"] == 23336.35
    assert levels["target_spot"] == 23095.66
    assert levels["risk_reward"] == 2.0


def test_bullish_active_risk_is_anchored_to_entry_spot():
    levels = _risk_levels(23256.12, "BULLISH", {"stop_points": 80.23, "target_points": 160.46, "risk_reward": 2.0})
    assert levels["stop_spot"] == 23175.89
    assert levels["target_spot"] == 23416.58
