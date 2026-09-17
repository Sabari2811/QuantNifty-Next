from pathlib import Path


ROOT = Path(__file__).parents[1]
INTELLIGENCE_HTML = ROOT / "src" / "quantnifty" / "web" / "intelligence.html"
MAIN_PY = ROOT / "src" / "quantnifty" / "main.py"


def test_live_monitor_shows_current_and_previous_trade_sections():
    text = INTELLIGENCE_HTML.read_text(encoding="utf-8")
    for label in [
        "Active Paper Trade · Live P&amp;L",
        "Previous Trades Today",
        "Option Premium",
        "Premium Target / SL",
        "Where price is moving now",
        "Entry Spot",
        "Current Spot",
        "Spot Move",
        "Exit Premium",
        "realized_pnl",
        "entry_risk",
    ]:
        assert label in text, f"missing live trade monitor field: {label}"


def test_live_monitor_reads_durable_paper_ledger_not_research_data():
    text = INTELLIGENCE_HTML.read_text(encoding="utf-8")
    assert "/api/v1/paper/ledger" in text
    assert "renderTradeHistory" in text
    assert "ledger.ledger" in text
    assert "ledger.open_positions" in text
    assert "/api/v1/paper/signal" not in text


def test_main_exposes_read_only_paper_ledger_router():
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "from quantnifty.paper_ledger_api import router as paper_ledger_router" in text
    assert "app.include_router(paper_ledger_router)" in text
