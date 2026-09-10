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
The Market Intelligence page uses a compact **Execution Plan · Read Only** card on the left of the priority row, with the **Live P&L Monitor directly to its right**. A second two-column row now places the full **Institutional Signal Engine** on the left and **Risk & Final Decision** on the right, instead of stacking those two panels vertically. The paper monitor retains all existing live telemetry: trade number, direction/strategy, strike and color-coded CE/PE badge, quantity/lots, entry/current premium, invested amount, live P&L/P&L%, movement direction and percentage, spot SL/target, MFE/MAE, mark timestamp and explicit read-only execution state. CE uses a green/teal visual treatment and PE uses a red visual treatment. When no paper trade is active, the monitor shows the current Brain option candidate and WAIT_FOR_TRIGGER state without fabricating a position or P&L.

The alignment change is presentation-only: no decision, risk, execution, paper-trade, learning or data-source logic was changed, and no monitor content was removed.

### Market Intelligence live transport + UI recovery — 2026-09-11
The production Market Intelligence page was observed remaining on `Connecting…` with all intelligence cards at their placeholders, and its navigation drawer toggle did not have a click handler. The UI was hardened without changing Brain/trading logic: the navigation drawer now opens/closes and routes to Raw Data and Backtest; the current screen is marked active; live rendering normalizes expected array fields before rendering, surfaces client render errors instead of silently swallowing them, retries `/api/v1/market` periodically, and keeps the `/ws/market` stream as a live transport. The backend live-market transport was already hardened to prefer the cached snapshot. Real trading remains disabled/read-only.

### Market Intelligence live-stream fix — 2026-09-10
The existing Market Intelligence page was blank because its browser WebSocket client connected to `/ws`, while the backend exposes the live market WebSocket at `/ws/market`. `apps/api/src/quantnifty/web/intelligence.html` was corrected to use `/ws/market`, display live-stream errors, reconnect after disconnects, and retry the initial `/api/v1/market` fetch so transient startup/cache timing does not leave the page blank. This is a UI transport/reliability fix only; no trading or Brain decision logic was changed.

## AI decision engine — incremental learning — 2026-09-11
The existing Adaptive Brain has now been connected to **same-day closed paper outcomes** at runtime rather than waiting exclusively for the next after-market policy artifact.

- `learning_store.py` now assigns event days using the **Asia/Kolkata trading day**, preventing UTC-date rollover from mixing two IST sessions.
- Learning event IDs now include trade/lifecycle identity when available, preventing an OPEN and CLOSED outcome at the same timestamp from colliding in durable storage.
- `research_brain.strategy_selector()` can rebuild a lightweight runtime Adaptive memory from only the current IST day's durable `CLOSED` paper outcomes.
- The runtime memory is enabled only when the final decision is running in **LIVE mode**. Replay/backtest/research modes explicitly do not enable this runtime memory path, preventing historical/replay outcomes from leaking into live Adaptive learning.
- The runtime memory feeds `adaptive_day_policy()` on subsequent live decisions, so completed same-day outcomes can influence later decisions incrementally.
- A validated prior-day future-safe policy remains the starting policy until same-day outcome evidence exists; once same-day evidence exists, the live selector uses the current-day adaptive memory rather than blindly overriding it with the stale prior-day policy.
- The Intelligence page's institutional/risk/execution stack now uses the **adaptive** decision path rather than a separate hard-coded directional path, keeping the visible decision stack aligned with the actual Adaptive Brain.
- `decision_intelligence()` now propagates its explicit `mode` into the adaptive final-decision stack, so any replay/research caller cannot accidentally fall back to LIVE-mode same-day learning.
- Counterfactual research outcomes remain research-only and are not inserted into live Adaptive memory.
- No historical recordings, `data_Review.txt`, or old replay evidence are used for this runtime learning path.
- Real-money execution remains disabled/read-only.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Risk -> FinalDecision -> ExecutionPlan -> Paper Outcome -> Same-Day Adaptive Memory -> Learning Store -> After-Market Research Policy`

Core ownership: `main.py`, `institutional_engine.py`, `research_brain.py`, `session_policy.py`, `decision_validation.py`, `replay.py`, `backtest.py`, `recording_loader.py`, `recording_api.py`, `adaptive_learning.py`, `learning_store.py`, `after_market_lab.py`, `after_market_scheduler.py`, `paper_trade_tracker.py`, `live_paper_manager.py`, `scenario_engine.py`, `research_strategy_runner.py`, `adaptive_policy.py`, `policy_runtime.py`, `paper_ledger_api.py`, and `web/*` UI.

## Paper ledger
`/api/v1/paper/ledger?day=YYYY-MM-DD` is read-only and exposes closed trades, same-day open positions, dynamic marks, realized/unrealized/total P&L, decision summary, stale-open diagnostics and `overnight_carry=false`. Paper entries contain complete Brain/risk/entry/exit evidence, MFE/MAE and explicit reasons. No real orders are submitted.

## UI acceptance criteria
- Session/read-only status and selected IST day.
- KPI cards: Brain decisions, approved, blocked, actual paper trades, open positions, winners, losers, win rate, realized P&L, unrealized P&L, total/net P&L.
- Trade table with trade ID, entry/exit time, direction, strategy/sub-strategy, option symbol/strike/side, quantity, entry/exit price, exit reason, result and P&L.
- Open positions with live mark, mark source/timestamp, unrealized P&L/%.
- **Live Trading Signal · Paper Monitor:** active trade number, direction, strategy, strike/option side, quantity/lots, entry/current mark, invested amount, movement, premium P&L, P&L%, spot SL/target, MFE/MAE and mark timestamp.
- **Decision-first layout:** Execution Plan is compact on the left of the priority row and Live P&L Monitor is directly on its right; Institutional Signal Engine and Risk & Final Decision form a second side-by-side row, with Institutional Signal Engine on the left and Risk & Final Decision on the right.
- **Color-coded option side:** PE is red, CE is green/teal wherever an option side is shown in the execution/P&L views.
- Expandable trade detail with scenario, Brain rationale/evidence, confidence, Adaptive regime/readiness/reason, risk gates/approval, MFE/MAE, exit context/reason and P&L basis.
- Decision timeline that clearly distinguishes actual trades from non-trade decisions and never presents counterfactual research as trades.
- No order-placement controls.

## Validation — completed for current deployment
The final source head deployed to Render is commit `866b39c7295d01bd9895dff2237a3d961be61c4d` via deployment `dep-dahing6q1p3s73dnu3e0`, which reached `live` successfully.

GitHub CI run `34536375379` completed successfully: compile passed and the complete `apps/api/tests` suite passed (**108 passed**). The same source head also passed the production evidence workflow, backtest-gate evidence, live-validation harness, paper-ledger evidence, and liveness wake workflows. The production evidence run included authenticated live-market/historical-replay checks and a browser E2E against production.

Render runtime evidence after deployment confirms PostgreSQL learning durability, `LIVE_PROVIDER` snapshot integrity, `/api/v1/paper/signal` availability, and `trading=DISABLED`. The service started cleanly and reported the primary production URL. The live WebSocket `/ws/market` was accepted in production evidence; older `/ws` 403 entries belong to stale clients before the current client fix and are not the current frontend transport.

Validation now covers:
- `/api/v1/market` live/cached transport.
- `/api/v1/paper/signal` read-only paper telemetry.
- `/api/v1/status` learning durability and `trading=DISABLED`.
- Same-day Adaptive learning, IST session boundaries, duplicate lifecycle identity, non-LIVE isolation, and explicit Intelligence mode propagation.
- Production browser E2E for the Intelligence and Backtest surfaces.
- Replay/backtest protection from same-day live Adaptive memory.
- No counterfactual/replay outcome entering live Adaptive memory.
- Temporary live-transport repair automation removed after the source-level fix.
- Python bytecode artifacts removed from tracking and ignored through `.gitignore`.

Remaining live-session validation is **operational rather than code-pending**: a real same-day paper trade must close during an actual IST session so the durable outcome and subsequent same-day adaptive update can be observed end-to-end. This is not a reason to enable real trading; broker execution remains disabled.

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts.
