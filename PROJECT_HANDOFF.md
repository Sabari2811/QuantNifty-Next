# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-10  
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

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Risk -> FinalDecision -> ExecutionPlan -> Paper Outcome -> Learning Store`

Core ownership: `main.py` provider/analytics/API/live refresh; `institutional_engine.py` signal/risk/FinalDecision/ExecutionPlan; `research_brain.py` adaptive regimes/selection/accumulation/exits; `session_policy.py` session/CAS; `decision_validation.py` validation; `replay.py`/`backtest.py` deterministic research; `historical.py` normalization/provenance diagnostics only; `recording_loader.py`/`recording_api.py` recording/replay; `adaptive_learning.py` policy helpers; `learning_store.py` durable events; `after_market_lab.py` and `after_market_scheduler.py` daily research; `paper_trade_tracker.py` and `live_paper_manager.py` read-only outcome lifecycle; `scenario_engine.py`; `research_strategy_runner.py`; `adaptive_policy.py`; `policy_runtime.py`; `paper_ledger_api.py` read-only ledger; `web/*` UI.

Governance: FinalDecision is authoritative; Risk owns permission; ExecutionPlan never submits orders; actual and counterfactual experience remain separate; replay reuses the canonical pipeline; time remains deterministic/injectable.

## Strategy universe
`directional`, `gamma_blast`, `early_accumulation`, `transition`, `range`, `breakout_watch`, `standby`, `cas_reentry`, `adaptive`.

Live API remains intentionally restricted to `directional`, `gamma_blast`, and `adaptive`. After-market research covers the research universe through the canonical Adaptive/FinalDecision/Risk pipeline.

## Learning / storage
PostgreSQL is the production durability target through `DATABASE_URL`/`QUANTNIFTY_DATABASE_URL`, with TLS explicitly required (`sslmode=require`) and JSONL fallback for local/testing. Render resource: `quantnifty-learning` in Singapore. No credentials are committed.

Live refresh persists immutable market snapshots and a read-only paper lifecycle. Learning remains live/same-day only.

## Paper trade lifecycle — finalized 2026-09-10
Every Brain-approved paper entry now persists enough evidence to reconstruct the trade without relying on counters:

- `trade_id`, strategy, direction, entry timestamp and entry NIFTY spot.
- Entry option instrument: security ID, trading symbol, strike, side/type.
- Entry price, price source (`ASK_THEN_LAST_THEN_BID`) and quantity/lot size.
- Full entry Brain decision context: signal direction/confidence/evidence/rationale, Adaptive regime/strategy/readiness/reason, risk approval, risk gates and risk reasons.
- MFE/MAE tracking.
- Exit timestamp, exit NIFTY spot, exit option price and price source.
- Explicit exit reason plus exit-time Brain signal/risk context.
- `realized_pnl`/`gross_pnl_proxy`, P&L basis, read-only execution marker and trading-day field.

Paper entries are read-only simulations only. No broker order is submitted.

### Same-day rule
`session_close_required()` now treats **15:30 IST and later** as a mandatory close boundary. Active paper positions are closed by the live manager at the first live snapshot at/after that boundary with `SESSION_CLOSE`. If a restored active position is detected from a different IST day, it is not restored as an active current-day position; an active day can therefore never intentionally carry forward.

If a runtime ever encounters a timestamp from a different trading day while an active paper position exists, the lifecycle uses `OVERNIGHT_GUARD` rather than silently continuing the position.

## Dynamic P&L ledger — finalized 2026-09-10
`/api/v1/paper/ledger?day=YYYY-MM-DD` is read-only and now exposes both realized and live mark-to-market state.

- `ledger`: closed trades for the selected IST day.
- `open_positions`: currently open same-day paper positions.
- Each open position is marked from the latest stored `LIVE_PROVIDER` snapshot using the executable sell-side mark: bid, then last, then ask.
- `unrealized_pnl` changes as live option prices move; `unrealized_pnl_pct`, mark price/source and mark timestamp are exposed.
- `summary.realized_pnl` = closed-trade P&L.
- `summary.unrealized_pnl` = current open-position mark-to-market P&L.
- `summary.total_pnl` / `net_pnl` = realized + unrealized.
- Closed-trade option P&L is `(exit_price - entry_price) * quantity` when both option prices are available; otherwise the existing directional spot proxy is used.
- Broker charges are not fabricated.
- Legacy same-day outcome rows without the new explicit `day` field are still recoverable by their entry/exit timestamps.
- The ledger also exposes the same-day Brain decision summary and a `stale_open_positions` diagnostic for any older unresolved OPEN record.
- `overnight_carry` is explicitly `False` in the API contract.

## Decision-event model — finalized
**Snapshots and decision events are separate concepts.** Every live provider refresh continues to be processed and may be stored as a snapshot. The durable `decisions` ledger emits only when the actionable state changes, instead of recording an identical decision on every polling cycle.

`decision_event_gate.py` owns the event signature. The signature includes market direction, strategy, risk approval state, selected sub-strategy and session phase. Repeated identical states are not persisted as new decision events. State transitions are persisted. The gate does not suppress live analytics, risk evaluation or paper-position management.

The gate is restart-safe for the same IST trading day: production startup restores the latest same-day persisted decision signature before live polling resumes. Runtime emitted/suppressed counters make deduplication auditable.

## After-market research
After close, research runs on the completed same-day stored live data only, persists scenarios and a future-safe policy candidate, and marks a day complete only after successful research persistence. Failed/`NO_DATA` runs remain retryable. Historical recordings never become live Adaptive training data.

## Completed / implemented
- Canonical decision/risk/execution architecture.
- Adaptive selector/regimes, accumulation and exits.
- Session/CAS policy and boundary tests.
- Data/decision validation.
- Replay/backtest consistency.
- Live-only Adaptive learning; legacy historical-learning dependency removed.
- PostgreSQL TLS durability support.
- After-market lab/scheduler with retryable completion state.
- Paper outcome tracker, MFE/MAE and restart recovery.
- Scenario extraction and future-safe policy persistence/loading.
- Production runtime observability and PostgreSQL diagnostics.
- Read-only paper ledger API and aggregation tests.
- Decision-event deduplication and restart-safe same-day seeding.
- Market-session liveness wake/verification workflow for the free Render web service.
- **2026-09-10:** complete Brain paper-trade evidence persisted at entry/exit, quantity/lot sizing exposed, explicit entry/exit reasons and decision context persisted, dynamic open-position mark-to-market P&L added, realized + unrealized + total P&L aggregation added, and no-overnight contract added.

## Key implementation commits
- `00880f50c5184a8118316bc8414ca350c5108b1b` — market-session liveness wake/verification workflow.
- `569b6322fc5d231a35841c2cfa0b951399c35df0` — push-triggered liveness verification.
- `574990b0dd06604a42263e40cace5cb36355cde0` — production liveness state documentation.
- `a4c6edec90389f41778cd3958d279b3b3876a20c` — paper session boundary/trading-day helpers.
- `907d934ecda4c9713084ff494f83e20b8bab25e9` — complete Brain paper-trade evidence and quantity persistence.
- `ce3a33d0ec7b9ad5f382f5b8987b43f6c677a2c8` — dynamic open-position P&L ledger.
- `12accb2134999cf8c3cb9cfb253d4141b54a787d` — paper lifecycle/ledger regression tests.

## Validation checklist
1. Full live-session repeated-state decision dedup — pending full-session evidence.
2. Direction/approval/strategy/sub-strategy/session transitions — pending full-session evidence.
3. **Paper trade lifecycle and P&L:** implementation complete; production reconciliation must be re-observed after deployment, including a 1-lot validation scenario.
4. Automatic same-day after-market research completion/persistence — pending final post-session evidence.
5. Restart/deploy during active trading day does not duplicate the latest same-day decision signature — implementation/evidence present; final active-day observation remains part of the gate.
6. **Liveness workflow:** verified successful in GitHub Actions run `34463616621` on commit `574990b0...`; production wake path is PASS.
7. **Dynamic P&L contract:** unit/regression coverage added; production `/api/v1/paper/ledger` must be observed after the new deployment to close the runtime evidence item.

## Live evidence / operational state
Production has previously shown `LIVE_PROVIDER`, 82 option-chain rows, PostgreSQL durability, decision-event gate activity, and `trading=DISABLED`. During the 2026-09-10 live session the paper manager was observed `OPEN`, later returned to `IDLE`, and persisted outcome count increased; exact historical trade rows were not previously exposed in runtime logs, which motivated this implementation.

The Render free service had an idle shutdown at 07:33:18Z; the scheduled liveness workflow was added and later verified successfully. A fresh production process started after the implementation commits.

## Non-negotiable rules
- Never commit API tokens/secrets or `data_Review.txt`.
- Never use future outcomes in live decisions.
- Never use historical recordings for live Adaptive memory/policy.
- Never represent counterfactual research as actual trading.
- Never submit real orders; execution remains READ-ONLY.
- No overnight paper positions.
- Do not touch `data/instruments/fno.csv` or unrelated untracked audit/backup artifacts.
