from quantnifty.institutional_engine import final_decision
from quantnifty.decision_validation import validate_snapshot


def snapshot(ts="2026-08-04T04:30:00+00:00"):
    return {
        "timestamp": ts,
        "spot": 24500,
        "bias": "BULLISH",
        "liquidity_score": 85,
        "data_integrity": "LIVE_PROVIDER",
        "expected_move": {"move": 100},
        "atm_iv": 15,
        "gex": -10,
        "dex": 20,
        "option_chain": [
            {"strike": 24500, "side": "CE", "oi": 1100, "previous_oi": 1000, "last_price": 90, "previous_close": 88, "volume": 1000},
            {"strike": 24500, "side": "PE", "oi": 900, "previous_oi": 1000, "last_price": 80, "previous_close": 82, "volume": 900},
        ],
        "strike_selection": {"candidates": [{"strike": 24500, "side": "CE", "security_id": "CE1"}]},
    }


def test_live_snapshot_validation_requires_live_provider():
    assert validate_snapshot(snapshot(), "LIVE")["valid"]
    bad = snapshot(); bad["data_integrity"] = "RECORDED_HISTORICAL"
    assert not validate_snapshot(bad, "LIVE")["valid"]


def test_final_decision_exposes_validated_stages():
    result = final_decision(snapshot(), None, "directional", "LIVE")
    validation = result["validation"]
    assert validation["valid"]
    assert all(validation["stages"][stage]["valid"] for stage in ("input", "signal", "risk", "execution_plan"))
    assert result["trading"] == "DISABLED"


def test_invalid_live_data_cannot_be_approved():
    bad = snapshot(); bad["timestamp"] = ""
    result = final_decision(bad, None, "directional", "LIVE")
    assert result["status"] == "NO_TRADE"
    assert not result["risk"]["approved"]
    assert "decision_validation" in result["risk"]["reasons"]


def test_replay_uses_recorded_historical_provenance():
    data = snapshot(); data["data_integrity"] = "RECORDED_HISTORICAL"
    result = final_decision(data, None, "adaptive", "REPLAY")
    assert result["validation"]["stages"]["input"]["valid"]
