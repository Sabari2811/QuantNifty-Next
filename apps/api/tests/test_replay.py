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
