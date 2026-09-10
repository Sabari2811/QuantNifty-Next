from quantnifty.research_brain import adaptive_day_policy, strategy_selector, update_adaptive_memory
from quantnifty.learning_store import trading_day


def snap(spot=24500, bias="BULLISH", gex=10):
    return {
        "spot": spot,
        "bias": bias,
        "liquidity_score": 80,
        "expected_move": {"move": 100},
        "atm_iv": 15,
        "gex": gex,
        "option_chain": [],
        "timestamp": "2026-09-11T05:00:00+00:00",
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


def test_trading_day_is_ist_safe_at_midnight_boundary():
    assert trading_day("2026-09-10T18:29:59+00:00") == "2026-09-10"
    assert trading_day("2026-09-10T18:30:00+00:00") == "2026-09-11"


def test_same_day_closed_outcome_becomes_runtime_memory_and_prevents_stale_policy_override(monkeypatch):
    monkeypatch.setattr(
        "quantnifty.research_brain.load_events",
        lambda kind, day=None: [
            {
                "kind": "outcomes",
                "day": day,
                "outcome": {
                    "status": "CLOSED",
                    "strategy": "directional",
                    "direction": "BULLISH",
                    "realized_pnl": 250.0,
                    "entry_reasons": {"adaptive_regime": "TREND_UP", "adaptive_selected_strategy": "directional"},
                },
            }
        ],
    )
    selected = strategy_selector({**snap(), "_adaptive_policy": {"policy": {"created_day": "2026-09-10", "status": "VALIDATED", "strategy": "gamma_blast", "version": 3}, "future_safe": True}})
    assert selected["selected_strategy"] == "directional"
    assert selected["learning"]["same_day_trades"] == 1
