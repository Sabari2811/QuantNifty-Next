from quantnifty.research_optimizer import optimize_candidates, parameter_grid


def test_parameter_grid_is_deterministic():
    rows = parameter_grid({"stop": [50, 100], "target": [100, 200]})
    assert rows == [
        {"stop": 50, "target": 100},
        {"stop": 50, "target": 200},
        {"stop": 100, "target": 100},
        {"stop": 100, "target": 200},
    ]


def test_optimizer_prefers_oos_edge_over_win_rate():
    ranked = optimize_candidates(
        [{"name": "weak"}, {"name": "strong"}],
        lambda p: {
            "out_of_sample": {
                "trades": 40,
                "profit_factor": 1.3 if p["name"] == "strong" else 1.1,
                "expectancy_per_trade": 50 if p["name"] == "strong" else 100,
                "max_drawdown_pct": 10,
            }
        },
    )
    assert ranked[0]["parameters"]["name"] == "strong"
    assert ranked[0]["robustness_gate"]["passed"] is True
