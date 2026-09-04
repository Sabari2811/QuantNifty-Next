from datetime import datetime, timezone

from quantnifty.main import expected_move_value
from quantnifty.replay import Candle, normalize_candles, replay, summary


def test_normalize_indstocks_payload():
    payload = {"success": True, "data": {"NSE_1": {"candles": [
        {"ts": 2, "o": 101, "h": 103, "l": 100, "c": 102, "v": 20},
        {"ts": 1, "o": 100, "h": 102, "l": 99, "c": 101, "v": 10},
    ]}}}
    candles = normalize_candles(payload, "NSE_1")
    assert [c.ts for c in candles] == [1, 2]
    assert candles[0].c == 101.0


def test_replay_is_deterministic_and_side_effect_free():
    points = replay([Candle(1, 100, 101, 99, 100), Candle(2, 100, 103, 100, 102), Candle(3, 102, 102, 101, 101)])
    assert [p.direction for p in points] == ["FLAT", "UP", "DOWN"]
    assert points[1].return_pct == 2.0
    assert points[2].return_pct < 0


def test_summary():
    points = replay([Candle(1, 100, 100, 100, 100), Candle(2, 100, 100, 100, 105)])
    result = summary(points)
    assert result["count"] == 2
    assert result["start"] == 100
    assert result["end"] == 105
    assert result["net_return_pct"] == 5.0
    assert result["up_bars"] == 1


def test_expected_move_treats_iv_as_percentage():
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    move = expected_move_value(25000, 10.0, "2026-09-11", now)
    assert move is not None
    assert round(move, 2) == 346.21


def test_expected_move_rejects_missing_or_invalid_inputs():
    assert expected_move_value(0, 10.0) is None
    assert expected_move_value(25000, 0) is None
