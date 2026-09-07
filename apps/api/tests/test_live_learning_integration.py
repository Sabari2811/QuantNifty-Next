from quantnifty.live_paper_manager import _leg
from quantnifty.policy_runtime import load_future_policy
from quantnifty.research_strategy_runner import RESEARCH_STRATEGIES


def test_research_universe_is_complete():
    assert RESEARCH_STRATEGIES == ("directional", "gamma_blast", "adaptive", "early_accumulation", "transition", "range", "breakout_watch")


def test_option_leg_matching_prefers_security_id():
    snapshot = {"option_chain": [{"security_id": "1", "trading_symbol": "NIFTY-CE", "strike": 25000, "side": "CE"}, {"security_id": "2", "trading_symbol": "NIFTY-PE", "strike": 25000, "side": "PE"}]}
    assert _leg(snapshot, {"security_id": "2", "strike": 25000, "side": "PE"})["security_id"] == "2"


def test_future_policy_loader_rejects_current_day(monkeypatch):
    monkeypatch.setattr("quantnifty.policy_runtime.load_events", lambda kind: [{"research": {"type": "adaptive_policy", "schema": "adaptive-policy-v1", "future_safe": True, "counterfactual_source": True, "policy": {"created_day": "2026-09-07", "version": 1, "status": "VALIDATED", "strategy": "adaptive"}}}])
    assert load_future_policy("2026-09-07") is None
    assert load_future_policy("2026-09-08") is not None
