from quantnifty.dual_learning import summarize_live_and_post_market


def test_dual_learning_keeps_live_and_post_tracks_independent():
    result = summarize_live_and_post_market(
        [{"strategy": "directional", "net_pnl": 100}],
        {"strategies": {"directional": {"status": "TESTED", "metrics": {"net_pnl": 250}, "trades": []}}},
    )
    row = result["comparison"][0]
    assert row["live"]["net_pnl"] == 100
    assert row["post_market"]["net_pnl"] == 250
    assert row["combined_pnl"] == 350
    assert result["post_market_track"]["independent_from_live_trades"] is True


def test_dual_learning_identifies_positive_and_negative_strategies():
    result = summarize_live_and_post_market(
        [{"strategy": "good", "net_pnl": 100}, {"strategy": "bad", "net_pnl": -200}],
        {"strategies": {
            "good": {"status": "TESTED", "metrics": {"net_pnl": 50}, "trades": []},
            "bad": {"status": "TESTED", "metrics": {"net_pnl": -20}, "trades": []},
        }},
    )
    assert "good" in result["profitable_strategies"]
    assert "bad" in result["negative_strategies"]


def test_dual_learning_handles_missing_track_without_fabrication():
    result = summarize_live_and_post_market([], {"strategies": {"x": {"status": "TESTED", "metrics": {"net_pnl": 10}}}})
    assert result["comparison"][0]["live"]["trades"] == 0
    assert result["comparison"][0]["live"]["net_pnl"] == 0.0
    assert result["read_only"] is True
