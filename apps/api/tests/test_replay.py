from datetime import datetime, timezone

from quantnifty.main import analytics, expected_move_value, flatten_chain
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


def test_option_chain_normalization_preserves_provider_fields():
    payload = {"data": {"underlying_ltp": 24000, "strikes": {
        "24000": {
            "ce": {
                "security_id": "100", "trading_symbol": "NIFTY-24000-CE", "last_price": 120,
                "previous_close_price": 100, "oi": 1000, "previous_oi": 900, "volume": 5000,
                "top_bid_price": 119, "top_bid_quantity": 50, "top_ask_price": 121, "top_ask_quantity": 60,
                "iv": 10.5, "greeks": {"delta": 0.5, "gamma": 0.001, "theta": -8, "vega": 12},
            },
            "pe": {
                "security_id": "101", "trading_symbol": "NIFTY-24000-PE", "last_price": 110,
                "previous_close_price": 115, "oi": 1200, "previous_oi": 1300, "volume": 6000,
                "top_bid_price": 109, "top_bid_quantity": 70, "top_ask_price": 111, "top_ask_quantity": 80,
                "iv": 11.0, "greeks": {"delta": -0.5, "gamma": 0.001, "theta": -7, "vega": 12},
            },
        }
    }}}
    spot, rows = flatten_chain(payload)
    assert spot == 24000
    assert len(rows) == 2
    assert rows[0]["security_id"] == "100"
    assert rows[0]["theta"] == -8
    assert rows[1]["bid_qty"] == 70
    assert rows[1]["ask_qty"] == 80


def test_analytics_exposes_complete_ui_contract():
    rows = [
        {"strike": 23900.0, "side": "CE", "security_id": "1", "trading_symbol": "C", "last_price": 200,
         "previous_close": 190, "oi": 1000, "previous_oi": 900, "volume": 10000, "bid": 199, "bid_qty": 10,
         "ask": 201, "ask_qty": 10, "iv": 10, "delta": 0.55, "gamma": 0.001, "theta": -8, "vega": 10},
        {"strike": 23900.0, "side": "PE", "security_id": "2", "trading_symbol": "P", "last_price": 100,
         "previous_close": 105, "oi": 1200, "previous_oi": 1100, "volume": 12000, "bid": 99, "bid_qty": 10,
         "ask": 101, "ask_qty": 10, "iv": 11, "delta": -0.45, "gamma": 0.001, "theta": -7, "vega": 10},
    ]
    result = analytics(24000, rows, "2026-09-11")
    assert result["vanna_proxy"] != 0
    assert result["expected_move"]["lower"] < 24000 < result["expected_move"]["upper"]
    assert result["option_chain"] == rows
    assert result["option_chain"][0]["theta"] == -8
