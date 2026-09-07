from quantnifty.adaptive_learning import build_validated_policy, validate_live_policy


def _snapshot(ts, provenance="LIVE_PROVIDER"):
    return {"timestamp": ts, "spot": 25000, "option_chain": [{"strike": 25000, "side": "CE", "security_id": "1", "last_price": 100, "oi": 1000, "volume": 100}], "data_integrity": provenance}


def test_policy_does_not_require_one_year_history():
    snapshots = [_snapshot("2026-09-07T09:20:00+05:30"), _snapshot("2026-09-07T09:21:00+05:30")]
    result = build_validated_policy(snapshots, [{"strategy": "directional", "net_pnl": 100}])
    assert result["status"] == "VALIDATED_RESEARCH_POLICY"
    assert result["learning_ready"] is True


def test_preexisting_historical_recording_cannot_train_policy():
    snapshots = [_snapshot("2026-09-01T09:20:00+05:30", "RECORDED_HISTORICAL")]
    result = build_validated_policy(snapshots, [{"strategy": "directional", "net_pnl": 100}])
    assert result["status"] == "LIVE_LEARNING_SOURCE_REQUIRED"
    assert result["learning_ready"] is False


def test_live_policy_rejects_future_training_end():
    policy = {
        "schema_version": "adaptive-policy-v1",
        "status": "VALIDATED_RESEARCH_POLICY",
        "learning_ready": True,
        "historical_data": {"status": "LIVE_DATA", "provenance": ["LIVE_PROVIDER"]},
        "training_end": "2026-09-08T09:20:00+05:30",
    }
    result = validate_live_policy(policy, "2026-09-07T09:20:00+05:30")
    assert result["valid"] is False
    assert "future_data_leak" in result["errors"]


def test_live_policy_accepts_prior_live_training():
    policy = {
        "schema_version": "adaptive-policy-v1",
        "status": "VALIDATED_RESEARCH_POLICY",
        "learning_ready": True,
        "historical_data": {"status": "LIVE_DATA", "provenance": ["LIVE_PROVIDER"]},
        "training_end": "2026-09-06T15:30:00+05:30",
    }
    result = validate_live_policy(policy, "2026-09-07T09:20:00+05:30")
    assert result["valid"] is True
