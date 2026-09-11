import json

from quantnifty import astra_intelligence as astra


def test_astra_disabled_without_secret(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(astra, "ENABLED", True)
    result = astra.evaluate_astra({"spot": 25000}, None, {"decision": {"trade_ready": True}}, "LIVE")
    assert result["provider"] == "GPT-6 Astra"
    assert result["available"] is False
    assert result["decision"] == "WAIT"


def test_astra_structured_response_can_enter(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(astra, "ENABLED", True)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "resp_test",
                "output_text": json.dumps({
                    "decision": "ENTER",
                    "direction": "BULLISH",
                    "confidence": 88,
                    "thesis": "directional confirmation",
                    "invalidation": "loss of support",
                    "reasons": ["trend", "OI"],
                    "risk_flags": [],
                }),
            }

    monkeypatch.setattr(astra.httpx, "post", lambda *args, **kwargs: Response())
    result = astra.evaluate_astra({"spot": 25000}, None, {"decision": {"trade_ready": True}}, "LIVE")
    assert result["available"] is True
    assert result["model"] == "gpt-6-astra"
    assert result["decision"] == "ENTER"
    assert result["confidence"] == 88


def test_astra_cannot_override_deterministic_rejection(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(astra, "ENABLED", True)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "resp_test", "output_text": json.dumps({
                "decision": "ENTER", "direction": "BULLISH", "confidence": 95,
                "thesis": "x", "invalidation": "y", "reasons": ["x"], "risk_flags": [],
            })}

    monkeypatch.setattr(astra.httpx, "post", lambda *args, **kwargs: Response())
    result = astra.evaluate_astra({"spot": 25000}, None, {"decision": {"trade_ready": False}}, "LIVE")
    assert result["decision"] == "WAIT"
    assert "DETERMINISTIC_GATE_REJECTED" in result["risk_flags"]


def test_astra_is_never_used_for_replay(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(astra, "ENABLED", True)
    result = astra.evaluate_astra({"spot": 25000}, None, {"decision": {"trade_ready": True}}, "BACKTEST")
    assert result["available"] is False
    assert "LIVE_ONLY" in result["risk_flags"]
