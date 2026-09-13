from pathlib import Path


MAIN = Path(__file__).parents[1] / "src" / "quantnifty" / "main.py"
HTML = Path(__file__).parents[1] / "src" / "quantnifty" / "web" / "index.html"


def test_dashboard_websocket_path_matches_backend_and_keeps_legacy_alias():
    backend = MAIN.read_text(encoding="utf-8")
    frontend = HTML.read_text(encoding="utf-8")
    assert '@app.websocket("/ws/market")' in backend
    assert '@app.websocket("/ws")' in backend
    assert "new WebSocket(`${proto}://${location.host}/ws`" in frontend


def test_backend_stops_live_provider_access_outside_nse_session():
    backend = MAIN.read_text(encoding="utf-8")
    assert "if not is_live_market_session():" in backend
    assert "NSE live market session is closed" in backend
    assert "seconds_until_next_open()" in backend
    assert '"data_integrity": "MARKET_CLOSED"' in backend or "closed_payload()" in backend
