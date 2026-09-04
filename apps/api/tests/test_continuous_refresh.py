from pathlib import Path


def test_continuous_refresh_loop_is_configured():
    source = Path('apps/api/src/quantnifty/main.py').read_text()
    assert 'async def continuous_market_refresh()' in source
    assert 'asyncio.create_task(continuous_market_refresh())' in source
    assert 'await asyncio.sleep(POLL_SECONDS)' in source
    assert 'task.cancel()' in source
    assert '"refresh_interval_seconds":POLL_SECONDS' in source
