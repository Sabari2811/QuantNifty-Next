from __future__ import annotations

from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_itm(row: dict[str, Any], spot: float) -> bool:
    strike = _num(row.get("strike"))
    return (row.get("side") == "CE" and strike < spot) or (row.get("side") == "PE" and strike > spot)


def _is_otm(row: dict[str, Any], spot: float) -> bool:
    strike = _num(row.get("strike"))
    return (row.get("side") == "CE" and strike > spot) or (row.get("side") == "PE" and strike < spot)


def _score(row: dict[str, Any], spot: float, expected_move: float | None, gamma_blast: bool) -> float:
    premium = max(_num(row.get("last_price")), 0.0)
    delta = abs(_num(row.get("delta")))
    gamma = abs(_num(row.get("gamma")))
    theta = abs(_num(row.get("theta")))
    volume = max(_num(row.get("volume")), 0.0)
    bid, ask = _num(row.get("bid")), _num(row.get("ask"))
    spread = max(0.0, ask - bid) if ask > 0 and bid > 0 else premium * 0.10
    distance = abs(_num(row.get("strike")) - spot)
    move_fit = 1.0 if not expected_move or expected_move <= 0 else max(0.0, 1.0 - max(0.0, distance - expected_move) / expected_move)
    liquidity = min(1.0, volume / 100_000.0)
    score = 45.0 * delta + 25.0 * min(1.0, gamma * 100.0) + 20.0 * move_fit + 10.0 * liquidity
    score -= 20.0 * min(1.0, spread / max(premium, 1.0))
    score -= 10.0 * min(1.0, theta / max(premium, 1.0))
    if gamma_blast:
        score += 25.0 * min(1.0, gamma * 100.0)
    return round(score, 4)


def select_strikes(
    spot: float,
    rows: list[dict[str, Any]],
    direction: str,
    *,
    gamma_blast: bool = False,
    expected_move: float | None = None,
    gamma_blast_qualified: bool = True,
) -> dict[str, Any]:
    direction = direction.upper()
    if spot <= 0 or direction not in {"BULLISH", "BEARISH"}:
        return {"eligible": False, "reason": "no_directional_signal", "candidates": [], "selected": None}
    if gamma_blast and not gamma_blast_qualified:
        return {
            "eligible": False,
            "reason": "gamma_blast_not_confirmed",
            "required_confirmation": [
                "directional_breakout_or_breakdown",
                "volume_confirmation",
                "OI_flow_confirmation",
                "gamma_acceleration",
                "dealer_flow_confirmation",
                "expected_move_expansion",
            ],
            "candidates": [],
            "selected": None,
        }
    side = "CE" if direction == "BULLISH" else "PE"
    side_rows = [r for r in rows if r.get("side") == side and _num(r.get("last_price")) > 0]
    if not side_rows:
        return {"eligible": False, "reason": "no_liquid_contracts", "candidates": [], "selected": None}

    if gamma_blast:
        # Gamma Blast is deliberately restricted to qualified OTM contracts.
        # ATM/ITM contracts remain valid for normal directional signals only.
        candidates = sorted(
            (r for r in side_rows if _is_otm(r, spot)),
            key=lambda r: abs(_num(r.get("strike")) - spot),
        )
        if expected_move and expected_move > 0:
            candidates = [r for r in candidates if abs(_num(r.get("strike")) - spot) <= expected_move]
        candidates = candidates[:2]
    else:
        atm = min(side_rows, key=lambda r: abs(_num(r.get("strike")) - spot))
        itm = sorted((r for r in side_rows if _is_itm(r, spot)), key=lambda r: abs(_num(r.get("strike")) - spot))
        candidates = [atm] + itm[:3]

    unique: dict[str, dict[str, Any]] = {}
    for row in candidates:
        unique[f"{row.get('side')}:{_num(row.get('strike')):.4f}"] = row
    ranked = []
    for row in unique.values():
        classification = "OTM" if gamma_blast else (
            "ATM" if abs(_num(row.get("strike")) - spot) == min(abs(_num(r.get("strike")) - spot) for r in side_rows)
            else "ITM"
        )
        ranked.append({
            "side": row.get("side"), "strike": _num(row.get("strike")), "classification": classification,
            "security_id": row.get("security_id", ""), "trading_symbol": row.get("trading_symbol", ""),
            "premium": _num(row.get("last_price")), "delta": _num(row.get("delta")), "gamma": _num(row.get("gamma")),
            "theta": _num(row.get("theta")), "iv": _num(row.get("iv")), "volume": _num(row.get("volume")),
            "score": _score(row, spot, expected_move, gamma_blast),
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return {
        "eligible": bool(ranked), "direction": direction,
        "strategy": "GAMMA_BLAST" if gamma_blast else "DIRECTIONAL",
        "allowed_classifications": ["OTM"] if gamma_blast else ["ATM", "ITM"],
        "selected": ranked[0] if ranked else None, "candidates": ranked,
        "reason": "best_qualified_otm_risk_adjusted_strike" if gamma_blast and ranked else "best_risk_adjusted_strike" if ranked else "no_candidate",
    }
