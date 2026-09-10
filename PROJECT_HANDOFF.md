# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-11  
**Branch:** `main`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production:** https://quantnifty-api.onrender.com  
**Backtest:** https://quantnifty-api.onrender.com/backtest  
**Execution:** READ-ONLY; no real orders; `trading=DISABLED`.

## Product plan
QuantNifty-Next is a **Live Adaptive Brain + After-Market Research Lab**.

- Live decisions use only data available at decision time.
- Adaptive Brain: 09:20–15:15 IST.
- 15:15–15:30 IST: only already-produced live CAS may authorize `cas_reentry`.
- 15:30 IST: new decisions stop and all open paper trades must close as `SESSION_CLOSE`.
- No paper position may be carried into the next IST trading day.
- Learn only from `LIVE_PROVIDER` current/future observations and `STORED_DAY` same-day completed live observations.
- Historical learning/bootstrap/performance gates are removed completely.
- `data_Review.txt` and old recordings are replay/reference evidence only and must never seed, train, promote or influence live Adaptive memory/policy.
- After close, replay the stored live day only, test the research universe, extract scenarios and persist a future-safe policy candidate.

## UI status — 2026-09-11
The Market Intelligence page includes a **Live Trading Signal · Paper Monitor** section. It is read-only and shows the actual active Brain paper trade when one exists: trade number for the day, direction, strategy, strike/option side, quantity/lots, entry premium, current live mark and source, invested amount, live premium P&L/P&L%, movement direction and favorable movement, Brain spot-level SL/target, MFE/MAE, and read-only execution status. When no paper position is active, it shows today's paper-trade count plus the current Brain direction/strategy/risk-gate state.

The telemetry is served by `/api/v1/paper/signal` and refreshes every 5 seconds in the UI. P&L is based on the same option-premium mark hierarchy used by the paper lifecycle (BID -> LAST -> ASK); invested amount is entry premium × quantity. The monitor does not create or modify trades.

### Decision-first + live P&L layout — 2026-09-11
The Market Intelligence page now uses a compact **Execution Plan · Read Only** card on the left of the priority decision row, with the **Institutional Signal Engine** beside it. The **Risk & Final Decision** panel remains immediately below. The paper section has been upgraded to a larger **Live P&L Monitor** with live trade number, direction/strategy, strike and color-coded CE/PE badge, quantity/lots, entry/current premium, invested amount, live P&L/P&L%, movement direction and percentage, spot SL/target, MFE/MAE, mark timestamp and explicit read-only execution state. CE uses a green/teal visual treatment and PE uses a red visual treatment. When no paper trade is active, the monitor shows the current Brain option candidate and WAIT_FOR_TRIGGER state without fabricating a position or P&L.

No decision, risk, execution, paper-trade, learning or data-source logic was changed by this UI work.

### Market Intelligence live-stream fix — 2026-09-10
The existing Market Intelligence page was blank because its browser WebSocket client connected to `/ws`, while the backend exposes the live market WebSocket at `/ws/market`. `apps/api/src/quantnifty/web/intelligence.html` was corrected to use `/ws/market`, display live-stream errors, reconnect after disconnects, and retry the initial `/api/v1/market` fetch so transient startup/cache timing does not leave the page blank. This is a UI transport/reliability fix only; no trading or Brain decision logic was changed.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Risk -> FinalDecision -> ExecutionPlan -> Paper Outcome -> Learning Store`

Core ownership: `main.py`, `institutional_engine.py`, `research_brain.py`, `session_policy.py`, `decision_validation.py`, `replay.py`, `backtest.py`, `recording_loader.py`, `recording_api.py`, `adaptive_learning.py`, `learning_store.py`, `after_market_lab.py`, `after_market_scheduler.py`, `paper_trade_tracker.py`, `live_paper_manager.py`, `scenario_engine.py`, `research_strategy_runner.py`, `adaptive_policy.py`, `policy_runtime.py`, `paper_ledger_api.py`, and `web/*` UI.

## Paper ledger
`/api/v1/paper/ledger?day=YYYY-MM-DD` is read-only and exposes closed trades, same-day open positions, dynamic marks, realized/unrealized/total P&L, decision summary, stale-open diagnostics and `overnight_carry=false`. Paper entries contain complete Brain/risk/entry/exit evidence, MFE/MAE and explicit reasons. No real orders are submitted.

## UI acceptance criteria
- Session/read-only status and selected IST day.
- KPI cards: Brain decisions, approved, blocked, actual paper trades, open positions, winners, losers, win rate, realized P&L, unrealized P&L, total/net P&L.
- Trade table with trade ID, entry/exit time, direction, strategy/sub-strategy, option symbol/strike/side, quantity, entry/exit price, exit reason, result and P&L.
- Open positions with live mark, mark source/timestamp, unrealized P&L/%.
- **Live Trading Signal · Paper Monitor:** active trade number, direction, strategy, strike/option side, quantity/lots, entry/current mark, invested amount, movement, premium P&L, P&L%, spot SL/target, MFE/MAE and mark timestamp.
- **Decision-first layout:** Execution Plan is compact on the left of the priority row, Institutional Signal Engine is beside it, and Risk & Final Decision follows immediately below.
- **Color-coded option side:** PE is red, CE is green/teal wherever an option side is shown in the execution/P&L views.
- Expandable trade detail with scenario, Brain rationale/evidence, confidence, Adaptive regime/readiness/reason, risk gates/approval, MFE/MAE, exit context/reason and P&L basis.
- Decision timeline that clearly distinguishes actual trades from non-trade decisions and never presents counterfactual research as trades.
- No order-placement controls.

## Validation
Latest UI code is committed on `main`. The change is presentation-only and keeps the existing `/api/v1/paper/signal` polling, `/ws/market` stream, and read-only paper lifecycle intact. Render manual deployment and live production validation are required before this UI commit is considered production-verified. After deployment, verify `/api/v1/paper/signal` returns successfully, the monitor renders on `/intelligence`, values update without page refresh, CE/PE colors are correct, the execution plan is compact on the left, and active paper trades show correct live mark/P&L. Full-session deduplication, state transitions, post-recovery ledger reconciliation, after-market research persistence and restart behavior remain pending the 2026-09-11 live session. Real-money execution remains disabled.

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts.
