from quantnifty.adaptive_learning import build_validated_policy, validate_live_policy


def _snapshot(ts, provenance="RECORDED_HISTORICAL"):
    return {"timestamp": ts, "spot": 25000, "option_chain": [{"strike": 25000, "side": "CE", "security_id": "1", "last_price": 100, "oi": 1000, "volume": 100}], "data_integrity": provenance}


def test_policy_stays_blocked_until_one_year_is_available():
    snapshots = [_snapshot("2025-01-01T09:20:00+05:30"), _snapshot("2025-01-02T09:20:00+05:30")]
    result = build_validated_policy(snapshots, [{"strategy": "directional", "net_pnl": 100}])
    assert result["status"] == "INSUFFICIENT_1Y_DATA"
    assert result["learning_ready"] is False


def test_live_policy_rejects_future_training_end():
    policy = {
        "schema_version": "adaptive-policy-v1",
        "status": "VALIDATED_RESEARCH_POLICY",
        "learning_ready": True,
        "historical_data": {"status": "VALID_HISTORICAL"},
        "training_end": "2026-09-08T09:20:00+05:30",
    }
    result = validate_live_policy(policy, "2026-09-07T09:20:00+05:30")
    assert result["valid"] is False
    assert "future_data_leak" in result["errors"]


def test_live_policy_accepts_completed_historical_training():
    policy = {
        "schema_version": "adaptive-policy-v1",
        "status": "VALIDATED_RESEARCH_POLICY",
        "learning_ready": True,
        "historical_data": {"status": "VALID_HISTORICAL"},
        "training_end": "2026-09-06T15:30:00+05:30",
    }
    result = validate_live_policy(policy, "2026-09-07T09:20:00+05:30")
    assert result["valid"] is True
