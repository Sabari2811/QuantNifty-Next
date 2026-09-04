from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class Candle:
    ts: int
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


@dataclass(frozen=True)
class ReplayPoint:
    ts: int
    close: float
    return_pct: float
    direction: str


def normalize_candles(payload: dict[str, Any], scrip_code: str | None = None) -> list[Candle]:
    """Normalize INDstocks historical response into deterministic candles.

    INDstocks returns data keyed by scrip code and candle timestamps in epoch seconds.
    The caller may select one code; otherwise the single returned series is used.
    """
    data = payload.get("data") or {}
    if not isinstance(data, dict) or not data:
        return []
    key = scrip_code or next(iter(data))
    series = data.get(key) or {}
    raw = series.get("candles") if isinstance(series, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[Candle] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(Candle(
                ts=int(item["ts"]),
                o=float(item["o"]), h=float(item["h"]),
                l=float(item["l"]), c=float(item["c"]),
                v=float(item.get("v", 0) or 0),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, key=lambda x: x.ts)


def replay(candles: Iterable[Candle]) -> list[ReplayPoint]:
    """Produce a deterministic close-to-close replay stream.

    This is deliberately signal-neutral: it replays market state without placing,
    modifying, or cancelling orders. It is the safe foundation for later strategy
    replay because it has no broker side effects.
    """
    ordered = sorted(candles, key=lambda x: x.ts)
    if not ordered:
        return []
    points: list[ReplayPoint] = []
    previous = ordered[0].c
    points.append(ReplayPoint(ordered[0].ts, ordered[0].c, 0.0, "FLAT"))
    for candle in ordered[1:]:
        pct = ((candle.c - previous) / previous * 100.0) if previous else 0.0
        direction = "UP" if pct > 0 else "DOWN" if pct < 0 else "FLAT"
        points.append(ReplayPoint(candle.ts, candle.c, pct, direction))
        previous = candle.c
    return points


def summary(points: Iterable[ReplayPoint]) -> dict[str, Any]:
    values = list(points)
    if not values:
        return {"count": 0, "first_ts": None, "last_ts": None, "start": None, "end": None,
                "net_return_pct": 0.0, "up_bars": 0, "down_bars": 0, "flat_bars": 0}
    start, end = values[0].close, values[-1].close
    return {
        "count": len(values),
        "first_ts": values[0].ts,
        "last_ts": values[-1].ts,
        "start": start,
        "end": end,
        "net_return_pct": ((end - start) / start * 100.0) if start else 0.0,
        "up_bars": sum(p.direction == "UP" for p in values[1:]),
        "down_bars": sum(p.direction == "DOWN" for p in values[1:]),
        "flat_bars": sum(p.direction == "FLAT" for p in values[1:]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def to_dict(points: Iterable[ReplayPoint]) -> list[dict[str, Any]]:
    return [asdict(p) for p in points]
