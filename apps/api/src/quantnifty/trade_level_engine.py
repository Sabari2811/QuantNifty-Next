from __future__ import annotations

from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _level_score(row: dict[str, Any], max_oi: float, max_volume: float) -> float:
    oi = max(_f(row.get("oi")), 0.0)
    volume = max(_f(row.get("volume")), 0.0)
    bid = max(_f(row.get("bid")), 0.0)
    ask = max(_f(row.get("ask")), 0.0)
    book = min(1.0, bid / ask) if ask > 0 and bid > 0 else 0.0
    return 0.55 * (oi / max_oi if max_oi else 0.0) + 0.25 * (volume / max_volume if max_volume else 0.0) + 0.20 * book


def _pick_level(rows: list[dict[str, Any]], side: str, spot: float, direction: str) -> dict[str, Any] | None:
    # PE OI below spot is treated as support; CE OI above spot as resistance.
    if side == "PE":
        candidates = [r for r in rows if _f(r.get("strike")) < spot]
    else:
        candidates = [r for r in rows if _f(r.get("strike")) > spot]
    if not candidates:
        return None
    max_oi = max((_f(r.get("oi")) for r in candidates), default=0.0)
    max_volume = max((_f(r.get("volume")) for r in candidates), default=0.0)
    scored = []
    for row in candidates:
        strike = _f(row.get("strike"))
        if strike <= 0:
            continue
        distance = abs(strike - spot)
        # Prefer the nearest meaningful wall, with OI/liquidity used to break ties.
        proximity = 1.0 / max(distance, 1.0)
        score = _level_score(row, max_oi, max_volume) + min(0.35, proximity * 8.0)
        scored.append((score, distance, row))
    if not scored:
        return None
    _, _, row = max(scored, key=lambda item: item[0])
    return {
        "strike": round(_f(row.get("strike")), 2),
        "side": str(row.get("side") or side).upper(),
        "oi": round(_f(row.get("oi")), 2),
        "volume": round(_f(row.get("volume")), 2),
        "bid": round(_f(row.get("bid")), 4),
        "ask": round(_f(row.get("ask")), 4),
        "score": round(_level_score(row, max_oi, max_volume), 4),
    }


def derive_trade_levels(data: dict[str, Any], direction: str, entry_spot: float | None = None) -> dict[str, Any]:
    direction = str(direction or "").upper()
    spot = _f(entry_spot if entry_spot is not None else data.get("spot"))
    rows = [r for r in (data.get("option_chain") or []) if isinstance(r, dict)]
    if spot <= 0 or direction not in {"BULLISH", "BEARISH"}:
        return {"source": "UNAVAILABLE", "support": None, "resistance": None, "stop_spot": None, "target_spot": None, "stop_points": None, "target_points": None, "risk_reward": None}

    support = _pick_level(rows, "PE", spot, direction)
    resistance = _pick_level(rows, "CE", spot, direction)

    expected_move = _f((data.get("expected_move") or {}).get("move"))
    min_distance = max(25.0, spot * 0.0005)
    fallback = max(expected_move * 0.35, spot * 0.002) if expected_move > 0 else spot * 0.002

    if direction == "BULLISH":
        stop_level = _f(support.get("strike")) if support else spot - fallback
        target_level = _f(resistance.get("strike")) if resistance else spot + fallback * 2.0
        stop_points = max(min_distance, spot - stop_level + 5.0)
        target_points = max(min_distance, target_level - spot)
    else:
        stop_level = _f(resistance.get("strike")) if resistance else spot + fallback
        target_level = _f(support.get("strike")) if support else spot - fallback * 2.0
        stop_points = max(min_distance, stop_level - spot + 5.0)
        target_points = max(min_distance, spot - target_level)

    # If the nearest wall does not offer at least 1.5R, look for the next
    # option-chain wall in the intended direction before falling back.
    if target_points < stop_points * 1.5:
        target_candidates = []
        target_side = "CE" if direction == "BULLISH" else "PE"
        for row in rows:
            strike = _f(row.get("strike"))
            if (direction == "BULLISH" and str(row.get("side") or "").upper() == target_side and strike > spot) or (direction == "BEARISH" and str(row.get("side") or "").upper() == target_side and strike < spot):
                target_candidates.append(row)
        target_candidates.sort(key=lambda r: abs(_f(r.get("strike")) - spot))
        for row in target_candidates:
            candidate = abs(_f(row.get("strike")) - spot)
            if candidate >= stop_points * 1.5:
                target_points = candidate
                target_level = spot + candidate if direction == "BULLISH" else spot - candidate
                break

    stop_spot = spot - stop_points if direction == "BULLISH" else spot + stop_points
    target_spot = spot + target_points if direction == "BULLISH" else spot - target_points
    rr = target_points / stop_points if stop_points > 0 else None
    return {
        "source": "NSE_OPTION_CHAIN_OI_LIQUIDITY",
        "method": "OI_WALL_PLUS_VOLUME_BOOK_LIQUIDITY",
        "support": support,
        "resistance": resistance,
        "stop_anchor": support if direction == "BULLISH" else resistance,
        "target_anchor": resistance if direction == "BULLISH" else support,
        "stop_spot": round(stop_spot, 2),
        "target_spot": round(target_spot, 2),
        "stop_points": round(stop_points, 2),
        "target_points": round(target_points, 2),
        "risk_reward": round(rr, 2) if rr is not None else None,
        "buffer_points": 5.0,
    }
