from pathlib import Path

def test_decision_endpoint_exposes_read_only_risk_gate():
    h=Path('apps/api/src/quantnifty/main.py').read_text()
    assert '@app.get("/api/v1/decision")' in h
    # The endpoint delegates to the canonical FinalDecision object, which owns risk and execution plan.
    assert 'from quantnifty.institutional_engine import final_decision' in h
    assert '"decision":result' in h
    assert '"mode":"READ_ONLY"' in h
    assert '"strategy":"gamma_blast"' in h
