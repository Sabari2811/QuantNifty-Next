from pathlib import Path

def test_decision_endpoint_exposes_read_only_risk_gate():
    h=Path('apps/api/src/quantnifty/main.py').read_text()
    assert '@app.get("/api/v1/decision")' in h
    # FinalDecision is authoritative: the endpoint returns its nested risk and execution plan.
    assert '"decision":result' in h
    assert 'execution_plan' in h
    assert 'DISABLED' in h
    assert 'gamma_blast' in h
