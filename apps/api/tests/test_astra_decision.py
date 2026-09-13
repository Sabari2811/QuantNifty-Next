from quantnifty import astra_decision


def test_astra_is_live_only(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    result = astra_decision.review_decision({}, {"direction": "BULLISH"}, {"approved": True}, "REPLAY")
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "live_only"


def test_astra_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = astra_decision.review_decision({}, {"direction": "BULLISH"}, {"approved": True}, "LIVE")
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "OPENAI_API_KEY_not_configured"


def test_astra_skips_unapproved_quant_signal(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    result = astra_decision.review_decision({}, {"direction": "BULLISH"}, {"approved": False}, "LIVE")
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "quant_risk_not_approved"


def test_astra_structured_response_and_cache(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    astra_decision._last_fingerprint = None
    astra_decision._last_review = None

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"output_text": '{"decision":"APPROVE","confidence":88,"direction":"BULLISH","regime":"EXPANSION","setup_quality":"A","conflicts":[],"invalidation":"spot thesis invalidation","reason_codes":["OI_FLOW_CONFIRMED"],"summary":"coherent setup"}'}

    calls = {"count": 0}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            calls["count"] += 1
            return FakeResponse()

    monkeypatch.setattr(astra_decision.httpx, "Client", lambda *args, **kwargs: FakeClient())
    evidence = {"spot": 23400, "atm_iv": 14}
    signal = {"direction": "BULLISH", "confidence": 80}
    risk = {"approved": True}
    result = astra_decision.review_decision(evidence, signal, risk, "LIVE")
    cached = astra_decision.review_decision(evidence, signal, risk, "LIVE")
    assert result["status"] == "AVAILABLE"
    assert result["decision"] == "APPROVE"
    assert result["confidence"] == 88
    assert cached["cached"] is True
    assert calls["count"] == 1
