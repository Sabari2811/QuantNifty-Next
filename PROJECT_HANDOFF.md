# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-13  
**Branch:** `main`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production:** https://quantnifty-api.onrender.com  
**Backtest:** https://quantnifty-api.onrender.com/backtest  
**Execution:** READ-ONLY; no real orders; `trading=DISABLED`.

## Product and safety contract
QuantNifty-Next is a Live Adaptive Brain + After-Market Research Lab. Live decisions use only data available at decision time. Adaptive runtime is restricted to the live IST session; no overnight paper positions are allowed. Same-day Adaptive memory consumes only current-IST-day CLOSED outcomes in explicit LIVE mode. There is no historical learning/bootstrap/performance-gate path. Past live-session data is retained and accumulated; it is not deleted or used as a historical replay substitute. `data_Review.txt`, old recordings and external historical archives are replay/reference evidence only and never seed live Adaptive memory or policy. Real trading is permanently disabled.

Do not modify `QuantNifty`, `data/instruments/fno.csv`, or commit secrets.

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

The offline-completable gate covers compilation and the full unit suite; canonical CSV loading and exact-expiry enforcement; CE/PE/OI/volume/premium normalization; deterministic market-state, event, pressure and confidence gates; V3 entry/fill lifecycle; stored-option premium P&L mechanics; bid/ask-aware fills; spot-point stop/2R target; thesis/session/expiry exits; one-position lifecycle and re-entry suppression; paper/read-only invariants; research diagnostics; chronological splitting; robustness gates; deterministic parameter-grid/ranking behavior; cost-sensitivity plumbing; decision-latency instrumentation; UI telemetry integrity; and independent dual-learning track isolation.

The live-only gate covers provider connectivity and current option-chain freshness; real expiry discovery; real-time timestamp monotonicity; live snapshot cadence and network latency; PostgreSQL durability in the deployed environment; append-only same-day Adaptive memory using only CLOSED live-paper outcomes; live paper OPEN/HOLD/EXIT behavior against changing quotes; real bid/ask/liquidity and delta availability; Render deployment parity; weekday live-validation harness success; and complete live sessions including after-market learning. These tests remain paper/read-only.

## Historical options adapter
`apps/api/src/quantnifty/external_options_loader.py` remains available only as a generic research/replay adapter for supplied datasets. It is not an empirical validation dependency and must never seed live Adaptive memory. No historical archive is required for project completion under the incremental live-learning architecture.

## Decision-quality hardening
The deterministic market brain treats both upstream input confidence and institutional-model confidence as required confidence gates. A weak provider confidence cannot be hidden by a later aggregate score. This remains a no-trade safety filter and does not enable execution.

## Decision latency instrumentation
`decision_latency.py` instruments the deterministic decision critical path by stage and reports total/stage milliseconds. The instrumentation is observational only and does not alter decisions or enable execution. Real provider/network latency still requires live observation.

## Production validation evidence
On 2026-09-11 Render evidence established LIVE_PROVIDER option-chain snapshots, advancing durable snapshots, distinct decision-event gating, a live paper OPEN -> IDLE lifecycle, PostgreSQL learning durability and `trading=DISABLED`. This proved the live read-only loop is operating, not that it is profitable.

The production evidence workflow checks the stored-day V3 research endpoint and asserts `source=STORED_DAY`, `research_only=true`, `orders_placed=0`, `mode=READ_ONLY_AFTER_MARKET`, `position_lifecycle=THESIS_HOLD_UNTIL_INVALIDATION`, `risk_model=SPOT_ATR_PROXY_X4_WITH_ATM_IV_ADJUSTMENT`, and `tuning_profile=INTRADAY_OPTION_RESEARCH_V3_THESIS_HOLD` for tested strategies. It separately requires `/api/v1/market` to remain `LIVE_PROVIDER` and `/api/v1/replay` to remain `READ_ONLY_REPLAY`, preserving live/replay isolation.

The live validation harness treats NSE weekends as an intentional no-market condition and does not falsely fail on expected provider unavailability outside market days. Weekday live-provider validation remains strict and retries transient provider failures instead of treating one 503 as a code regression.

## Live provider session guard
`market_session.py` is now the authoritative provider-access boundary for the deployed live loop. LIVE_PROVIDER polling is allowed only Monday-Friday from **09:15 through 15:29 IST**. At 15:30 IST and later, weekends, and pre-open, the background refresh loop does not call INDstocks and sleeps until the next eligible session. `/api/v1/market`, `/api/v1/intelligence`, `/api/v1/decision`, and `/api/v1/final-decision` return an explicit `MARKET_CLOSED` read-only payload instead of initiating a provider call outside the live session. The after-market scheduler remains separate and continues to run its raw stored-snapshot research after the close.

The dashboard previously connected to `/ws` while the backend only exposed `/ws/market`, which caused the screenshot's **"Live stream disconnected · retrying…"** state. The backend now exposes both `/ws` and `/ws/market` to preserve compatibility. Outside market hours the WebSocket sends a `MARKET_CLOSED` heartbeat and does not poll the live provider.

## Validation state
- Live-provider session guard: `dc3cb1f27e27aaa62eeccfc3a048cf9db4325ee9`.
- Live refresh/WebSocket/session-boundary implementation: `87f3755ff00368078ea4f67dbedae285111df590`.
- NSE session boundary regression tests: `992757c575d8525819fd7e1dfd39e862a4d677ae`.
- Dashboard/live-session contract tests: `08e408888e85f4c89df13940e614371d9bd8fd68`.
- Dual learning isolation implemented on `main`: `after_market_lab.py` is explicitly raw-snapshot-only and records `live_*_data_accessed=false`; it remains counterfactual/read-only.
- New `dual_learning.py` comparison layer: `8cc0fb08da6f741700718859515bcc927966b3da`.
- Post-market isolation and metadata: `023e1a31671ecc109127dfa67eb3adda445dd82a`.
- Dual-track regression tests: `96d3cf7162f126287d04e6f31bfa73b561de7622` plus strengthened after-market isolation assertions in `ff271151cc20d07d98e02b1f75dda9b58e253424`.
- Historical statistical validation remains removed as a project requirement.
- Thesis-hold implementation and point-based volatility risk are on `main`.
- Research robustness and optimizer modules remain secondary offline tooling and do not seed live learning.
- Validation harness hardening: `ff61a70f7d20fa00a356cc41d9dc474bd617e98c`.
- Latency instrumentation: `d7349e16f2d564cb49bf78cf0afcce7622eae7c1`, `6af1c459efcf37f2423e4e81fa234320e88772d2`, `b6e30ed7163081713fdd762e36998cced4e248a3`.
- Offline validation gate: `5802e4dd6c148544e722bc8ca2d2478d366b4dc4`, with V3 bid/ask assertion correction `c56c63591a192fa5b61601124b03f2d4a2f7f2f8`.
- Deterministic QuantNifty intelligence is the sole decision layer; Astra is removed.
- Real trading remains permanently disabled.

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts. Retain live learning history; do not silently reset or delete prior learning data. Post-market research must remain independent of live paper decisions/outcomes. Use normal repository changes and existing validation workflows only.
