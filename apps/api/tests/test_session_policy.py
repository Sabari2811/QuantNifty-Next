from quantnifty.session_policy import session_decision_policy, session_phase


def snap(ts, cas=None):
    data = {"timestamp": ts}
    if cas is not None:
        data["cas"] = cas
    return data


def test_adaptive_window_starts_at_0920():
    assert session_phase(snap("2026-09-07T03:50:00Z"))["phase"] == "NORMAL_ADAPTIVE"
    assert session_phase(snap("2026-09-07T03:49:59Z"))["phase"] == "PRE_OPEN"


def test_cas_reentry_replaces_normal_brain_after_1515():
    result = session_decision_policy(snap("2026-09-07T09:45:00Z", {"direction": "BULLISH", "confidence": 85}))
    assert result["phase"] == "CAS_REENTRY"
    assert result["selected_strategy"] == "cas_reentry"
    assert result["preferred_direction"] == "BULLISH"
    assert result["allow_normal_adaptive"] is False


def test_cas_window_waits_without_valid_live_cas():
    result = session_decision_policy(snap("2026-09-07T09:50:00Z"))
    assert result["phase"] == "CAS_REENTRY"
    assert result["selected_strategy"] == "standby"
    assert result["allow_new_trade"] is False


def test_after_close_is_blocked():
    result = session_decision_policy(snap("2026-09-07T10:00:01Z", {"direction": "BULLISH", "confidence": 99}))
    assert result["phase"] == "CLOSED"
    assert result["allow_new_trade"] is False
