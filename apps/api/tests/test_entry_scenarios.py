from quantnifty.entry_scenarios import classify_entry_scenario, scenario_contract


def test_all_live_entry_scenarios_are_explicitly_classified():
    cases = [
        ("EARLY_ACCUMULATION", "early_accumulation", "BULLISH", "EARLY_ACCUMULATION"),
        ("BREAKOUT_UP", "directional", "BULLISH", "DIRECTIONAL"),
        ("TREND_DOWN", "directional", "BEARISH", "DIRECTIONAL"),
        ("NEGATIVE_GAMMA_EXPANSION", "gamma_blast", "BEARISH", "NEGATIVE_GAMMA_EXPANSION"),
        ("GAMMA_TRANSITION", "transition", "BULLISH", "GAMMA_TRANSITION"),
        ("TREND_UP", "cas_reentry", "BULLISH", "CAS_REENTRY"),
    ]
    for regime, strategy, direction, expected in cases:
        assert classify_entry_scenario(regime, strategy, direction) == expected


def test_non_entry_states_never_become_trade_entry_scenarios():
    for regime, strategy in [
        ("LIQUIDITY_RISK", "standby"),
        ("POSITIVE_GAMMA_RANGE", "range"),
        ("COMPRESSION", "breakout_watch"),
        ("TRANSITION", "standby"),
    ]:
        contract = scenario_contract(regime, strategy, "NEUTRAL")
        assert contract["scenario"] == "NO_ENTRY"
        assert contract["entry_capable"] is False


def test_early_accumulation_confirmation_is_the_live_trigger():
    contract = scenario_contract("EARLY_ACCUMULATION", "early_accumulation", "BEARISH")
    assert contract["confirmation"] == "EARLY_ACCUMULATION_CONFIRMATION"
    assert contract["entry_capable"] is True


def test_scenario_contract_is_direction_aware_without_changing_strategy_identity():
    bullish = scenario_contract("BREAKOUT_UP", "directional", "BULLISH")
    bearish = scenario_contract("BREAKDOWN_DOWN", "directional", "BEARISH")
    assert bullish["scenario"] == bearish["scenario"] == "DIRECTIONAL"
    assert bullish["direction"] == "BULLISH"
    assert bearish["direction"] == "BEARISH"
