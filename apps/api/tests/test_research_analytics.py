from quantnifty.research_analytics import robustness_gate, time_bucket, trade_diagnostics, walk_forward_splits


def test_time_bucket_uses_ist_session_windows():
    assert time_bucket("2026-09-10T09:30:00+05:30") == "09:30-10:30"
    assert time_bucket("2026-09-10T14:59:00+05:30") == "14:00-15:00"
    assert time_bucket("2026-09-10T16:00:00+05:30") == "OUTSIDE_SESSION"


def test_trade_diagnostics_groups_without_changing_trades():
    trades = [{"entry_index": 0, "timestamp": "2026-09-10T09:31:00+05:30", "direction": "BULLISH", "net_pnl": 100.0, "exit_reason": "POINT_TARGET"}]
    snapshots = [{"timestamp": "2026-09-10T09:30:00+05:30", "structure": "NEGATIVE_GAMMA_EXPANSION"}]
    report = trade_diagnostics(trades, snapshots)
    assert report["overall"]["net_pnl"] == 100.0
    assert report["by_direction"]["BULLISH"]["trades"] == 1
    assert report["by_regime"]["NEGATIVE_GAMMA_EXPANSION"]["profit_factor"] == 999.0


def test_walk_forward_is_chronological_and_has_oos():
    splits = walk_forward_splits(1000, min_train=100)
    assert len(splits) == 1
    split = splits[0]
    assert split["train"][1] == split["validation"][0]
    assert split["validation"][1] == split["out_of_sample"][0]
    assert split["out_of_sample"][0] < split["out_of_sample"][1]


def test_robustness_gate_rejects_weak_edge():
    result = robustness_gate({"trades": 10, "profit_factor": 1.01, "expectancy_per_trade": -1, "max_drawdown_pct": 30})
    assert result["passed"] is False
    assert result["checks"]["enough_trades"] is False
