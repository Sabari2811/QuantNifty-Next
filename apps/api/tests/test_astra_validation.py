from quantnifty.decision_validation import validate_astra_gate


def test_astra_gate_is_advisory_and_does_not_invalidate_open_risk():
    data = {"intelligence": {"astra_intelligence": {
        "available": True, "decision": "WAIT", "confidence": 64, "min_confidence": 70,
    }}}
    result = {"risk": {"approved": True}}
    stage = validate_astra_gate(data, result, "LIVE")
    assert stage["valid"] is True
    assert stage["advisory"] is True
    assert stage["would_reject_entry"] is True


def test_astra_gate_is_inactive_when_unavailable():
    data = {"intelligence": {"astra_intelligence": {"available": False}}}
    result = {"risk": {"approved": True}}
    stage = validate_astra_gate(data, result, "LIVE")
    assert stage["valid"] is True
    assert stage["applied"] is False


def test_astra_gate_is_not_used_for_backtest():
    data = {"intelligence": {"astra_intelligence": {"available": True, "decision": "WAIT", "confidence": 10}}}
    result = {"risk": {"approved": True}}
    stage = validate_astra_gate(data, result, "BACKTEST")
    assert stage["valid"] is True
    assert stage["applied"] is False
