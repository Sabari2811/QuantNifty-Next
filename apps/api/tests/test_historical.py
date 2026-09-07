from quantnifty.historical import canonicalize_snapshot, canonicalize_snapshots, historical_data_status


def snap(ts, provenance="RECORDED_HISTORICAL"):
    return {
        "timestamp": ts,
        "spot": 25000,
        "option_chain": [{"strike": 25000, "side": "CE", "security_id": "1", "last_price": 100, "oi": 1000, "volume": 5000}],
        "data_integrity": provenance,
    }


def test_canonicalizes_and_sorts_historical_snapshots():
    out = canonicalize_snapshots([snap("2026-09-01T09:16:00+00:00"), snap("2026-09-01T09:15:00+00:00")])
    assert [x["timestamp"] for x in out] == ["2026-09-01T09:15:00+00:00", "2026-09-01T09:16:00+00:00"]
    assert out[0]["historical_snapshot"] is True
    assert out[0]["rows"] == 1


def test_rejects_incomplete_option_leg():
    bad = snap("2026-09-01T09:15:00+00:00")
    del bad["option_chain"][0]["security_id"]
    try:
        canonicalize_snapshot(bad)
    except ValueError as exc:
        assert "security_id" in str(exc)
    else:
        raise AssertionError("incomplete option leg must be rejected")


def test_live_provider_data_is_the_live_learning_source():
    result = historical_data_status([snap("2026-09-01T09:15:00+00:00", "LIVE_PROVIDER")])
    assert result["status"] == "LIVE_DATA"
    assert result["learning_ready"] is True
    assert result["learning_status"] == "LIVE_LEARNING_ONLY"
    assert result["live_learning_source"] == "LIVE_PROVIDER"
    assert result["post_market_learning_source"] == "STORED_DAY"


def test_no_one_year_history_gate():
    result = historical_data_status([
        snap("2026-09-01T09:15:00+00:00"),
        snap("2026-09-01T09:16:00+00:00"),
    ])
    assert result["learning_ready"] is True
    assert result["learning_status"] == "LIVE_LEARNING_ONLY"
    assert "days_missing" not in result
    assert "minimum_learning_trading_days" not in result
    assert "minimum_learning_calendar_days" not in result
    assert result["historical_replay_only"] is True
