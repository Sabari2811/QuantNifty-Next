from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Any, Iterator


@contextmanager
def stage_timer(stages: dict[str, float], name: str) -> Iterator[None]:
    started = perf_counter()
    try:
        yield
    finally:
        stages[name] = round((perf_counter() - started) * 1000.0, 3)


def summarize_latency(stages: dict[str, float]) -> dict[str, Any]:
    total = round(sum(stages.values()), 3)
    return {
        "unit": "ms",
        "stages": dict(stages),
        "total_ms": total,
        "critical_path": True,
    }
