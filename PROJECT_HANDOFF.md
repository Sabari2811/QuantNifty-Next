# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-10  
**Branch:** `main`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production:** https://quantnifty-api.onrender.com  
**Backtest:** https://quantnifty-api.onrender.com/backtest  
**Execution:** READ-ONLY; no real orders; `trading=DISABLED`.

## Current UI work
The operator UI is being extended to expose the already-implemented read-only paper ledger and decision-event data: today's Brain decisions, actual paper trades, open positions, entry/exit evidence, scenario/rationale, exit reasons, and realized/unrealized/total P&L. Counterfactual research remains separate from actual paper trades.

## Product plan
QuantNifty-Next is a **Live Adaptive Brain + After-Market Research Lab**. Live decisions use only data available at decision time. Adaptive Brain runs 09:20–15:15 IST; 15:15–15:30 IST permits only already-produced live CAS `cas_reentry`; 15:30 IST closes all paper positions with `SESSION_CLOSE`. No overnight paper positions. Learning is only from current/future live provider observations and same-day stored live observations. Historical recordings and `data_Review.txt` are replay/reference only and never seed or train live Adaptive memory/policy.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Risk -> FinalDecision -> ExecutionPlan -> Paper Outcome -> Learning Store`.
Core ownership includes `main.py`, `institutional_engine.py`, `research_brain.py`, `session_policy.py`, `decision_validation.py`, `replay.py`, `backtest.py`, `recording_loader.py`, `recording_api.py`, `learning_store.py`, `after_market_lab.py`, `after_market_scheduler.py`, `paper_trade_tracker.py`, `live_paper_manager.py`, `scenario_engine.py`, `research_strategy_runner.py`, `adaptive_policy.py`, `policy_runtime.py`, `paper_ledger_api.py`, and `web/*` UI. FinalDecision is authoritative; Risk owns permission; ExecutionPlan never submits orders.

## Strategy universe
`directional`, `gamma_blast`, `early_accumulation`, `transition`, `range`, `breakout_watch`, `standby`, `cas_reentry`, `adaptive`. Live API remains intentionally restricted to `directional`, `gamma_blast`, and `adaptive`; after-market research covers the research universe.

## Storage / paper lifecycle
Production PostgreSQL uses DATABASE_URL/QUANTNIFTY_DATABASE_URL with TLS `sslmode=require`; JSONL is fallback for local/testing. Paper trade records contain trade ID, strategy, direction, entry time/spot, option instrument/security ID/symbol/strike/side, entry price/source, quantity/lot size, Brain signal/confidence/evidence/rationale, Adaptive regime/strategy/readiness/reason, risk approval/gates/reasons, MFE/MAE, exit time/spot/option price/source, exit reason, exit Brain/risk context, realized/gross P&L, P&L basis, read-only marker and day. Prior-day stale OPEN rows are reconciled against that trade day's last stored LIVE_PROVIDER snapshot; no overnight carry.

## Dynamic P&L ledger
`/api/v1/paper/ledger?day=YYYY-MM-DD` is read-only. It exposes closed trades, same-day open positions, dynamic executable-side marks, unrealized P&L, realized P&L, total/net P&L, decision summary, stale-open diagnostic and `overnight_carry=false`. No broker charges are fabricated.

## UI requirement
The operator UI must provide a Today/Paper Trading & Brain Decisions experience backed directly by the canonical ledger/decision APIs. It must show session/read-only status; KPI cards for decisions/approvals/blocks/trades/open positions/winners/losers/win rate/realized/unrealized/total P&L; a trade table; open-position live marks; expandable trade detail with scenario, Brain rationale/evidence, Adaptive regime/readiness, risk gates/approval, MFE/MAE, exit context/reason and P&L basis; and a decision timeline clearly distinguishing decisions that did not become trades. No order-placement controls and no counterfactual research presented as actual trades.

## Validation
Live-session evidence for full-session deduplication, state transitions, post-recovery ledger reconciliation, after-market research persistence, and restart behavior remains pending the 2026-09-11 live session. UI implementation must be verified in production after deployment. Real-money execution remains disabled.

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts.
