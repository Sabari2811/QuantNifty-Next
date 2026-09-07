from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "adaptive-learning-event-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root() -> Path:
    return Path(os.getenv("QUANTNIFTY_LEARNING_ROOT", "/tmp/quantnifty-learning"))


def _database_url() -> str:
    return (os.getenv("QUANTNIFTY_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


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


def _pg_connection():
    url = _database_url()
    if not url:
        return None
    try:
        import psycopg
        return psycopg.connect(url, connect_timeout=5)
    except Exception:
        return None


def _ensure_pg(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS quantnifty_learning_events (event_id TEXT PRIMARY KEY, kind TEXT NOT NULL, day TEXT, timestamp TEXT, payload JSONB NOT NULL, stored_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
    conn.commit()


def _pg_append(event: dict[str, Any]) -> dict[str, Any] | None:
    conn = _pg_connection()
    if conn is None:
        return None
    try:
        _ensure_pg(conn)
        with conn.cursor() as cur:
            cur.execute("INSERT INTO quantnifty_learning_events(event_id,kind,day,timestamp,payload) VALUES (%s,%s,%s,%s,%s::jsonb) ON CONFLICT (event_id) DO NOTHING", (event["event_id"], event["kind"], event.get("day"), event.get("timestamp"), _json(event)))
        conn.commit()
        return event
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()


def _pg_events(kind: str, day: str | None = None) -> list[dict[str, Any]] | None:
    conn = _pg_connection()
    if conn is None:
        return None
    try:
        _ensure_pg(conn)
        with conn.cursor() as cur:
            if day:
                cur.execute("SELECT payload FROM quantnifty_learning_events WHERE kind=%s AND day=%s ORDER BY timestamp", (kind, day))
            else:
                cur.execute("SELECT payload FROM quantnifty_learning_events WHERE kind=%s ORDER BY timestamp", (kind,))
            return [row[0] for row in cur.fetchall() if isinstance(row[0], dict)]
    except Exception:
        return None
    finally:
        conn.close()


def _append(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {"schema_version": SCHEMA_VERSION, "event_id": f"{kind}:{payload.get('timestamp') or _utc_now()}", "kind": kind, "stored_at": _utc_now(), **payload}
    if _pg_append(event) is not None:
        return event
    root = _root(); root.mkdir(parents=True, exist_ok=True)
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
    events = _pg_events("snapshots", day)
    if events is None:
        events = _read_jsonl(_root() / "snapshots.jsonl")
        if day:
            events = [e for e in events if str(e.get("day") or "") == day]
    values = [e.get("snapshot") for e in events if isinstance(e.get("snapshot"), dict)]
    return sorted(values, key=lambda v: str(v.get("timestamp") or ""))


def load_events(kind: str, day: str | None = None) -> list[dict[str, Any]]:
    events = _pg_events(kind, day)
    if events is None:
        events = _read_jsonl(_root() / f"{kind}.jsonl")
        if day:
            events = [e for e in events if str(e.get("day") or "") == day]
    return events


def learning_status() -> dict[str, Any]:
    if _database_url():
        conn = _pg_connection()
        if conn is not None:
            try:
                _ensure_pg(conn)
                with conn.cursor() as cur:
                    cur.execute("SELECT kind, COUNT(*) FROM quantnifty_learning_events GROUP BY kind")
                    counts = {str(k): int(v) for k, v in cur.fetchall()}
                return {"configured": True, "durability": "POSTGRESQL", "database_available": True, "snapshots": counts.get("snapshots", 0), "decisions": counts.get("decisions", 0), "outcomes": counts.get("outcomes", 0), "research_runs": counts.get("research", 0)}
            finally:
                conn.close()
        return {"configured": True, "durability": "POSTGRESQL_CONFIGURED_UNAVAILABLE", "database_available": False, "warning": "Configured database could not be reached; filesystem fallback is active."}
    root = _root()
    return {"configured": True, "root": str(root), "exists": root.exists(), "snapshots": len(_read_jsonl(root / "snapshots.jsonl")), "decisions": len(_read_jsonl(root / "decisions.jsonl")), "outcomes": len(_read_jsonl(root / "outcomes.jsonl")), "research_runs": len(_read_jsonl(root / "research.jsonl")), "durability": "FILESYSTEM_ONLY", "warning": "Configure QUANTNIFTY_DATABASE_URL or DATABASE_URL for durable production storage."}
