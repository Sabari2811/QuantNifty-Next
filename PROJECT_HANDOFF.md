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
`session_close_required()` treats **15:30 IST and later** as a mandatory close boundary. Active paper positions are closed by the live manager at the first live snapshot at/after that boundary with `SESSION_CLOSE`. If a restored active position is detected from a different IST day, it is not restored as an active current-day position.

A startup recovery pass now reconciles any unresolved prior-day OPEN paper trade against the **last stored LIVE_PROVIDER snapshot from that trade's own day**, recording `SESSION_CLOSE_RECOVERY` and its realized P&L. This prevents stale OPEN rows from becoming next-day positions without inventing a next-day price. If a live runtime crosses a trading-day boundary while active, the lifecycle uses `OVERNIGHT_GUARD` rather than silently carrying the position.

## Dynamic P&L ledger — finalized 2026-09-10
`/api/v1/paper/ledger?day=YYYY-MM-DD` is read-only and exposes realized and live mark-to-market state.

- `ledger`: closed trades for the selected IST day.
- `open_positions`: currently open same-day paper positions.
- Each open position is marked from the latest stored `LIVE_PROVIDER` snapshot using the executable sell-side mark: bid, then last, then ask.
- `unrealized_pnl` changes as live option prices move; `unrealized_pnl_pct`, mark price/source and mark timestamp are exposed.
- `summary.realized_pnl` = closed-trade P&L.
- `summary.unrealized_pnl` = current open-position mark-to-market P&L.
- `summary.total_pnl` / `net_pnl` = realized + unrealized.
- Closed-trade option P&L is `(exit_price-entry_price)*quantity` when both option prices are available; otherwise the directional spot proxy is used.
- Broker charges are not fabricated.
- Legacy same-day outcome rows without the new explicit `day` field remain recoverable by entry/exit timestamps or event timestamp fallback.
- The ledger exposes the same-day Brain decision summary and `stale_open_positions` diagnostic.
- `overnight_carry` is explicitly `False`.

## Decision-event model — finalized
Snapshots and decision events are separate. Every live provider refresh continues to be processed/stored, while the durable decisions ledger emits only when the actionable state changes. `decision_event_gate.py` owns the signature across market direction, strategy, risk approval, selected sub-strategy and session phase. Restart-safe same-day seeding prevents duplicate latest signatures.

## After-market research
After close, research runs on completed same-day stored live data only, persists scenarios and a future-safe policy candidate, and marks a day complete only after successful research persistence. Failed/`NO_DATA` runs remain retryable. Historical recordings never become live Adaptive training data.

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
- Complete Brain paper-trade evidence, quantity/lot sizing, entry/exit reasons and decision context.
- Dynamic realized + unrealized + total P&L aggregation.
- Prior-day stale OPEN reconciliation at the prior session's last stored live snapshot.

## Key implementation commits
- `f7a536ab33a86eb72516d5e8800a8dfa38e8cef7` — legacy ledger rows recoverable by event timestamp fallback; deployed to production.
- `349ef05509d8c7390ff0a999edc8f5530d2badbb` — stale-lifecycle P&L diagnostic fix.
- `00880f50c5184a8118316bc8414ca350c5108b1b` — market-session liveness wake/verification workflow.
- `569b6322fc5d231a35841c2cfa0b951399c35df0` — push-triggered liveness verification.
- `574990b0dd06604a42263e40cace5cb36355cde0` — production liveness state documentation.
- `49e966a20e12393d3d63f2ca03c9fded7b9abe6e` — stale paper-position reconciliation at prior session close.

## Validation checklist
1. Full live-session repeated-state decision dedup — **pending tomorrow's full-session evidence**.
2. Direction/approval/strategy/sub-strategy/session transitions — **pending tomorrow's full-session evidence**.
3. **Paper trade lifecycle and P&L:** implementation complete; CI passed; production deployment is live; final post-recovery ledger response still needs a fresh production query during/after the next live session.
4. Automatic same-day after-market research completion/persistence — **pending next post-session evidence**.
5. Restart/deploy during active trading day does not duplicate latest same-day decision signature — implementation/evidence present; tomorrow's active-session observation will be the final gate.
6. **Liveness workflow:** previously verified successful in GitHub Actions run `34463616621`.
7. **Dynamic P&L contract:** CI and production contract evidence passed previously; post-`f7` production reconciliation remains an explicit next-session evidence gate.

## Production evidence
Before the stale-recovery redeploy, the 2026-09-10 production paper ledger returned 38 closed paper trades, realized P&L **-₹13.90**, unrealized P&L **₹0.00**, total/net P&L **-₹13.90**, 38 option-premium P&L trades, 87 same-day decision events (47 approved, 40 blocked), spot 23,477.8, trading disabled, and 1 unresolved prior-day OPEN lifecycle row. That result is retained as historical evidence only; it is not claimed as the post-`f7` reconciliation.

## Current production state
The `f7a536ab` Render deployment is **LIVE**. Post-deploy runtime logs confirm PostgreSQL reachable, `LIVE_PROVIDER` cached with 82 rows, snapshots continuing to increase, decision-event gate enabled, and `trading=DISABLED`. No post-deploy paper-ledger request has yet been observed, so no post-`f7` ledger numbers are claimed.

## Tomorrow live-validation plan — 2026-09-11
Use the live market session strictly as **paper/read-only validation**:

- 09:15–09:20 IST: verify service wake, provider connectivity, DB durability and trading-disabled state.
- 09:20–15:15 IST: observe Brain decisions, validation gates, strategy/direction/sub-strategy transitions, decision-event deduplication, paper entries, exits and dynamic P&L.
- 15:15–15:30 IST: verify CAS-only re-entry policy.
- 15:30 IST: verify all paper positions are closed with no overnight carry.
- After close: verify same-day after-market research, scenario persistence and future-safe policy candidate persistence.
- Capture production ledger/P&L evidence and compare actual paper outcomes with Brain decision events; never treat counterfactual/research decisions as trades.

No real-money execution will be enabled during this validation.

## Non-negotiable rules
- Never commit API tokens/secrets or `data_Review.txt`.
- Never use future outcomes in live decisions.
- Never use historical recordings for live Adaptive memory/policy.
- Never represent counterfactual research as actual trading.
- Never submit real orders; execution remains READ-ONLY.
- No overnight paper positions.
- Do not touch `data/instruments/fno.csv` or unrelated untracked audit/backup artifacts.
