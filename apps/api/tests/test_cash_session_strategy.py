from datetime import datetime
from zoneinfo import ZoneInfo

from quantnifty.cash_session_strategy import evaluate_cash_strategy
from quantnifty.paper_trade_tracker import session_close_required
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


def test_cas_window_and_derivatives_close_are_distinct():
    assert session_phase({"timestamp": datetime(2026, 9, 17, 15, 14, tzinfo=IST).isoformat()})["phase"] == "NORMAL_ADAPTIVE"
    assert session_phase({"timestamp": datetime(2026, 9, 17, 15, 15, tzinfo=IST).isoformat()})["phase"] == "CAS_REENTRY"
    assert session_phase({"timestamp": datetime(2026, 9, 17, 15, 35, tzinfo=IST).isoformat()})["phase"] == "DERIVATIVES_CLOSE_ONLY"
    assert session_phase({"timestamp": datetime(2026, 9, 17, 15, 40, tzinfo=IST).isoformat()})["phase"] == "CLOSED"


def test_cas_strategy_is_deterministic_and_read_only():
    previous = snapshot(datetime(2026, 9, 17, 15, 14, 30, tzinfo=IST).isoformat(), 23388.0)
    current = snapshot(datetime(2026, 9, 17, 15, 15, 0, tzinfo=IST).isoformat(), 23400.0)
    result = evaluate_cash_strategy(current, previous)
    assert result["strategy"] == "cas_reentry"
    assert result["read_only_execution"] is True
    assert result["research_only"] is False
    assert result["direction"] == "BULLISH"
    assert result["score"] >= 70
    assert result["cas"]["nifty_options_participate_in_cas"] is False


def test_cas_policy_uses_deterministic_strategy_without_future_auction_result():
    previous = snapshot(datetime(2026, 9, 17, 15, 14, 30, tzinfo=IST).isoformat(), 23388.0)
    current = snapshot(datetime(2026, 9, 17, 15, 15, 0, tzinfo=IST).isoformat(), 23400.0)
    policy = session_decision_policy(current, previous)
    assert policy["phase"] == "CAS_REENTRY"
    assert policy["selected_strategy"] == "cas_reentry"
    assert policy["cas"]["source"] == "DETERMINISTIC_CAS_AWARE"
    assert policy["cas_strategy"]["strategy"] == "cas_reentry"
    assert policy["cash_strategy"]["strategy"] == "cas_reentry"


def test_cas_entry_stops_before_matching_end_and_position_exits_before_derivatives_close():
    previous = snapshot(datetime(2026, 9, 17, 15, 29, 30, tzinfo=IST).isoformat(), 23398.0)
    current = snapshot(datetime(2026, 9, 17, 15, 30, 0, tzinfo=IST).isoformat(), 23400.0)
    policy = session_decision_policy(current, previous)
    assert policy["selected_strategy"] == "standby"
    assert policy["allow_new_trade"] is False
    assert session_close_required(datetime(2026, 9, 17, 15, 29, tzinfo=IST).isoformat()) is False
    assert session_close_required(datetime(2026, 9, 17, 15, 39, tzinfo=IST).isoformat()) is True
