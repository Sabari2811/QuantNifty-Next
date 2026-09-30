from __future__ import annotations

from typing import Any


DIRECTIONS = {"BULLISH", "BEARISH"}


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _direction(value: Any) -> str:
    return str(value or "").strip().upper()


def _row_key(row: dict[str, Any]) -> tuple[str, float, str]:
    return (
        str(row.get("security_id") or ""),
        _f(row.get("strike")),
        _direction(row.get("side") or row.get("option_type")),
    )


def _find_leg(snapshot: dict[str, Any], current: dict[str, Any]) -> dict[str, Any] | None:
    key = _row_key(current)
    for row in snapshot.get("option_chain") or []:
        if isinstance(row, dict) and _row_key(row) == key:
            return row
    return None


def _option_response(
    snapshot: dict[str, Any],
    previous: dict[str, Any] | None,
    direction: str,
) -> tuple[bool, float | None]:
    selections = snapshot.get("strike_selection") or []
    if isinstance(selections, dict):
        selections = selections.get("candidates") or selections.get("strikes") or []
    wanted = "CE" if direction == "BULLISH" else "PE"
    candidate = next(
        (
            row for row in selections
            if isinstance(row, dict)
            and _direction(row.get("side") or row.get("option_type")) == wanted
        ),
        None,
    )
    if not candidate or not isinstance(previous, dict):
        return False, None
    current = _find_leg(snapshot, candidate)
    if not current:
        return False, None
    previous_leg = _find_leg(previous, candidate)
    if not previous_leg:
        return False, None
    current_price = _f(current.get("last_price"))
    previous_price = _f(previous_leg.get("last_price"))
    if current_price <= 0 or previous_price <= 0:
        return False, None
    change_pct = (current_price - previous_price) / previous_price * 100.0
    return (change_pct > 0.0), round(change_pct, 3)


def trade_confirmation(
    snapshot: dict[str, Any],
    previous: dict[str, Any] | None,
    signal: dict[str, Any],
    strategy: str,
) -> dict[str, Any]:
    direction = _direction(signal.get("direction"))
    strategy = str(strategy or "").strip().lower()
    spot = _f(snapshot.get("spot"))
    prev_spot = _f((previous or {}).get("spot"))
    expected_move = _f((snapshot.get("expected_move") or {}).get("move"))

    if direction not in DIRECTIONS:
        return {
            "status": "NO_DIRECTION",
            "confirmed": False,
            "take_trade": False,
            "direction": direction,
            "strategy": strategy,
            "score": 0,
            "required": 4,
            "gates": {},
            "reasons": ["direction_required"],
        }

    if strategy in {"standby", "range"}:
        return {
            "status": "NOT_APPLICABLE",
            "confirmed": False,
            "take_trade": False,
            "direction": direction,
            "strategy": strategy,
            "score": 0,
            "required": 4,
            "gates": {"strategy_entry": False},
            "reasons": ["strategy_does_not_open_directional_trade"],
        }

    if strategy == "cas_reentry":
        return {
            "status": "CONFIRMED",
            "confirmed": True,
            "take_trade": True,
            "direction": direction,
            "strategy": strategy,
            "score": 100,
            "required": 0,
            "gates": {"cas_confirmation": True},
            "reasons": ["existing_cas_confirmation_is_authoritative"],
        }

    if not previous or spot <= 0 or prev_spot <= 0:
        return {
            "status": "SETUP",
            "confirmed": False,
            "take_trade": False,
            "direction": direction,
            "strategy": strategy,
            "score": 0,
            "required": 4,
            "gates": {"previous_snapshot": False},
            "reasons": ["previous_snapshot_required"],
        }

    move_points = abs(spot - prev_spot)
    min_displacement = max(8.0, min(25.0, expected_move * 0.07 if expected_move > 0 else 12.0))
    displacement = move_points >= min_displacement

    # Freeze the trigger level from the previous snapshot. Using the current
    # support/resistance can let the level move with price and manufacture a
    # break after the fact.
    previous_support = _f((previous or {}).get("support"))
    previous_resistance = _f((previous or {}).get("resistance"))
    if direction == "BULLISH":
        level = previous_resistance
        level_break = level > 0 and prev_spot < level and spot >= level
    else:
        level = previous_support
        level_break = level > 0 and prev_spot > level and spot <= level

    previous_bias = _direction(previous.get("bias"))
    current_bias = _direction(snapshot.get("bias"))
    persistence = current_bias == direction and previous_bias == direction

    pre = snapshot.get("intelligence") if isinstance(snapshot.get("intelligence"), dict) else {}
    oi = signal.get("oi_flow") if isinstance(signal.get("oi_flow"), dict) else {}
    dealer = signal.get("dealer") if isinstance(signal.get("dealer"), dict) else {}
    flow_confirmed = _direction(oi.get("bias")) == direction
    dealer_confirmed = _direction(dealer.get("delta_pressure")) == direction and _direction(dealer.get("alignment")) == "CONFIRMED"

    # Option-chain volume is cumulative. Compare the selected directional
    # contract instead of summing the whole chain across a short poll interval.
    selections = snapshot.get("strike_selection") or []
    if isinstance(selections, dict):
        selections = selections.get("candidates") or selections.get("strikes") or []
    wanted = "CE" if direction == "BULLISH" else "PE"
    volume_candidate = next(
        (
            row for row in selections
            if isinstance(row, dict)
            and _direction(row.get("side") or row.get("option_type")) == wanted
        ),
        None,
    )
    current_leg = _find_leg(snapshot, volume_candidate) if isinstance(volume_candidate, dict) else None
    previous_leg = _find_leg(previous, volume_candidate) if isinstance(volume_candidate, dict) else None
    previous_volume = _f((previous_leg or {}).get("volume"))
    current_volume = _f((current_leg or {}).get("volume"))
    volume_change = (
        (current_volume - previous_volume) / previous_volume * 100.0
        if previous_volume > 0
        else 0.0
    )
    # A meaningful selected-contract increase is sufficient for volume
    # participation. Premium response remains an independent alternative.
    volume_confirmed = (
        current_volume > previous_volume
        and (volume_change >= 1.0 or current_volume - previous_volume >= 1000.0)
    )

    premium_confirmed, premium_change = _option_response(snapshot, previous, direction)

    supporting = sum(
        1 for value in (displacement, persistence, volume_confirmed, flow_confirmed, dealer_confirmed, premium_confirmed)
        if value
    )
    # A directional trade is never released from a setup solely because the
    # thesis is strong. A real price-level break is mandatory; three additional
    # independent confirmations are required to avoid duplicate/redundant gates.
    confirmed = level_break and supporting >= 4
    take_trade = confirmed and persistence and (volume_confirmed or premium_confirmed) and (flow_confirmed or dealer_confirmed)

    reasons: list[str] = []
    if not level_break:
        reasons.append("KEY_LEVEL_NOT_BROKEN")
    if not displacement:
        reasons.append("INSUFFICIENT_DISPLACEMENT")
    if not persistence:
        reasons.append("DIRECTION_NOT_PERSISTENT")
    if not volume_confirmed:
        reasons.append("VOLUME_NOT_EXPANDED")
    if not flow_confirmed:
        reasons.append("OI_FLOW_NOT_CONFIRMED")
    if not dealer_confirmed:
        reasons.append("DEALER_PRESSURE_NOT_CONFIRMED")
    if not premium_confirmed:
        reasons.append("OPTION_PREMIUM_NOT_RESPONDING")

    status = "TAKE_TRADE" if take_trade else "CONFIRMED" if confirmed else "SETUP"
    return {
        "status": status,
        "confirmed": confirmed,
        "take_trade": take_trade,
        "direction": direction,
        "strategy": strategy,
        "score": supporting,
        "required": 4,
        "gates": {
            "key_level_break": level_break,
            "displacement": displacement,
            "direction_persistence": persistence,
            "volume_expansion": volume_confirmed,
            "oi_flow": flow_confirmed,
            "dealer_pressure": dealer_confirmed,
            "option_premium_response": premium_confirmed,
        },
        "level": round(level, 2) if level > 0 else None,
        "spot": round(spot, 4),
        "previous_spot": round(prev_spot, 4),
        "move_points": round(move_points, 4),
        "minimum_displacement_points": round(min_displacement, 4),
        "volume_change_pct": round(volume_change, 3),
        "option_premium_change_pct": premium_change,
        "reasons": reasons,
        "method": "LEVEL_BREAK_PLUS_INDEPENDENT_CONFIRMATIONS",
    }
