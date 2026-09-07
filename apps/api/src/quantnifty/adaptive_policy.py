from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

POLICY_SCHEMA = "adaptive-policy-v1"
ANCHOR_STRATEGY = "adaptive"


@dataclass(frozen=True)
class PolicyCandidate:
    strategy: str
    score: float
    samples: int
    win_rate_pct: float
    net_pnl: float


@dataclass(frozen=True)
class ValidatedPolicy:
    version: int
    created_day: str
    strategy: str
    regime: str
    score: float
    samples: int
    status: str
    fallback: str = ANCHOR_STRATEGY


def _candidate(strategy: str, metrics: dict[str, Any]) -> PolicyCandidate:
    samples = int(metrics.get("trades") or 0)
    pnl = float(metrics.get("net_pnl") or 0.0)
    win = float(metrics.get("win_rate_pct") or 0.0)
    score = pnl / max(1, samples) + win * 0.10
    return PolicyCandidate(strategy, round(score, 4), samples, round(win, 2), round(pnl, 2))


def validate_policy(day: str, regime: str, anchor_metrics: dict[str, Any], candidate_metrics: dict[str, dict[str, Any]], version: int = 1, min_samples: int = 5, min_improvement: float = 0.08) -> dict[str, Any]:
    anchor = _candidate(ANCHOR_STRATEGY, anchor_metrics)
    candidates = [_candidate(name, metrics) for name, metrics in candidate_metrics.items()]
    eligible = [c for c in candidates if c.samples >= min_samples]
    winner = max([anchor, *eligible], key=lambda c: c.score)
    improvement = (winner.score - anchor.score) / max(1.0, abs(anchor.score)) if anchor.score else 0.0
    promoted = winner.strategy != ANCHOR_STRATEGY and improvement >= min_improvement and winner.score > anchor.score
    selected = winner.strategy if promoted else ANCHOR_STRATEGY
    status = "VALIDATED" if promoted or winner.strategy == ANCHOR_STRATEGY else "FALLBACK"
    policy = ValidatedPolicy(version, day, selected, regime, round(winner.score, 4), winner.samples, status)
    return {"schema": POLICY_SCHEMA, "policy": asdict(policy), "anchor": asdict(anchor), "candidates": [asdict(c) for c in candidates], "improvement_vs_anchor": round(improvement, 4), "promotion_gate": {"min_samples": min_samples, "min_improvement": min_improvement}, "future_safe": True, "counterfactual_source": True}
