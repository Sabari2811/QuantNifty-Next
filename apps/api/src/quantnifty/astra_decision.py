from __future__ import annotations

import json
import os
from typing import Any

import httpx


ASTRA_MODEL = "gpt-6-astra"
ASTRA_URL = "https://api.openai.com/v1/responses"
_last_fingerprint: tuple[Any, ...] | None = None
_last_review: dict[str, Any] | None = None

_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["APPROVE", "HOLD", "REJECT"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "direction": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"]},
        "regime": {"type": "string"},
        "setup_quality": {"type": "string", "enum": ["A", "B", "C", "D"]},
        "conflicts": {"type": "array", "items": {"type": "string"}},
        "invalidation": {"type": "string"},
        "reason_codes": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["decision", "confidence", "direction", "regime", "setup_quality", "conflicts", "invalidation", "reason_codes", "summary"],
    "additionalProperties": False,
}


def _disabled(reason: str) -> dict[str, Any]:
    return {"status": "UNAVAILABLE", "provider": "OPENAI", "model": ASTRA_MODEL, "decision": "HOLD", "confidence": 0.0, "reason": reason}


def _output_text(payload: dict[str, Any]) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text
    for item in payload.get("output") or []:
        for part in item.get("content") or []:
            value = part.get("text")
            if isinstance(value, str) and value.strip():
                return value
    return ""


def _fingerprint(data: dict[str, Any], signal: dict[str, Any], risk: dict[str, Any]) -> tuple[Any, ...]:
    adaptive = signal.get("adaptive") or {}
    return (
        signal.get("direction"),
        round(float(signal.get("confidence") or 0) / 5) * 5,
        adaptive.get("selected_strategy"),
        adaptive.get("regime"),
        (signal.get("gamma") or {}).get("regime"),
        (signal.get("oi_flow") or {}).get("bias"),
        (signal.get("volatility") or {}).get("regime"),
        round(float(data.get("spot") or 0) / 25) * 25,
        round(float(data.get("atm_iv") or 0)),
        bool(risk.get("approved")),
    )


def review_decision(data: dict[str, Any], signal: dict[str, Any], risk: dict[str, Any], mode: str) -> dict[str, Any]:
    global _last_fingerprint, _last_review
    if str(mode).upper() != "LIVE":
        return _disabled("live_only")
    if not bool(risk.get("approved")):
        return _disabled("quant_risk_not_approved")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _disabled("OPENAI_API_KEY_not_configured")

    fingerprint = _fingerprint(data, signal, risk)
    if _last_fingerprint == fingerprint and _last_review is not None:
        cached = dict(_last_review)
        cached["cached"] = True
        return cached

    evidence = {
        "market": {
            "timestamp": data.get("timestamp"),
            "spot": data.get("spot"),
            "bias": data.get("bias"),
            "confidence": data.get("confidence"),
            "liquidity_score": data.get("liquidity_score"),
            "atm_iv": data.get("atm_iv"),
            "gamma_flip": data.get("gamma_flip"),
            "gex": data.get("gex"),
            "dex": data.get("dex"),
            "expected_move": data.get("expected_move"),
            "pcr": data.get("pcr"),
        },
        "institutional_signal": signal,
        "risk": risk,
    }
    system = (
        "You are the Astra Decision Advisor inside QuantNifty-Next. "
        "Review only the supplied market evidence. Do not invent data, future outcomes, or news. "
        "You are a veto/review layer, not an execution engine. Preserve the quantitative direction unless the evidence is contradictory. "
        "APPROVE only when the setup is coherent and risk is acceptable; HOLD when evidence is incomplete or conflicting; "
        "REJECT when a material conflict invalidates the proposed entry. Never recommend broker execution."
    )
    body = {
        "model": ASTRA_MODEL,
        "reasoning": {"effort": "low"},
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(evidence, separators=(",", ":"), default=str)},
        ],
        "text": {"format": {"type": "json_schema", "name": "astra_decision_review", "strict": True, "schema": _SCHEMA}},
        "store": False,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
            response = client.post(ASTRA_URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body)
        response.raise_for_status()
        parsed = json.loads(_output_text(response.json()))
        result = {"status": "AVAILABLE", "provider": "OPENAI", "model": ASTRA_MODEL, "cached": False, **parsed}
        _last_fingerprint = fingerprint
        _last_review = result
        return result
    except Exception as exc:
        return _disabled(f"request_failed:{type(exc).__name__}")
