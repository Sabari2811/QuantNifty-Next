from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quantnifty.adaptive_policy import POLICY_SCHEMA, validate_policy
from quantnifty.learning_store import load_events, record_research

IST = ZoneInfo("Asia/Kolkata")


def _today() -> str:
    return datetime.now(IST).date().isoformat()


def next_version() -> int:
    versions = []
    for event in load_events("research"):
        research = event.get("research") if isinstance(event, dict) else None
        if isinstance(research, dict) and research.get("type") == "adaptive_policy":
            try:
                versions.append(int((research.get("policy") or {}).get("version", 0)))
            except (TypeError, ValueError):
                pass
    return max(versions, default=0) + 1


def persist_validated_policy(policy: dict[str, Any]) -> dict[str, Any]:
    if policy.get("schema") != POLICY_SCHEMA or policy.get("future_safe") is not True or policy.get("counterfactual_source") is not True:
        raise ValueError("policy failed future-safety contract")
    research = {"type": "adaptive_policy", "timestamp": datetime.now(IST).isoformat(), "day": str((policy.get("policy") or {}).get("created_day") or _today()), **policy}
    return record_research(research)


def load_future_policy(day: str | None = None) -> dict[str, Any] | None:
    target = day or _today()
    candidates = []
    for event in load_events("research"):
        research = event.get("research") if isinstance(event, dict) else None
        if not isinstance(research, dict) or research.get("type") != "adaptive_policy":
            continue
        if research.get("schema") != POLICY_SCHEMA or research.get("future_safe") is not True or research.get("counterfactual_source") is not True:
            continue
        policy = research.get("policy") or {}
        created = str(policy.get("created_day") or "")
        if created and created < target and policy.get("status") in {"VALIDATED", "FALLBACK"}:
            candidates.append((created, int(policy.get("version", 0) or 0), research))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def validate_and_persist(day: str, regime: str, anchor_metrics: dict[str, Any], candidate_metrics: dict[str, dict[str, Any]], min_samples: int = 5, min_improvement: float = 0.08) -> dict[str, Any]:
    policy = validate_policy(day, regime, anchor_metrics, candidate_metrics, version=next_version(), min_samples=min_samples, min_improvement=min_improvement)
    return persist_validated_policy(policy)
