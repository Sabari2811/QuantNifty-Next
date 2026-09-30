import asyncio

from quantnifty import main


def test_live_monitor_no_active_trade_uses_cached_provider_snapshot(monkeypatch):
    original_live_session = main.is_live_market_session
    original_snapshot = dict(main.cache)

    async def fail_api_get(*args, **kwargs):
        raise AssertionError("per-contract quote endpoint must not be called without an active paper trade")

    try:
        monkeypatch.setattr(main, "is_live_market_session", lambda: True)
        monkeypatch.setattr(main, "api_get", fail_api_get)
        main.cache["snapshot"] = {
            "spot": 22705.1,
            "timestamp": "2026-09-30T03:49:00+00:00",
            "data_integrity": "LIVE_PROVIDER",
        }
        main.live_paper.active = None
        main.live_paper.instrument = None

        result = asyncio.run(main.paper_live_monitor())

        assert result["status"] == "NO_ACTIVE_TRADE"
        assert result["spot"] == 22705.1
        assert result["quote_source"] == "LIVE_PROVIDER_OPTION_CHAIN_SNAPSHOT"
        assert result["quote_quality"] == "OK"
        assert result["trade"] is None
    finally:
        main.cache.clear()
        main.cache.update(original_snapshot)
        main.is_live_market_session = original_live_session
