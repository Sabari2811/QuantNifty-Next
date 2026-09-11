from quantnifty.recording_api import _trade_audit


def _snapshot(ts="2026-09-11T03:52:10+00:00"):
    return {
        "timestamp": ts,
        "spot": 23254.85,
        "expiry": "2026-09-15",
        "pcr": 1.08,
        "call_oi": 1000,
        "put_oi": 1080,
        "call_oi_change": -25,
        "put_oi_change": 60,
        "gex": -123.4,
        "dex": -456.7,
        "vanna_proxy": 8.2,
        "iv_skew": 1.7,
        "atm_iv": 12.4,
        "gamma_flip": 23300,
        "gamma_walls": [{"side": "PE", "strike": 23400, "exposure": 91}],
        "max_pain": 23300,
        "expected_move": {"move": 150, "lower": 23104.85, "upper": 23404.85},
        "support": 23200,
        "resistance": 23300,
        "structure": "BELOW_GAMMA_FLIP",
        "dealer_flow": "PUT_SUPPORT",
        "liquidity_score": 82,
        "bullish_score": 35,
        "bearish_score": 65,
        "bias": "BEARISH",
        "confidence": 65,
        "rationale": ["positive put OI flow"],
        "data_integrity": "LIVE_PROVIDER",
        "rows": 82,
        "strike_selection": [{"strike": 23400, "side": "PE", "score": 91.2}],
        "option_chain": [{"strike": 23400, "side": "PE", "delta": -0.61, "gamma": 0.0002, "iv": 13.1, "oi": 500}],
    }


def _decision(ts="2026-09-11T03:52:10+00:00"):
    return {
        "timestamp": ts,
        "strategy": "adaptive",
        "mode": "LIVE",
        "signal": {
            "direction": "BEARISH",
            "confidence": 72,
            "liquidity": 82,
            "evidence": ["OI_FLOW", "GEX", "VWAP", "EMA"],
            "rationale": ["early accumulation confirmation"],
            "adaptive": {
                "regime": "TREND",
                "selected_strategy": "early_accumulation",
                "reason": "EARLY_ACCUMULATION_CONFIRMATION",
            },
        },
        "risk": {
            "approved": True,
            "gates": {"direction": True, "confidence": True, "liquidity": True, "data_integrity": True},
            "reasons": [],
        },
        "execution_plan": {
            "entry": "EARLY_ACCUMULATION_CONFIRMATION",
            "entry_mode": "TRIGGERED",
            "stop_points": 81.5,
            "target_points": 161.66,
            "risk_reward": 1.98,
            "instrument": {"trading_symbol": "NIFTY263400SEPPE", "strike": 23400, "side": "PE", "security_id": "x"},
            "exit_policy": {"session_close": True},
        },
    }


def _outcome(ts="2026-09-11T03:52:10+00:00"):
    return {
        "trade_id": "T-1",
        "status": "CLOSED",
        "entry_timestamp": ts,
        "entry_spot": 23254.85,
        "entry_price": 189.35,
        "entry_price_source": "ASK_THEN_LAST_THEN_BID",
        "direction": "BEARISH",
        "strategy": "early_accumulation",
        "entry_trigger": "EARLY_ACCUMULATION_CONFIRMATION",
        "entry_mode": "TRIGGERED",
        "quantity": 65,
        "instrument": {"trading_symbol": "NIFTY263400SEPPE", "strike": 23400, "side": "PE", "security_id": "x"},
        "entry_risk": {"stop_points": 81.5, "target_points": 161.66, "risk_reward": 1.98, "stop_spot": 23336.35, "target_spot": 23093.19},
        "risk_anchor": "ENTRY_SPOT_IMMUTABLE",
        "exit_policy": {"session_close": True},
        "exit_timestamp": "2026-09-11T09:30:00+00:00",
        "exit_spot": 23180,
        "exit_price": 210,
        "exit_price_source": "BID_THEN_LAST_THEN_ASK",
        "exit_reason": "SESSION_CLOSE",
        "realized_pnl": 1343.25,
        "pnl_basis": "OPTION_PREMIUM_WHEN_AVAILABLE_ELSE_SPOT_PROXY",
        "read_only": True,
    }


def test_trade_audit_joins_exact_entry_timestamp_without_hindsight():
    ts = "2026-09-11T03:52:10+00:00"
    audit = _trade_audit(_outcome(ts), {ts: _snapshot(ts)}, {ts: _decision(ts)})
    assert audit["completeness"]["complete"] is True
    assert audit["entry"]["premium"] == 189.35
    assert audit["market_evidence"]["gex"] == -123.4
    assert audit["market_evidence"]["dex"] == -456.7
    assert audit["market_evidence"]["pcr"] == 1.08
    assert audit["market_evidence"]["strike_selection"][0]["strike"] == 23400
    assert audit["decision"]["checklist"]["risk_approved"]["passed"] is True
    assert audit["decision"]["checklist"]["confidence_threshold"]["passed"] is True
    assert audit["exit"]["premium"] == 210


def test_trade_audit_marks_legacy_missing_snapshot_instead_of_reconstructing():
    ts = "2026-09-11T03:52:10+00:00"
    audit = _trade_audit(_outcome(ts), {}, {ts: _decision(ts)})
    assert audit["completeness"]["complete"] is False
    assert "decision_time_snapshot" in audit["completeness"]["missing"]
    assert audit["market_evidence"] == {}
    assert audit["learning"]["historical_learning_used_for_entry"] is False
