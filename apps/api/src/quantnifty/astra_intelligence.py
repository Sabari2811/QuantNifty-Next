from __future__ import annotations

import json
import os
from typing import Any

import httpx

MODEL = os.getenv("ASTRA_MODEL", "gpt-6-astra").strip() or "gpt-6-astra"
API_URL = os.getenv("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses").strip()
ENABLED = os.getenv("ASTRA_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
TIMEOUT = max(2.0, float(os.getenv("ASTRA_TIMEOUT_SECONDS", "8")))
MIN_CONFIDENCE = max(0.0, min(100.0, float(os.getenv("ASTRA_MIN_CONFIDENCE", "70"))))

_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["WAIT", "ENTER", "HOLD", "EXIT"]},
        "direction": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "thesis": {"type": "string"},
        "invalidation": {"type": "string"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "direction", "confidence", "thesis", "invalidation", "reasons", "risk_flags"],
    "additionalProperties": False,
}


def _compact_market(data: dict[str, Any], previous: dict[str, Any] | None, deterministic: dict[str, Any]) -> dict[str, Any]:
    state = deterministic.get("market_state") or {}
    return {
        "spot": data.get("spot"), "expiry": data.get("expiry"), "bias": data.get("bias"),
        "confidence": data.get("confidence"), "pcr": data.get("pcr"), "gex": data.get("gex"),
        "dex": data.get("dex"), "atm_iv": data.get("atm_iv"), "iv_skew": data.get("iv_skew"),
        "gamma_flip": data.get("gamma_flip"), "max_pain": data.get("max_pain"),
        "expected_move": data.get("expected_move"), "support": data.get("support"),
        "resistance": data.get("resistance"), "dealer_flow": data.get("dealer_flow"),
        "liquidity_score": data.get("liquidity_score"), "market_state": state.get("state"),
        "events": deterministic.get("events", [])[:8], "move_attribution": deterministic.get("move_attribution"),
        "signal_dna": deterministic.get("signal_dna", []), "deterministic_decision": deterministic.get("decision"),
        "previous_spot": (previous or {}).get("spot"), "previous_gex": (previous or {}).get("gex"),
        "previous_atm_iv": (previous or {}).get("atm_iv"),
    }


def _extract_output_text(payload: dict[str, Any]) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                value = content.get("text")
                if isinstance(value, str) and value.strip():
                    return value
    raise ValueError("Astra response did not contain output text")


def _disabled(reason: str) -> dict[str, Any]:
    return {"provider": "GPT-6 Astra", "model": MODEL, "enabled": False, "available": False,
            "decision_role": "ADVISORY_FILTER", "decision": "WAIT", "direction": "NEUTRAL", "confidence": 0.0,
            "thesis": reason, "invalidation": "Astra unavailable; deterministic risk controls remain authoritative.",
            "reasons": [], "risk_flags": ["ASTRA_UNAVAILABLE"]}


def evaluate_astra(data: dict[str, Any], previous: dict[str, Any] | None, deterministic: dict[str, Any], mode: str = "LIVE") -> dict[str, Any]:
    """Run GPT-6 Astra as a bounded decision-intelligence filter."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not ENABLED:
        return _disabled("Astra intelligence is disabled by configuration.")
    if not api_key:
        return _disabled("Astra intelligence is configured but OPENAI_API_KEY is not present.")
    if mode != "LIVE":
        return _disabled("Astra live decision intelligence is restricted to LIVE mode.")
    market = _compact_market(data, previous, deterministic)
    instructions = ("You are QuantNifty's GPT-6 Astra decision-intelligence layer. Analyze only supplied market evidence. "
                    "Do not invent missing data. You are a precision filter, not a broker. Never bypass risk controls. "
                    "For LIVE mode never use future information. Prefer WAIT when evidence conflicts, liquidity is poor, "
                    "market state is compressed, or the thesis is weak. ENTER is advisory and valid only when the "
                    "deterministic decision already says trade_ready=true. Return a falsifiable thesis and invalidation condition.")
    body = {
        "model": MODEL, "store": False, "reasoning": {"effort": os.getenv("ASTRA_REASONING_EFFORT", "medium")},
        "instructions": instructions, "input": json.dumps({"mode": mode, "market": market}, separators=(",", ":"), default=str),
        "text": {"format": {"type": "json_schema", "name": "quantnifty_astra_decision", "strict": True, "schema": _SCHEMA}},
        "max_output_tokens": 900,
    }
    try:
        response = httpx.post(API_URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body, timeout=TIMEOUT)
        response.raise_for_status()
        payload = response.json(); parsed = json.loads(_extract_output_text(payload)); decision = str(parsed.get("decision", "WAIT")).upper(); confidence = float(parsed.get("confidence", 0))
        if not bool((deterministic.get("decision") or {}).get("trade_ready")) and decision == "ENTER":
            decision = "WAIT"; parsed.setdefault("risk_flags", []).append("DETERMINISTIC_GATE_REJECTED")
        return {"provider": "GPT-6 Astra", "model": MODEL, "enabled": True, "available": True,
                "decision_role": "ADVISORY_FILTER", "decision": decision,
                "direction": str(parsed.get("direction", "NEUTRAL")).upper(), "confidence": max(0.0, min(100.0, confidence)),
                "thesis": str(parsed.get("thesis", "")), "invalidation": str(parsed.get("invalidation", "")),
                "reasons": [str(x) for x in parsed.get("reasons", [])], "risk_flags": [str(x) for x in parsed.get("risk_flags", [])],
                "api_response_id": payload.get("id"), "min_confidence": MIN_CONFIDENCE}
    except Exception as exc:
        return {**_disabled("Astra request failed; deterministic decision remains authoritative."),
                "error_type": type(exc).__name__, "error": str(exc)[:240]}
