from quantnifty.edge_lab import build_edge_analysis


def _snap(ts, spot, premium):
    return {
        "timestamp": ts,
        "spot": spot,
        "bias": "BEARISH",
        "expected_move": {"move": 100},
        "option_chain": [{"strike": 22800, "side": "PE", "security_id": "PE1", "last_price": premium, "volume": 1000}],
    }


def _decision(ts, spot, approved, level=22700):
    return {
        "timestamp": ts,
        "decision": {
            "strategy": "adaptive",
            "signal": {
                "direction": "BEARISH",
                "confidence": 85,
                "adaptive": {"selected_strategy": "early_accumulation"},
            },
            "risk": {
                "approved": approved,
                "reasons": [] if approved else ["trade_confirmation"],
                "confirmation": {
                    "status": "TAKE_TRADE" if approved else "SETUP",
                    "take_trade": approved,
                    "level": level,
                    "move_points": 15,
                    "minimum_displacement_points": 8,
                    "score": 5,
                    "gates": {
                        "key_level_break": approved,
                        "displacement": True,
                        "direction_persistence": True,
                        "volume_expansion": approved,
                        "oi_flow": True,
                        "dealer_pressure": True,
                        "option_premium_response": approved,
                    },
                    "reasons": [] if approved else ["KEY_LEVEL_NOT_BROKEN"],
                },
            },
            "execution_plan": {
                "instrument": {
                    "side": "PE", "strike": 22800, "security_id": "PE1",
                    "delta": -0.55, "iv": 12.0, "last_price": 100,
                },
            },
            "validation": {"decision_action": "TAKE_TRADE" if approved else "WAIT_CONFIRMATION"},
        },
    }


def test_edge_analysis_labels_blocked_follow_through_without_calling_it_a_live_trade():
    snaps = [
        _snap("2026-10-01T09:15:00+00:00", 22710, 100),
        _snap("2026-10-01T09:20:00+00:00", 22690, 105),
        _snap("2026-10-01T09:25:00+00:00", 22650, 112),
        _snap("2026-10-01T09:30:00+00:00", 22620, 120),
        _snap("2026-10-01T10:00:00+00:00", 22580, 130),
    ]
    result = build_edge_analysis(snaps, [_decision("2026-10-01T09:15:00+00:00", 22710, False)])
    assert result["do_not_enter_setups"] == 1
    assert result["counterfactual_follow_through"] == 1
    assert result["observations_detail"][0]["counterfactual_only"] is True


def test_edge_analysis_requires_three_observations_for_edge_candidate():
    snaps = [
        _snap("2026-10-01T09:15:00+00:00", 22710, 100),
        _snap("2026-10-01T09:20:00+00:00", 22690, 105),
        _snap("2026-10-01T09:25:00+00:00", 22670, 110),
        _snap("2026-10-01T09:30:00+00:00", 22640, 120),
        _snap("2026-10-01T09:35:00+00:00", 22620, 130),
    ]
    events = [_decision("2026-10-01T09:15:00+00:00", 22710, False),
              _decision("2026-10-01T09:20:00+00:00", 22690, False),
              _decision("2026-10-01T09:25:00+00:00", 22670, False)]
    result = build_edge_analysis(snaps, events)
    assert result["edge_candidates"]
    assert result["edge_candidates"][0]["observations"] == 3
