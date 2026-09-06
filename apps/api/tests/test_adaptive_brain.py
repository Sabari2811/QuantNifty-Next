from quantnifty.research_brain import adaptive_day_policy, update_adaptive_memory


def snap(spot=24500, bias="BULLISH", gex=10):
    return {
        "spot": spot,
        "bias": bias,
        "liquidity_score": 80,
        "expected_move": {"move": 100},
        "atm_iv": 15,
        "gex": gex,
        "option_chain": [],
    }


def test_adaptive_day_policy_uses_prior_memory_without_future_outcome():
    memory = {
        "by_regime": {
            "TREND_UP": {
                "directional": {"trades": 5, "wins": 1, "losses": 4, "net_pnl": -500},
                "gamma_blast": {"trades": 5, "wins": 4, "losses": 1, "net_pnl": 500},
            }
        },
        "global": {},
        "recent_days": [{"day": "2026-08-03", "net_pnl": 100, "trades": 1}],
        "last_direction": "BULLISH",
    }
    policy = adaptive_day_policy(snap(), None, memory)
    assert policy["regime"] == "TREND_UP"
    assert policy["selected_strategy"] == "gamma_blast"
    assert "learned override" in policy["reason"]


def test_adaptive_memory_only_changes_after_closed_trade():
    memory = {"by_regime": {}, "global": {}, "recent_days": [], "last_direction": None}
    before = adaptive_day_policy(snap(), None, memory)
    assert before["learning"]["global_samples"]["directional"] == 0
    updated = update_adaptive_memory(memory, {"net_pnl": -120, "direction": "BEARISH"}, "2026-08-04", "TREND_UP", "directional")
    assert updated["global"]["directional"]["trades"] == 1
    assert updated["global"]["directional"]["losses"] == 1
    assert updated["by_regime"]["TREND_UP"]["directional"]["net_pnl"] == -120
    assert updated["last_direction"] == "BEARISH"
