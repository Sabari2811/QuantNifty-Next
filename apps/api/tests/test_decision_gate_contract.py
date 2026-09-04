from pathlib import Path
def test_decision_endpoint_exposes_read_only_risk_gate():
    h=Path('apps/api/src/quantnifty/main.py').read_text()
    assert '@app.get("/api/v1/decision")' in h
    assert 'risk_gate' in h and 'execution' in h and 'DISABLED' in h
    assert 'gamma_blast_qualified' in h
