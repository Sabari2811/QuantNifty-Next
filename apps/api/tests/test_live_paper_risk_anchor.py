from quantnifty.live_paper_manager import DEFAULT_NIFTY_LOT_SIZE, _delta_premium_levels, _quantity, _risk_levels


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


def test_delta_converts_nifty_risk_points_to_option_premium_risk():
    risk = {"stop_points": 80.0, "target_points": 160.0}
    levels = _delta_premium_levels(189.35, -0.65, risk)
    assert levels["delta"] == 0.65
    assert levels["premium_stop"] == 137.35
    assert levels["premium_target"] == 293.35
    assert levels["premium_stop_distance"] == 52.0
    assert levels["premium_target_distance"] == 104.0


def test_delta_risk_changes_when_live_delta_changes():
    risk = {"stop_points": 100.0, "target_points": 200.0}
    slow_delta = _delta_premium_levels(200.0, -0.50, risk)
    high_delta = _delta_premium_levels(200.0, -0.80, risk)
    assert slow_delta["premium_stop"] == 150.0
    assert slow_delta["premium_target"] == 300.0
    assert high_delta["premium_stop"] == 120.0
    assert high_delta["premium_target"] == 360.0
    assert high_delta["premium_stop"] != slow_delta["premium_stop"]


def test_delta_is_required_for_delta_driven_entry_risk():
    unavailable = _delta_premium_levels(189.35, None, {"stop_points": 80.0, "target_points": 160.0})
    assert unavailable["premium_stop"] is None
    assert unavailable["premium_target"] is None
    assert unavailable["method"] == "DELTA_UNAVAILABLE"
