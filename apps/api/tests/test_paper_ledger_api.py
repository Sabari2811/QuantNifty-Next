from quantnifty import paper_ledger_api


def test_paper_ledger_returns_closed_pnl_and_decision_summary(monkeypatch):
    def fake_events(kind, day=None):
        if kind == "outcomes":
            return [
                {"timestamp": "2026-09-09T10:00:00+00:00", "outcome": {"trade_id": "t1", "status": "CLOSED", "strategy": "adaptive", "direction": "BULLISH", "entry_price": 100, "exit_price": 112.5, "quantity": 1, "gross_pnl_proxy": 12.5, "pnl_basis": "OPTION_PREMIUM_WHEN_AVAILABLE_ELSE_SPOT_PROXY"}},
                {"timestamp": "2026-09-09T11:00:00+00:00", "outcome": {"trade_id": "t2", "status": "OPEN", "gross_pnl_proxy": 999}},
            ]
        if kind == "decisions":
            return [
                {"timestamp": "2026-09-09T09:30:00+00:00", "strategy": "adaptive", "decision": {"signal": {"direction": "BULLISH", "name": "BUY_CALL"}, "risk": {"approved": True}}},
                {"timestamp": "2026-09-09T09:31:00+00:00", "strategy": "adaptive", "decision": {"signal": {"direction": "BEARISH", "name": "NO_TRADE"}, "risk": {"approved": False}}},
            ]
        return []

    monkeypatch.setattr(paper_ledger_api, "load_events", fake_events)
    result = paper_ledger_api.paper_ledger("2026-09-09")

    assert result["mode"] == "READ_ONLY_PAPER"
    assert result["trading"] == "DISABLED"
    assert result["summary"]["closed_trades"] == 1
    assert result["summary"]["gross_pnl_proxy"] == 12.5
    assert result["summary"]["net_pnl"] == 12.5
    assert result["decisions"]["total"] == 2
    assert result["decisions"]["approved"] == 1
    assert result["decisions"]["blocked"] == 1
