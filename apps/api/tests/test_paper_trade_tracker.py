from quantnifty.paper_trade_tracker import PaperTrade, make_trade_id, session_close_required


def test_paper_trade_tracks_mfe_mae_and_close():
    trade = PaperTrade(make_trade_id("2026-09-07T09:30:00+05:30", 1), "early_accumulation", "BULLISH", "2026-09-07T09:30:00+05:30", 25000.0)
    trade.update("2026-09-07T09:35:00+05:30", 25050.0)
    trade.update("2026-09-07T09:40:00+05:30", 24950.0)
    closed = trade.close("2026-09-07T09:45:00+05:30", 25025.0, "ADAPTIVE_TRAIL")
    assert closed["status"] == "CLOSED"
    assert closed["peak_favorable_pct"] > 0
    assert closed["worst_adverse_pct"] < 0
    assert closed["read_only"] is True
    assert closed["execution"] == "NONE"


def test_session_close_boundary():
    assert not session_close_required("2026-09-07T15:29:59+05:30")
    assert session_close_required("2026-09-07T15:30:00+05:30")
