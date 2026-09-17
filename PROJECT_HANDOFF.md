# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-17  
**Branch:** `main`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production:** https://quantnifty-api.onrender.com  
**Backtest:** https://quantnifty-api.onrender.com/backtest  
**Execution:** READ-ONLY; no real orders; `trading=DISABLED`.

## Product and safety contract
QuantNifty-Next is a Live Adaptive Brain + After-Market Research Lab. Live decisions use only data available at decision time. Adaptive runtime is restricted to the live IST session; no overnight paper positions are allowed. Same-day Adaptive memory consumes only current-IST-day CLOSED outcomes in explicit LIVE mode. There is no historical learning/bootstrap/performance-gate path. Past live-session data is retained and accumulated; it is not deleted or used as a historical replay substitute. `data_Review.txt`, old recordings and external historical archives are replay/reference evidence only and never seed live Adaptive memory or policy. Real trading is permanently disabled.

Do not modify `QuantNifty`, `data/instruments/fno.csv`, or commit secrets.

## Render runtime / cost boundary
The application runtime window is **09:00-16:00 IST, Monday-Friday**. This intentionally includes 09:00-09:15 pre-market initialization and 15:30-16:00 post-market research. The live provider remains separately guarded to **09:15-15:30 IST**. The new `application_runtime_state()` / `is_application_runtime_window()` helpers in `apps/api/src/quantnifty/market_session.py` make this boundary explicit and add runtime state to the closed payload.

The production cost-saving design is: paid `quantnifty-api` compute active only during the 09:00-16:00 weekday window; paid `quantnifty-production` PostgreSQL remains available for durable learning, paper trades and research history. Application sleep alone does not stop paid Render compute; the Render service itself must be suspended/resumed. The required scheduler configuration is documented in `docs/RENDER_RUNTIME.md`. No Render API secret is committed.

Required QuantNifty-Next production resources:
- `quantnifty-api`: paid `0.5c-512mb` / Starter-equivalent compute.
- `quantnifty-production`: paid PostgreSQL for durable production state.
- Separate `QuantNifty` services/workers are unrelated and must not be enabled for this project.

Current Render integration cannot perform suspend/resume directly, so the final daily service lifecycle requires Render Dashboard/API scheduler configuration using a secret Render API key. The application code and exact IST/UTC schedule are now documented.

## Live paper risk
At entry the paper manager freezes entry spot, entry premium, selected instrument, trigger, stop/target points, R:R and exit policy. Option premium SL/target are delta-driven from the NIFTY-point risk budget using live option delta. New entries require valid delta. Existing legacy OPEN trades without delta evidence are not fabricated or rewritten. No real orders are submitted and no overnight paper positions are carried.

## Live entry scenarios
Entry-capable pathways: `EARLY_ACCUMULATION`, `DIRECTIONAL`, `NEGATIVE_GAMMA_EXPANSION`, `GAMMA_TRANSITION`, `CAS_REENTRY`. Liquidity-risk, positive-gamma range, compression and standby states are explicit NO_ENTRY states.

## Deterministic decision intelligence
QuantNifty's own deterministic intelligence is the authoritative decision layer; no external LLM/API is required. The live path is:

`LIVE_PROVIDER snapshot -> market-state/event detection -> move attribution + signal DNA + pressure map -> institutional signal -> risk gates -> read-only paper lifecycle -> same-day learning`

The decision layer combines the existing market-structure, OI, GEX/DEX, IV, expected-move, liquidity, scenario and institutional/risk engines. It can only produce read-only paper decisions and cannot submit broker orders. There is no Astra/OpenAI dependency, no API key requirement, and no external AI inference cost.

## Trade Audit
Read-only paper trade audit is available at `/trade-audit` with API `/api/v1/paper/trade-audit`. It joins durable outcomes to exact entry snapshots/decision timestamps without hindsight and marks incomplete legacy evidence instead of fabricating it.

## Live monitor trade history
The Market Brain screen now has a dedicated daily trade-history component inside the Active Paper Trade monitor. It reads the durable read-only paper ledger from `/api/v1/paper/ledger` rather than research data or the post-market lab.

For the **current open trade**, the monitor shows option premium entry -> current mark, live P&L, premium target/SL derived from the frozen entry delta/risk budget, current NIFTY spot, entry spot, spot movement, spot SL/target, entry time, mark time, instrument and read-only execution state. Exit is explicitly shown as `OPEN` until the paper lifecycle closes it.

For **previous completed trades today**, the monitor shows trade number, direction, strategy, option/strike, entry premium, exit premium, entry spot, exit spot, frozen NIFTY SL, frozen NIFTY target, realized P&L, exit reason, quantity and entry/exit times. The component refreshes every 5 seconds and uses only the current IST-day paper ledger.

The UI enhancement is implemented in `apps/api/src/quantnifty/web/intelligence.html`. The application now explicitly mounts `paper_ledger_api.py` from `main.py`, making the durable paper ledger available to the live monitor. This remains read-only and does not submit, modify or cancel broker orders.

## Paper-trade discrepancy guard and daily kill switch
The live monitor screenshot on 2026-09-17 showed **6 completed · 2 active** while only one active trade was rendered. This exposed a lifecycle-recovery edge case: `LivePaperManager._recover()` previously restored only the newest OPEN trade into memory while leaving an older OPEN lifecycle in the durable ledger. That could violate the intended one-position-at-a-time invariant across a service restart.

`live_paper_manager.py` now enforces a single-active invariant during recovery. If multiple current-day OPEN paper trades are found, the newest entry is retained and older orphaned OPEN trades are closed at the latest available snapshot with reason `MULTIPLE_ACTIVE_TRADE_GUARD`. This is paper-only and does not represent a broker action.

A persistent **daily paper kill switch** is now implemented in `paper_control.py` and stored through the durable learning-event store as `paper_controls`. It is scoped to the **current IST trading day only** and automatically ceases to apply on the next IST trading day. When active:
- all new paper entries are blocked;
- any existing paper position is closed on the next live snapshot with reason `MANUAL_KILL_SWITCH`;
- previously closed trades remain untouched;
- the kill state survives service restart because it is persisted in PostgreSQL when configured, with the existing filesystem fallback otherwise;
- real trading remains disabled.

Control endpoints:
- `/api/v1/paper/control` — current kill-switch state.
- `POST /api/v1/paper/kill-switch` — activate the daily kill switch.
- `/paper-control` — dedicated browser control page with confirmation and status.

The kill switch intentionally has **no reset endpoint for the same day**. The next IST trading day starts clear automatically. The dedicated control page links back to `/intelligence`.

The current live monitor's left-side **Brain Plan** is a next/current decision plan, not the frozen risk plan of the already-open trade. Therefore it can show `WAIT_FOR_TRIGGER` and different spot SL/target values while an existing trade remains OPEN. The active trade's frozen entry/risk values are shown separately in the Active Paper Trade panel. This distinction should remain explicit in future UI revisions.

## 2026-09-17 entry-loss safeguards and lifecycle reconciliation
The 17-Sep trade review identified three deterministic safeguards and they are now implemented in `apps/api/src/quantnifty/entry_guard.py` and enforced through `decision_validation.validate_decision()` for **LIVE mode only**:

1. **Minimum directional displacement:** 8 NIFTY points in the intended direction. If raw displacement is unavailable, the guard records `UNAVAILABLE_PASS` rather than fabricating a block. A strong aligned trend/structural confirmation can also satisfy the gate, preserving strong directional entries such as the observed #3 trade.
2. **Support/resistance proximity confirmation:** within 35 NIFTY points of the relevant level, a directional entry requires a confirmed break of at least 5 points. Missing support/resistance data is `UNAVAILABLE_PASS`; it is never invented.
3. **Failed-signal cooldown:** after a negative same-direction CLOSED paper trade, the same direction is blocked for 3 minutes unless the cooldown expires. The guard uses only durable same-day CLOSED paper outcomes in LIVE mode.

The guard is part of the final deterministic validation path, is included in the immutable decision validation evidence, and forces the execution plan to `BLOCKED` when a guard fails. BACKTEST/REPLAY modes are not connected to live outcomes and are untouched by this guard.

Relevant commits:
- `20e25725941cd3db79a586017013173b4cfbc41e` — initial entry guard.
- `4f266e4975495f580fc413a208402132ed281480` — corrected support-break confirmation logic.
- `9f4dabdf99e6ba4d06a2cee100ed60012fa2eb4f` — integrated guard into deterministic decision validation.
- `edd596a0c6c6152e46683a865b8cdba55c9669d4` — regression tests for support-area blocking, strong displacement, confirmed break, cooldown, missing support and replay isolation.

The authoritative paper ledger was also hardened in `paper_ledger_api.py`:
- CLOSED rows are reconciled by durable `trade_id` so duplicate lifecycle events cannot inflate completed-trade counts.
- `/api/v1/paper/ledger` now exposes `summary.lifecycle_reconciliation` with lifecycle-event count, unique trade IDs, OPEN/CLOSED event counts, closed/active trade IDs and duplicate lifecycle IDs.
- This does **not** create a second ledger; `/api/v1/paper/ledger` and `/api/v1/paper/trade-audit` remain the canonical sources.
- Commit: `ac9596baa6be0e6845a15e7c3335de204735f9e8`.

### 17-Sep trade-count investigation
The earlier six-trade analysis was a **snapshot-time analysis**, based on the live-monitor screenshot captured around 11:19 IST, where the UI itself showed `6 completed · 2 active`. It was not a full-day ledger extraction. Therefore it did not include later trades from the remainder of 17-Sep.

Render production evidence shows the durable `outcomes` counter at **92** before the live session began producing new trades and **145** by 15:30/16:00 IST. `outcomes` is a lifecycle-event counter, not a trade counter: a normal paper trade writes an `OPEN` event and later a `CLOSED` event. Therefore `92 -> 145` cannot be interpreted as 53 trades. The new ledger reconciliation explicitly separates lifecycle events from unique completed/active trade IDs so this ambiguity is removed from future analysis.

The six rows in the earlier report were therefore not evidence that only six trades existed for the whole day. They were the six completed trades visible at that screenshot time. The durable backend is traceable; the earlier report was incomplete because it used the point-in-time UI evidence instead of the full authoritative ledger.

## V3 thesis-hold research
The research lifecycle is:

`ENTRY CONFIRMED -> BUY ACTUAL STORED OPTION -> OPEN POSITION -> HOLD/MONITOR -> EXIT -> ONLY THEN ALLOW NEXT ENTRY`

This is a research/replay capability only and is not a historical-learning path for the live Adaptive Brain. Stored-day research can validate the mechanics of the lifecycle using supplied/replayed snapshots, but those results never seed live Adaptive memory or policy.

## Dual learning architecture
There are now two deliberately independent daily test/learning tracks.

**Track A — LIVE_MARKET:** records what the deterministic Brain actually decided during the live IST session and what its read-only paper lifecycle actually produced. Live outcomes remain the authoritative record of actual paper behavior.

**Track B — POST_MARKET:** after the session, `after_market_lab.py` runs every configured research strategy against the day's raw market snapshots only. Raw inputs include the captured NIFTY/option market observations available in snapshots (prices/OHLC, OI, volume, Greeks/IV and related analytics where present). It generates counterfactual entries/exits and P&L for each strategy. It does not load, inspect, score or rewrite live decisions, paper trades or live outcomes.

The post-market track is therefore a genuine independent experiment: **"What would every strategy have produced if applied to today's raw market movement?"** It is not a replay of the live paper ledger.

`dual_learning.py` provides a deterministic, read-only comparison layer. It accepts already-produced LIVE_MARKET outcomes and POST_MARKET research as separate inputs, reports profitable/negative status for each strategy in each track, ranks strategies for future adaptation, and does not itself load data or mutate execution settings.

Daily lifecycle:

`LIVE SESSION -> LIVE_MARKET learning`  
`MARKET CLOSE -> POST_MARKET raw-data strategy test -> POST_MARKET learning`  
`BOTH COMPLETED -> deterministic dual-track comparison -> next-day adaptive preference`  
`NEXT DAY LIVE SESSION -> repeat`

Prior days remain retained. Learning is append-only and chronological; future outcomes never alter an earlier decision. A strategy is not considered reliable from one day alone. Any future policy/profile change must remain deterministic, auditable, risk-gated and paper-only.

## Incremental live learning model
The authoritative learning model is live, incremental, append-only learning from day one onward. Each live IST session produces snapshots, decisions, paper-trade lifecycle events and CLOSED outcomes. The learning store retains prior observations and accumulates new observations across days; past learning records are not deleted as part of normal operation.

The engine should continuously compare the current session against its retained live experience, evaluate strategy/scenario performance, regime behavior, entry/exit quality, risk outcomes and decision confidence, and use those observations to improve future paper decisions. The intended horizon is naturally rolling forward from day 1 to day 300 and beyond, without resetting the learned history.

Historical archives are not required for this learning model. No external historical dataset is a project dependency or acceptance criterion.

## Research robustness layer
`apps/api/src/quantnifty/research_analytics.py` is a research-only diagnostics layer. It reports performance by regime, direction, exit reason and IST time bucket and provides a conservative robustness gate using minimum trades, expectancy, profit factor and maximum drawdown. It never changes live decisions.

`apps/api/src/quantnifty/research_optimizer.py` provides deterministic parameter-grid generation and candidate ranking for offline/research analysis. It cannot call live trading or mutate execution configuration. These capabilities are secondary research tooling and are not used to bootstrap or seed the live Adaptive Brain.

## Validation boundary
Offline validation proves deterministic code behavior, data-contract handling, safety invariants and research mechanics. It does not prove future live-market behavior.

The offline-completable gate covers compilation and the full unit suite; canonical CSV loading and exact-expiry enforcement; CE/PE/OI/volume/premium normalization; deterministic market-state, event, pressure and confidence gates; V3 entry/fill lifecycle; stored-option premium P&L mechanics; bid/ask-aware fills; spot-point stop/2R target; thesis/session/expiry exits; one-position lifecycle and re-entry suppression; paper/read-only invariants; research diagnostics; chronological splitting; robustness gates; deterministic parameter-grid/ranking behavior; cost-sensitivity plumbing; decision-latency instrumentation; UI telemetry integrity; and independent dual-learning track isolation. The new entry-guard unit coverage includes support-area blocking, minimum displacement, confirmed breakdown, same-direction cooldown, missing-evidence behavior and replay isolation.

The live-only gate covers provider connectivity and current option-chain freshness; real expiry discovery; real-time timestamp monotonicity; live snapshot cadence and network latency; PostgreSQL durability in the deployed environment; append-only same-day Adaptive memory using only CLOSED live-paper outcomes; live paper OPEN/HOLD/EXIT behavior against changing quotes; real bid/ask/liquidity and delta availability; Render deployment parity; weekday live-validation harness success; and complete live sessions including after-market learning. These tests remain paper/read-only.

## Historical options adapter
`apps/api/src/quantnifty/external_options_loader.py` remains available only as a generic research/replay adapter for supplied datasets. It is not an empirical validation dependency and must never seed live Adaptive memory. No historical archive is required for project completion under the incremental live-learning architecture.

## Decision-quality hardening
The deterministic market brain treats both upstream input confidence and institutional-model confidence as required confidence gates. A weak provider confidence cannot be hidden by a later aggregate score. This remains a no-trade safety filter and does not enable execution.

## Decision latency instrumentation
`decision_latency.py` instruments the deterministic decision critical path by stage and reports total/stage milliseconds. The instrumentation is observational only and does not alter decisions or enable execution. Real provider/network latency still requires live observation.

## Production validation evidence
On 2026-09-11 Render evidence established LIVE_PROVIDER option-chain snapshots, advancing durable snapshots, distinct decision-event gating, a live paper OPEN -> IDLE lifecycle, PostgreSQL learning durability and `trading=DISABLED`. This proved the live read-only loop is operating, not that it is profitable.

The production evidence workflow checks the stored-day V3 research endpoint and asserts `source=STORED_DAY`, `research_only=true`, `orders_placed=0`, `mode=READ_ONLY_AFTER_MARKET`, `position_lifecycle=THESIS_HOLD_UNTIL_INVALIDATION`, `risk_model=SPOT_ATR_PROXY_X4_WITH_ATM_IV_ADJUSTMENT`, and `tuning_profile=INTRADAY_OPTION_RESEARCH_V3_THESIS_HOLD` for tested strategies. It separately requires `/api/v1/market` to remain `LIVE_PROVIDER` during an active market session and `/api/v1/replay` to remain `READ_ONLY_REPLAY`, preserving live/replay isolation.

The live validation harness treats NSE weekends as an intentional no-market condition and does not falsely fail on expected provider unavailability outside market days. Weekday live-provider validation remains strict and retries transient provider failures instead of treating one 503 as a code regression.

## Live provider session guard
`market_session.py` is now the authoritative provider-access boundary for the deployed live loop. LIVE_PROVIDER polling is allowed only Monday-Friday from **09:15 through 15:29 IST**. At 15:30 IST and later, weekends, and pre-open, the background refresh loop does not call INDstocks and sleeps until the next eligible session. `/api/v1/market`, `/api/v1/intelligence`, `/api/v1/decision`, and `/api/v1/final-decision` return an explicit `MARKET_CLOSED` read-only payload instead of initiating a provider call outside the live session. The after-market scheduler remains separate and continues to run its raw stored-snapshot research after the close.

The dashboard previously connected to `/ws` while the backend only exposed `/ws/market`, which caused the screenshot's **"Live stream disconnected · retrying…"** state. The backend now exposes both `/ws` and `/ws/market` to preserve compatibility. Outside market hours the WebSocket sends a `MARKET_CLOSED` heartbeat and does not poll the live provider.

## Validation state
- Application runtime boundary: `3009bcc8204da78231bdce2ce925b3521983dd8b` — explicit 09:00-16:00 IST weekday runtime helpers and runtime state in closed payload.
- Runtime boundary tests: `d2d7e70fb320c67d32472f3bf4cecca30387f8c2` — 09:00 open, 15:59 active, 16:00 close, weekend close.
- Render runtime/cost documentation: `5579304f8bcf4d656f6a551c601dfbb0f9c49211` — `docs/RENDER_RUNTIME.md`.
- Live monitor current/previous trade UI remains on `main`.
- Dual learning and post-market isolation remain on `main`.
- Real trading remains permanently disabled.
- Daily paper kill switch and multiple-active recovery guard are implemented on `main`.
- Live entry safeguards and lifecycle reconciliation are implemented on `main` as of commits `4f266e4975495f580fc413a208402132ed281480`, `9f4dabdf99e6ba4d06a2cee100ed60012fa2eb4f`, `edd596a0c6c6152e46683a865b8cdba55c9669d4`, and `ac9596baa6be0e6845a15e7c3335de204735f9e8`.
- The new entry-guard/lifecycle-reconciliation changes are not live until a successful Render deployment of the current `main` commit completes.

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts. Retain live learning history; do not silently reset or delete prior learning data. Post-market research must remain independent of live paper decisions/outcomes. Use normal repository changes and existing validation workflows only.
