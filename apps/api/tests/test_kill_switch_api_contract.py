from pathlib import Path


def test_kill_switch_api_is_explicit_not_toggle():
    source = (Path(__file__).parents[1] / "src" / "quantnifty" / "main.py").read_text(encoding="utf-8")
    start = source.index('@app.post("/api/v1/paper/kill-switch")')
    end = source.index('@app.post("/api/v1/replay/decisions")', start)
    block = source[start:end]
    assert "payload: dict[str, Any] = Body(...)" in block
    assert '"enabled" not in payload' in block
    assert "not current" not in block
    assert "requested != current" not in block
    assert "enabled") is not True" in block
    assert "NEXT_TRADING_DAY_AUTOMATIC" in block


def test_kill_switch_ui_sends_explicit_state():
    source = (Path(__file__).parents[1] / "src" / "quantnifty" / "web" / "intelligence.html").read_text(encoding="utf-8")
    assert "body:JSON.stringify({enabled:!active" in source
    assert "RELEASE KILL SWITCH" not in source
    assert "RESETS NEXT TRADING DAY" in source
    assert "body:JSON.stringify({enabled:true})" in source
