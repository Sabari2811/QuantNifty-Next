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
The application runtime window is **09:00-16:00 IST, Monday-Friday**. It includes 09:00-09:15 pre-market initialization and 15:40-16:00 post-market research. The NIFTY equity-derivatives live-provider window is **09:15-15:40 IST**. NSE Closing Auction Session (CAS) is a separate cash-segment session from 15:15-15:35; QuantNifty observes CAS as an underlying-market influence and does not treat NIFTY options as CAS instruments.

The production cost-saving design is: paid `quantnifty-api` compute active only during the 09:00-16:00 weekday window; paid `quantnifty-production` PostgreSQL remains available for durable learning, paper trades and research history. Application sleep alone does not stop paid Render compute; the Render service itself must be suspended/resumed.

The repository now contains `.github/workflows/render-service-resume.yml` and `.github/workflows/render-service-suspend.yml`. They call the Render API at 09:00 IST and 16:00 IST weekdays. They require the repository secret `RENDER_API_KEY`; the key is never committed. The non-secret QuantNifty service ID is `srv-dad5e767bikc739oighg`. GitHub Actions cron is UTC and may start a few minutes late; the application remains fail-closed outside its defined runtime/market windows.

Required QuantNifty-Next production resources:
- `quantnifty-api`: paid web-service compute, active only during the runtime window.
- `quantnifty-production`: paid PostgreSQL for durable production state.
- Separate `QuantNifty` services/workers are unrelated and must not be enabled for this project.

## NSE Closing Auction Session (CAS) policy
NSE currently documents CAS as a separate 20-minute session for eligible cash-segment stocks from **15:15-15:35 IST**. The reference-price/transition period is 15:15-15:20, order entry is 15:20-15:30, and matching/trade confirmation is 15:30-15:35. NSE separately documents equity-derivatives regular trading through **15:40 IST**.

QuantNifty therefore uses the following deterministic policy:
- **Before 15:15:** normal adaptive NIFTY-options strategy.
- **15:15-15:30:** `CAS_REENTRY` may generate a new NIFTY-options paper entry only when CAS-aware momentum, participation, OI and liquidity confirmation passes the deterministic threshold.
- **15:30-15:35:** CAS matching is complete; no new CAS-aware NIFTY entries are allowed. Existing CAS-aware paper positions remain eligible for management.
- **15:35-15:39:** no new entries; manage existing position only.
- **15:39:** force-close any remaining NIFTY paper position, one minute before the 15:40 derivatives close.
- **15:40 onward:** NIFTY derivatives live session closed; provider polling stops and post-market research can run.

The CAS strategy is implemented in `apps/api/src/quantnifty/cash_session_strategy.py` and exposed as `cas_reentry`. Backward-compatible `cash_*` aliases remain only to avoid breaking existing callers. The strategy never consumes a future auction result and explicitly records that NIFTY options do not participate in the cash CAS.

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
The Market Brain screen has a dedicated daily trade-history component inside the Active Paper Trade monitor. It reads the durable read-only paper ledger from `/api/v1/paper/ledger` rather than research data or the post-market lab.

For the **current open trade**, the monitor shows option premium entry -> current mark, live P&L, premium target/SL derived from the frozen entry delta/risk budget, current NIFTY spot, entry spot, spot movement, spot SL/target, entry time, mark time, instrument and read-only execution state. Exit is explicitly shown as `OPEN` until the paper lifecycle closes it.

For **previous completed trades today**, the monitor shows trade number, direction, strategy, option/strike, entry premium, exit premium, entry spot, exit spot, frozen NIFTY SL, frozen NIFTY target, realized P&L, exit reason, quantity and entry/exit times. The component refreshes every 5 seconds and uses only the current IST-day paper ledger.

The UI enhancement is implemented in `apps/api/src/quantnifty/web/intelligence.html`. The application mounts `paper_ledger_api.py` from `main.py`, making the durable paper ledger available to the live monitor. This remains read-only and does not submit, modify or cancel broker orders.

## Paper-trade discrepancy guard and daily kill switch
The live monitor screenshot on 2026-09-17 showed **6 completed · 2 active** while only one active trade was rendered. This exposed a lifecycle-recovery edge case: `LivePaperManager._recover()` previously restored only the newest OPEN trade into memory while leaving an older OPEN lifecycle in the durable ledger. That could violate the intended one-position-at-a-time invariant across a service restart.

`live_paper_manager.py` now enforces a single-active invariant during recovery. If multiple current-day OPEN paper trades are found, the newest entry is retained and older orphaned OPEN trades are closed at the latest available snapshot with reason `MULTIPLE_ACTIVE_TRADE_GUARD`. This is paper-only and does not represent a broker action.

A persistent **daily paper kill switch** is implemented in `paper_control.py` and stored through the durable learning-event store as `paper_controls`. It is scoped to the **current IST trading day only** and automatically ceases to apply on the next IST trading day. When active:
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
The 17-Sep trade review identified three deterministic safeguards and they are implemented in `apps/api/src/quantnifty/entry_guard.py` and enforced through `decision_validation.validate_decision()` for **LIVE mode only**:

1. **Minimum directional displacement:** 8 NIFTY points in the intended direction. If raw displacement is unavailable, the guard records `UNAVAILABLE_PASS` rather than fabricating a block. A strong aligned trend/structural confirmation can also satisfy the gate.
2. **Support/resistance proximity confirmation:** within 35 NIFTY points of the relevant level, a directional entry requires a confirmed break of at least 5 points. Missing support/resistance data is `UNAVAILABLE_PASS`; it is never invented.
3. **Failed-signal cooldown:** after a negative same-direction CLOSED paper trade, the same direction is blocked for 3 minutes unless the cooldown expires. The guard uses only durable same-day CLOSED paper outcomes in LIVE mode.

The guard is part of the final deterministic validation path, is included in the immutable decision validation evidence, and forces the execution plan to `BLOCKED` when a guard fails. BACKTEST/REPLAY modes are not connected to live outcomes and are untouched by this guard.

Relevant commits:
- `20e25725941cd3db79a586017013173b4cfbc41e` — initial entry guard.
- `4f266e4975495f580fc413a208402132ed281480` — corrected support-break confirmation logic.
- `9f4dabdf99e6ba4d06a2cee100ed60012fa2eb4f` — integrated guard into deterministic decision validation.
- `edd596a0c6c6152e46683a865b8cdba55c9669d4` — regression tests.

The authoritative paper ledger was also hardened in `paper_ledger_api.py`:
- CLOSED rows are reconciled by durable `trade_id` so duplicate lifecycle events cannot inflate completed-trade counts.
- `/api/v1/paper/ledger` exposes `summary.lifecycle_reconciliation` with lifecycle-event count, unique trade IDs, OPEN/CLOSED event counts, closed/active trade IDs and duplicate lifecycle IDs.
- This does **not** create a second ledger; `/api/v1/paper/ledger` and `/api/v1/paper/trade-audit` remain the canonical sources.
- Commit: `ac9596baa6be0e6845a15e7c3335de204735f9e8`.

## V3 thesis-hold research
The research lifecycle is:

`ENTRY CONFIRMED -> BUY ACTUAL STORED OPTION -> OPEN POSITION -> HOLD/MONITOR -> EXIT -> ONLY THEN ALLOW NEXT ENTRY`

This is a research/replay capability only and is not a historical-learning path for the live Adaptive Brain. Stored-day research can validate the mechanics of the lifecycle using supplied/replayed snapshots, but those results never seed live Adaptive memory or policy.

## Dual learning architecture
There are two deliberately independent daily test/learning tracks.

**Track A — LIVE_MARKET:** records what the deterministic Brain actually decided during the live IST session and what its read-only paper lifecycle actually produced. Live outcomes remain the authoritative record of actual paper behavior.

**Track B — POST_MARKET:** after the session, `after_market_lab.py` runs every configured research strategy against the day's raw market snapshots only. Raw inputs include captured NIFTY/option observations available in snapshots (prices/OHLC, OI, volume, Greeks/IV and related analytics where present). It generates counterfactual entries/exits and P&L for each strategy. It does not load, inspect, score or rewrite live decisions, paper trades or live outcomes.

The post-market track is therefore an independent experiment: **what would every strategy have produced if applied to today's raw market movement?** It is not a replay of the live paper ledger.

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

The offline-completable gate covers compilation and the full unit suite; canonical CSV loading and exact-expiry enforcement; CE/PE/OI/volume/premium normalization; deterministic market-state, event, pressure and confidence gates; V3 entry/fill lifecycle; stored-option premium P&L mechanics; bid/ask-aware fills; spot-point stop/2R target; thesis/session/expiry exits; one-position lifecycle and re-entry suppression; paper/read-only invariants; research diagnostics; chronological splitting; robustness gates; deterministic parameter-grid/ranking behavior; cost-sensitivity plumbing; decision-latency instrumentation; UI telemetry integrity; independent dual-learning track isolation; and CAS-aware session boundary coverage.

The live-only gate covers provider connectivity and current option-chain freshness; real expiry discovery; real-time timestamp monotonicity; live snapshot cadence and network latency; PostgreSQL durability in the deployed environment; append-only same-day Adaptive memory using only CLOSED live-paper outcomes; live paper OPEN/HOLD/EXIT behavior against changing quotes; real bid/ask/liquidity and delta availability; Render deployment parity; weekday live-validation harness success; and complete live sessions including after-market learning. These tests remain paper/read-only.

## Historical options adapter
`apps/api/src/quantnifty/external_options_loader.py` remains available only as a generic research/replay adapter for supplied datasets. It is not an empirical validation dependency and must never seed live Adaptive memory. No historical archive is required for project completion under the incremental live-learning architecture.

## Decision-quality hardening
The deterministic market brain treats both upstream input confidence and institutional-model confidence as required confidence gates. A weak provider confidence cannot be hidden by a later aggregate score. This remains a no-trade safety filter and does not enable execution.

## Decision latency instrumentation
`decision_latency.py` instruments the deterministic decision critical path by stage and reports total/stage milliseconds. The instrumentation is observational only and does not alter decisions or enable execution. Real provider/network latency still requires live observation.

## Production validation evidence
Production evidence previously established LIVE_PROVIDER option-chain snapshots, advancing durable snapshots, distinct decision-event gating, a live paper OPEN -> IDLE lifecycle, PostgreSQL learning durability and `trading=DISABLED`. This proves the live read-only loop is operating, not that it is profitable.

The production evidence workflow checks stored-day V3 research and replay isolation. It separately requires `/api/v1/market` to remain `LIVE_PROVIDER` during an active market session and `MARKET_CLOSED` outside the defined session, preserving provider isolation.

## Current implementation state
The current `main` includes the corrected NSE timing model and CAS-aware lifecycle:
- `market_session.py`: NIFTY derivatives live-provider window 09:15-15:40 IST; application runtime 09:00-16:00 IST.
- `cash_session_strategy.py`: deterministic `cas_reentry` strategy; CAS is explicitly modeled as a cash-market influence, not an NIFTY-options CAS instrument.
- `session_policy.py`: `NORMAL_ADAPTIVE` 09:20-15:15, `CAS_REENTRY` 15:15-15:35, `DERIVATIVES_CLOSE_ONLY` 15:35-15:40, then `CLOSED`.
- `paper_trade_tracker.py`: normal positions close before CAS; CAS-aware positions may be managed until forced close at 15:39.
- `paper_entry_gate.py`: normal entries stop before the CAS window; CAS-aware entries stop at 15:30; daily paper limits remain enforced.
- `.github/workflows/render-service-resume.yml`: 09:00 IST weekday Render resume.
- `.github/workflows/render-service-suspend.yml`: 16:00 IST weekday Render suspend.
- `docs/RENDER_RUNTIME.md`: authoritative runtime/cost schedule.

The Render scheduler workflows are committed, but **actual service suspend/resume cannot be claimed validated until the repository secret `RENDER_API_KEY` is configured and a scheduled/manual workflow run succeeds**. No secret is present in the repository.

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts. Retain live learning history; do not silently reset or delete prior learning data. Post-market research must remain independent of live paper decisions/outcomes. Use normal repository changes and existing validation workflows only.
