from pathlib import Path

WEB = Path(__file__).parents[1] / "src" / "quantnifty" / "web"


def test_intelligence_screen_exposes_backtest_navigation():
    text = (WEB / "intelligence.html").read_text(encoding="utf-8")
    assert 'href="/backtest"' in text
    assert "Backtest &amp; Validation" in text
    assert 'data-qn-nav="backtest"' in text


def test_all_primary_screens_expose_backtest_navigation():
    for name in ("index.html", "intelligence.html", "backtest.html"):
        text = (WEB / name).read_text(encoding="utf-8")
        assert 'href="/backtest"' in text, f"{name} lost Backtest navigation"
        assert "Backtest &amp; Validation" in text, f"{name} lost Backtest label"


def test_intelligence_marks_current_screen_without_hiding_backtest():
    text = (WEB / "intelligence.html").read_text(encoding="utf-8")
    assert 'data-qn-nav="intelligence"' in text
    assert 'data-qn-nav="raw"' in text
    assert 'data-qn-nav="backtest"' in text
    assert "path==='/intelligence'" in text
