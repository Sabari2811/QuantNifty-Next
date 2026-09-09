from quantnifty.decision_event_gate import DecisionEventGate


def decision(direction="BEARISH", approved=False, strategy="adaptive", selected="standby", phase="NORMAL_ADAPTIVE"):
    return {
        "direction": direction,
        "strategy": strategy,
        "risk": {
            "approved": approved,
            "selected_strategy": selected,
            "session": {"phase": phase},
        },
    }


def test_repeated_same_state_emits_once():
    gate = DecisionEventGate()
    value = decision()
    assert gate.should_emit(value) is True
    assert gate.should_emit(value) is False
    assert gate.should_emit(value) is False


def test_direction_transition_emits_new_event():
    gate = DecisionEventGate()
    assert gate.should_emit(decision("BEARISH")) is True
    assert gate.should_emit(decision("BULLISH")) is True
    assert gate.should_emit(decision("BULLISH")) is False


def test_approval_transition_emits_new_event():
    gate = DecisionEventGate()
    assert gate.should_emit(decision(approved=False)) is True
    assert gate.should_emit(decision(approved=True, selected="directional")) is True
    assert gate.should_emit(decision(approved=True, selected="directional")) is False


def test_session_boundary_is_an_event():
    gate = DecisionEventGate()
    assert gate.should_emit(decision(phase="NORMAL_ADAPTIVE")) is True
    assert gate.should_emit(decision(phase="CAS_REENTRY")) is True
    assert gate.should_emit(decision(phase="CAS_REENTRY")) is False
