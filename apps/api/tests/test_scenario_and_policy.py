from quantnifty.adaptive_policy import validate_policy
from quantnifty.scenario_engine import classify_scenario, extract_scenarios


def test_scenario_classification_is_deterministic():
    assert classify_scenario({"strategy": "early_accumulation"}) == "ACCUMULATION_BREAKOUT"
    assert classify_scenario({"exit_reason": "ADAPTIVE_EXHAUSTION"}) == "EXHAUSTION_OR_PROFIT_LOCK"
    assert classify_scenario({"exit_reason": "STOP"}) == "FAILED_DIRECTION"


def test_extract_scenarios_is_counterfactual():
    result = extract_scenarios({"day": "2026-09-07", "strategies": {"adaptive": {"trades": [{"direction": "BULLISH", "net_pnl": 100, "exit_reason": "ADAPTIVE_TRAIL"}]}}})
    assert result["counterfactual"] is True
    assert result["scenario_counts"]["EXHAUSTION_OR_PROFIT_LOCK"] == 1


def test_policy_requires_sample_and_improvement_before_promotion():
    result = validate_policy("2026-09-07", "EARLY_ACCUMULATION", {"trades": 10, "net_pnl": 100, "win_rate_pct": 60}, {"early_accumulation": {"trades": 3, "net_pnl": 1000, "win_rate_pct": 90}}, version=2)
    assert result["policy"]["strategy"] == "adaptive"
    assert result["policy"]["status"] == "VALIDATED"
    result2 = validate_policy("2026-09-07", "EARLY_ACCUMULATION", {"trades": 10, "net_pnl": 100, "win_rate_pct": 60}, {"early_accumulation": {"trades": 10, "net_pnl": 101, "win_rate_pct": 60}}, version=3)
    assert result2["policy"]["strategy"] == "adaptive"
