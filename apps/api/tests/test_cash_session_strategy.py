from datetime import datetime
from zoneinfo import ZoneInfo

from quantnifty.cash_session_strategy import evaluate_cash_strategy
from quantnifty.session_policy import session_decision_policy, session_phase

IST = ZoneInfo("Asia/Kolkata")


def snapshot(ts: str, spot: float = 23400.0) -> dict:
    return {
        "timestamp": ts,
        "spot": spot,
        "bias": "BULLISH",
        "liquidity_score": 80,
        "gex": -100,
        "atm_iv": 15.0,
        "expected_move": {"move": 100.0},
        "option_chain": [
            {"strike": 23400, "side": "CE", "last_price": 120, "previous_close": 110, "oi": 12000, "previous_oi": 11000, "volume": 2000},
            {"strike": 23400, "side": "PE", "last_price": 80, "previous_close": 75, "oi": 5000, "previous_oi": 4900, "volume": 300},
        ],
    }


def test_cash_session_starts_at_1515_and_ends_before_1530():
    assert session_phase({"timestamp": datetime(2026, 9, 17, 15, 14, tzinfo=IST).isoformat()})["phase"] == "NORMAL_ADAPTIVE"
    assert session_phase({"timestamp": datetime(2026, 9, 17, 15, 15, tzinfo=IST).isoformat()})["phase"] == "CAS_REENTRY"
    assert session_phase({"timestamp": datetime(2026, 9, 17, 15, 30, tzinfo=IST).isoformat()})["phase"] == "CLOSED"


def test_cash_strategy_is_deterministic_and_read_only():
    previous = snapshot(datetime(2026, 9, 17, 15, 14, 30, tzinfo=IST).isoformat(), 23388.0)
    current = snapshot(datetime(2026, 9, 17, 15, 15, 0, tzinfo=IST).isoformat(), 23400.0)
    result = evaluate_cash_strategy(current, previous)
    assert result["strategy"] == "cash_session"
    assert result["read_only_execution"] is True
    assert result["research_only"] is False
    assert result["direction"] == "BULLISH"
    assert result["score"] >= 70


def test_cash_policy_uses_deterministic_strategy_without_provider_cas_payload():
    previous = snapshot(datetime(2026, 9, 17, 15, 14, 30, tzinfo=IST).isoformat(), 23388.0)
    current = snapshot(datetime(2026, 9, 17, 15, 15, 0, tzinfo=IST).isoformat(), 23400.0)
    policy = session_decision_policy(current, previous)
    assert policy["phase"] == "CAS_REENTRY"
    assert policy["selected_strategy"] == "cas_reentry"
    assert policy["cas"]["source"] == "DETERMINISTIC_CASH_SESSION"
    assert policy["cash_strategy"]["strategy"] == "cash_session"
