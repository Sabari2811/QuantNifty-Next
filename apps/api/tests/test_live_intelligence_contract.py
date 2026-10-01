from pathlib import Path


MAIN = Path('apps/api/src/quantnifty/main.py')


def test_snapshot_publishes_complete_intelligence_before_cache():
    source = MAIN.read_text(encoding='utf-8')
    intelligence_pos = source.index('intelligence = decision_intelligence(result, previous)')
    cache_pos = source.index('cache["snapshot"] = result')
    assert intelligence_pos < cache_pos
    assert 'result["intelligence"] = intelligence' in source
    assert 'result["intelligence_contract"] = intelligence_contract(intelligence)' in source
    assert 'contract["status"] != "OK"' in source


def test_decision_evidence_exposes_confirmation_and_risk_blockers():
    source = MAIN.read_text(encoding='utf-8')
    required = [
        'QUANTNIFTY_DECISION_EVIDENCE',
        'decision_action',
        'risk_reasons',
        'take_trade',
        'supporting_confirmations',
        'selected_strategy',
        'intelligence_contract',
    ]
    for marker in required:
        assert marker in source, f'missing decision evidence field: {marker}'


def test_health_provider_check_no_longer_uses_undefined_f_helper():
    source = MAIN.read_text(encoding='utf-8')
    assert 'def _f(' not in source
    assert '_f(cache.get("updated_at"))' not in source
    assert 'updated_at = cache.get("updated_at")' in source


def test_continuous_refresh_surfaces_decision_errors_in_logs():
    source = MAIN.read_text(encoding='utf-8')
    assert 'QUANTNIFTY_DECISION_ERROR' in source
    assert 'QUANTNIFTY_SNAPSHOT_ERROR' in source
    assert 'flush=True' in source
