from pathlib import Path


HTML = Path(__file__).parents[1] / "src" / "quantnifty" / "web" / "index.html"


def test_dashboard_retains_legacy_live_option_chain_details():
    text = HTML.read_text(encoding="utf-8")
    required = [
        "Live Option Chain",
        "All",
        "Calls",
        "Puts",
        "ATM",
        "Side",
        "Strike",
        "Security ID",
        "LTP",
        "Prev Close",
        "OI",
        "OI Δ",
        "Volume",
        "Bid",
        "Bid Qty",
        "Ask",
        "Ask Qty",
        "IV %",
        "Delta",
        "Gamma",
        "Theta",
        "Vega",
        "Data Integrity",
    ]
    for label in required:
        assert label in text, f"missing dashboard detail: {label}"


def test_dashboard_retains_all_current_analytics_sections():
    text = HTML.read_text(encoding="utf-8")
    required = [
        "Market Snapshot",
        "Key Market Levels",
        "Market Level Map",
        "Gamma Walls",
        "Expected Move Range",
        "Market Structure",
        "Dealer Flow",
        "Directional Score",
        "Positioning & Volatility",
        "Reference Levels & Feed",
        "Market Intelligence Charts",
        "OI Distribution",
        "Gamma Profile",
        "IV Smile",
        "Dealer Positioning",
        "Vanna Proxy",
        "IV Skew",
        "Gamma Flip",
        "Max Pain",
        "Liquidity",
        "Bullish Score",
        "Bearish Score",
    ]
    for label in required:
        assert label in text, f"missing analytics UI detail: {label}"


def test_dashboard_binds_visualizations_and_chain_to_provider_payload():
    text = HTML.read_text(encoding="utf-8")
    assert "d.option_chain" in text
    assert "currentChain=Array.isArray(d.option_chain)?d.option_chain:[]" in text
    assert "renderCharts(currentChain)" in text
    assert "strikeSeries(rows,'oi')" in text
    assert "gamma_contribution" in text
    assert "LIVE_PROVIDER" in text
    assert "No mock values are rendered" in text
