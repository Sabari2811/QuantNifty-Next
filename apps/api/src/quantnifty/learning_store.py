from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "adaptive-learning-event-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root() -> Path:
    return Path(os.getenv("QUANTNIFTY_LEARNING_ROOT", "/tmp/quantnifty-learning"))


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
            except json.JSONDecodeError:
                continue
    return rows


def _append(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    root = _root(); root.mkdir(parents=True, exist_ok=True)
    event = {"schema_version": SCHEMA_VERSION, "event_id": f"{kind}:{payload.get('timestamp') or _utc_now()}", "kind": kind, "stored_at": _utc_now(), **payload}
    path = root / f"{kind}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_json(event) + "\n")
    return event


def record_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return _append("snapshots", {"timestamp": snapshot.get("timestamp"), "day": str(snapshot.get("timestamp") or "")[:10], "snapshot": snapshot})


def record_decision(snapshot: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return _append("decisions", {"timestamp": snapshot.get("timestamp"), "day": str(snapshot.get("timestamp") or "")[:10], "strategy": decision.get("strategy"), "decision": decision})


def record_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    return _append("outcomes", {"timestamp": outcome.get("timestamp"), "day": outcome.get("day"), "outcome": outcome})


def record_research(research: dict[str, Any]) -> dict[str, Any]:
    return _append("research", {"timestamp": research.get("timestamp"), "day": research.get("day"), "research": research})


def load_snapshots(day: str | None = None) -> list[dict[str, Any]]:
    events = _read_jsonl(_root() / "snapshots.jsonl")
    values = [e.get("snapshot") for e in events if isinstance(e.get("snapshot"), dict)]
    if day:
        values = [v for v in values if str(v.get("timestamp") or "")[:10] == day]
    return sorted(values, key=lambda v: str(v.get("timestamp") or ""))


def load_events(kind: str, day: str | None = None) -> list[dict[str, Any]]:
    events = _read_jsonl(_root() / f"{kind}.jsonl")
    return [e for e in events if not day or str(e.get("day") or "") == day]


def learning_status() -> dict[str, Any]:
    root = _root()
    return {"configured": True, "root": str(root), "exists": root.exists(), "snapshots": len(_read_jsonl(root / "snapshots.jsonl")), "decisions": len(_read_jsonl(root / "decisions.jsonl")), "outcomes": len(_read_jsonl(root / "outcomes.jsonl")), "research_runs": len(_read_jsonl(root / "research.jsonl")), "durability": "FILESYSTEM_ONLY", "warning": "Use a durable mounted store for production; local filesystem is a safe development fallback."}
