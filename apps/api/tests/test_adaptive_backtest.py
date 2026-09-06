from __future__ import annotations

from quantnifty.backtest import BacktestConfig, run_backtest
from quantnifty.institutional_engine import final_decision


def bearish_snapshot(spot: float, option: float) -> dict:
    return {
        "timestamp": "2026-09-01T09:15:00+00:00",
        "spot": spot,
        "bias": "BEARISH",
        "confidence": 80,
        "liquidity_score": 90,
        "data_integrity": "LIVE_PROVIDER",
        "option_chain": [{
            "strike": 25000, "side": "PE", "security_id": "PE1", "trading_symbol": "NIFTYPE",
            "last_price": option, "bid": option - 0.5, "ask": option + 0.5, "oi": 1000, "previous_oi": 1000,
            "volume": 5000,
        }],
        "strike_selection": [{"strike": 25000, "side": "PE", "security_id": "PE1"}],
        "expected_move": {"move": 100, "lower": spot - 100, "upper": spot + 100},
        "gamma_flip": 25100,
        "gex": -100,
        "dex": -100,
        "atm_iv": 10,
        "iv_skew": 0,
        "expiry": "2026-09-10",
        "intelligence": {"market_state": {"state": "TREND_DOWN"}},
    }


def test_adaptive_final_decision_uses_regime_and_can_select_bearish():
    result = final_decision(bearish_snapshot(25000, 100), None, "adaptive", "BACKTEST")
    assert result["strategy"] == "adaptive"
    assert result["signal"]["adaptive"]["selected_strategy"] == "directional"
    assert result["signal"]["adaptive"]["preferred_direction"] == "BEARISH"
    assert result["signal"]["direction"] == "BEARISH"
    assert result["risk"]["strategy"] == "adaptive"
    assert result["risk"]["approved"] is True
    assert result["execution_plan"]["instrument"]["side"] == "PE"
    assert result["trading"] == "DISABLED"


def test_adaptive_backtest_mode_is_supported():
    first = bearish_snapshot(25000, 100)
    second = bearish_snapshot(24900, 120)
    second["timestamp"] = "2026-09-01T09:16:00+00:00"
    result = run_backtest([first, second], "adaptive", BacktestConfig(lot_size=1, fixed_cost=0, slippage_bps=0, max_hold_bars=1))
    assert result["status"] == "OK"
    assert result["strategy"] == "adaptive"
    assert result["lookahead_free"] is True
    assert result["orders_placed"] == 0
