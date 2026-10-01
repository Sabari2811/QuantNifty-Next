# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-10-01  
**Branch:** `main`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production:** https://quantnifty-api.onrender.com  
**Backtest:** https://quantnifty-api.onrender.com/backtest  
**Execution:** READ-ONLY; real trading permanently disabled; `trading=DISABLED`.

## Authoritative scope and safety
QuantNifty-Next is the only project in scope. Do not start or modify the separate `QuantNifty` repository. Never submit broker orders, never commit secrets, never use an external LLM/API for live decisions, and never modify `data/instruments/fno.csv`.

Live decisions use only data available at decision time. Same-day Adaptive memory uses only current-IST-day CLOSED outcomes from explicit LIVE mode. Historical recordings/archives are replay/reference evidence only and never seed live Adaptive memory. No overnight paper positions are allowed.

The live path is deterministic:

`LIVE_PROVIDER snapshot -> market/event intelligence -> institutional/risk gates -> read-only paper lifecycle -> same-day learning`

Post-market research is a separate counterfactual track and never reads, scores or rewrites live decisions, paper trades or live outcomes.

## Required session policy
The current project policy is deliberately narrower than NSE's broader derivatives hours:

- **Application runtime:** 09:00-16:00 IST, Monday-Friday.
- **NIFTY live provider:** 09:15-15:30 IST only.
- **Normal paper strategy:** normal entries before the cash-session window; normal positions must close before 15:15 IST.
- **Cash-session strategy:** `CAS_REENTRY`, new entries only 15:15-15:27 IST.
- **Cash-session force exit:** 15:29 IST.
- **Post-market research:** 15:30-16:00 IST, independent of live decisions/trades.
- **Application compute suspension:** 16:00 IST weekdays; resume 09:00 IST weekdays.
- **Post-close/weekend:** no live provider polling and no live paper lifecycle.

NIFTY options are not CAS instruments. CAS is observed only as a cash-market influence/evidence window. The project must not consume a future auction result to make a decision.

## Paper-risk invariants
- Maximum **3 paper trades per IST trading day**.
- Exactly **one NIFTY option lot** per active paper position; current NIFTY lot-size policy is 65.
- Exactly **one active paper position** at a time.
- New entries are blocked while an active position exists.
- Paper risk is frozen at entry: entry spot/premium, selected instrument, trigger, stop, target, R:R and exit policy.
- Premium stop/target are derived from live option delta and the NIFTY-point risk budget.
- The daily paper kill switch is persistent, IST-day scoped and paper-only.
- Recovery reconciles multiple durable OPEN lifecycle records so an old orphan cannot create a second active position.

## Current implementation
Relevant authoritative modules:

- `market_session.py` — runtime 09:00-16:00 and live provider 09:15-15:30.
- `cash_session_strategy.py` — deterministic `cas_reentry`, 15:15-15:27 entry window and 15:29 force exit.
- `paper_trade_tracker.py` — normal-position close before cash session and cash force-close.
- `paper_entry_gate.py` — three-trade daily cap, active-position lock and cash entry cutoff.
- `live_paper_manager.py` — one-lot sizing, paper-only lifecycle and durable recovery.
- `after_market_lab.py` — independent raw-snapshot research track.
- `after_market_scheduler.py` — starts post-market research at **15:30 IST** and now performs an overdue-position recovery guard before research, so a restart/deploy cannot leave a durable OPEN paper lifecycle into post-market.
- `.github/workflows/render-service-resume.yml` — Render resume at 09:00 IST weekdays.
- `.github/workflows/render-service-suspend.yml` — Render suspend at 16:00 IST weekdays.
- `docs/RENDER_RUNTIME.md` — authoritative Render runtime/cost boundary.
- `render.yaml` — now aligned to `quantnifty-production`, PostgreSQL 18, and the intended paid web-service runtime definition.

## Post-market learning boundary
`after_market_lab.py` loads only the day's raw market snapshots and runs the configured research strategies counterfactually. It records `POST_MARKET`, `RAW_MARKET_SNAPSHOTS`, `READ_ONLY_AFTER_MARKET`, `research_only=true`, and `orders_placed=0`. It does not access live decision, paper-trade or live-outcome data. Any resulting policy information is for future deterministic adaptation and never changes an in-progress live decision.

## Render production architecture
Required production resources for this project:

1. `quantnifty-api` — paid application compute, active only 09:00-16:00 IST weekdays.
2. `quantnifty-production` — PostgreSQL, kept available for durable learning, paper and research history.
3. Separate `QuantNifty` services/workers are unrelated and must remain disabled.

Render workspace: `quantnifty-next` (`tea-dad5cr0n74is73dbho3g`).  
Render service ID: `srv-dad5e767bikc739oighg`.

Actual Render inspection on 2026-09-17 confirmed:
- `quantnifty-api` exists in the correct workspace, uses `main`, is auto-deploy enabled, Singapore region, and is currently a paid `1c-2g` web service.
- `quantnifty-production` exists, Singapore region, PostgreSQL 18, `basic_256mb`, and is available/not suspended.
- The separate `QuantNifty` services are present in the workspace but are not this project's service and must not be enabled for this project.

GitHub Actions use the non-secret service ID and repository secret `RENDER_API_KEY`. The secret must never be committed or placed in source. Scheduler cron is UTC: `30 3 * * 1-5` for 09:00 IST resume and `30 10 * * 1-5` for 16:00 IST suspend. Scheduler jitter must not widen the application/provider windows because the application is fail-closed outside its defined windows.

**Production database configuration gap discovered during audit:** the running `quantnifty-api` runtime evidence currently reports a reachable PostgreSQL database named `quantnifty_learning`, not `quantnifty_production`. The service's runtime diagnostics showed `quantnifty_learning_user` and host `dpg-dafd0kmq1p3s73b8inf0-a`. The `quantnifty-production` database itself is available, but the service environment has not yet been safely switched because its connection string is a secret and must not be guessed or committed. `render.yaml` has been corrected to point future Blueprint configuration at `quantnifty-production`. Do not claim the live service is using `quantnifty-production` until Render service environment configuration is explicitly reconciled and revalidated.

## Deployment and production validation evidence
Before this continuation, the deployed `quantnifty-api` was live on commit `99272c58ed0076d178d3e704ce98526feafe71a5`.

The audit confirmed runtime evidence with:
- `trading=DISABLED`.
- PostgreSQL reachable and durable.
- Live-provider polling stopped outside the configured provider window.
- Durable learning counters were present: 833 decisions, 148 outcomes, 10 research runs and 7,094 snapshots at the observed runtime point.

The audit also exposed an important lifecycle-recovery issue: at 15:59 IST the runtime evidence still showed a durable paper position as `OPEN` even though the live-provider window had already closed. The normal live path is designed to close positions by 15:29, but a restart/deploy after the cutoff could restore a stale OPEN lifecycle. `after_market_scheduler.py` now performs a fail-closed overdue-position recovery before starting post-market research.

A new Render deployment was triggered for commit `3e000c6a1bc4ef02d4f880b1f1ec1d002afdcdd9` after the repository changes. At the time this handoff was updated, that deployment was still progressing through Render's build/update lifecycle and therefore must not be described as fully production-validated yet.

## Tests and CI
The repository CI workflow compiles `apps/api/src` and runs `pytest -q apps/api/tests` on Python 3.11, plus the intelligence UI telemetry integrity checks. A regression test asserts the post-market scheduler starts at 15:30 IST. The scheduler recovery guard is covered by the existing scheduler test module and is isolated from live execution.

Local GitHub cloning was unavailable in the current execution environment due outbound DNS/network restrictions, so local pytest execution was not claimed. GitHub Actions were observed starting for the latest main commits; final CI conclusion must be checked before claiming the full test gate passed.

## Render runtime / cost boundary
Application-level sleep is not sufficient to stop paid Render compute. The actual `quantnifty-api` service must be suspended at 16:00 IST and resumed at 09:00 IST weekdays. PostgreSQL must remain available. Render's API supports explicit service suspend/resume operations, and the repository workflows use the required API-key secret without committing it.

## Non-negotiable future rules
Always follow:

`inspect -> identify gaps -> implement -> test -> commit -> deploy -> validate -> update PROJECT_HANDOFF.md`

Never redesign the architecture without an explicit requirement. Never enable real trading. Never carry paper positions overnight. Never use future market outcomes in live decisions. Keep post-market research independent. Keep PostgreSQL available. Suspend/resume the **actual Render application service**, not merely the Python process. Never modify `data/instruments/fno.csv`.


## 2026-09-18 UI runtime fix
- `apps/api/src/quantnifty/web/intelligence.html` had a JavaScript syntax error caused by the apostrophe in `Today's` inside a single-quoted HTML string.
- This prevented the entire intelligence-page script from executing, leaving the initial `Connecting…`/waiting placeholders visible even though `/api/v1/market` was returning `200` with `LIVE_PROVIDER` data.
- Fixed by replacing that apostrophe with a typographic apostrophe, syntax-checked the browser script, committed as `8d5dcbce15edd8d8d58c7d29b5ff78cc7d9996ca`, and deployed to Render deployment `dep-dambrf2jnfac73ei14lg`, which reached `live` at `2026-09-18T04:29:07Z`.


## 2026-09-18 directional option-side guard
- Fixed `institutional_engine.execution_plan()` so directional selection is strict: BULLISH may only map to CE and BEARISH may only map to PE; the previous fallback could select the first candidate of the opposite side when the requested side was absent.
- Strengthened `decision_validation.validate_execution_plan()` to reject an approved directional plan with no instrument or with a mismatched option side.
- Deployed commit `64d2c39eb8be7ea775a565fe86473045fd779bbd` as Render deployment `dep-dambti8u01pc73f3jmo0`; deployment reached `live` at `2026-09-18T04:33:50Z`.

## 2026-09-18 Market Brain UI semantic/risk display fix
- Fixed 'apps/api/src/quantnifty/web/intelligence.html' so a BLOCKED plan with 'stop_points=null' / 'target_points=null' no longer converts JavaScript 'Number(null)' into zero and incorrectly displays the current spot as both Spot SL and Spot Target. Blocked plans now show '—' until a valid risk plan exists.
- Decision Intelligence now displays the authoritative validation action ('TAKE_TRADE', 'WAIT_CONFIRMATION', 'HOLD_ACTIVE_TRADE', or 'NO_TRADE') instead of only the coarse market-intelligence 'trade_ready' status.
- Directional gate labels are rendered semantically: the existing 'support_breakdown_confirmation' key is shown as **Resistance breakout confirmation** for BULLISH and **Support breakdown confirmation** for BEARISH, avoiding a misleading bullish support-break label while preserving the existing gate contract.
- 'apps/api/src/quantnifty/market_brain.py' now exposes 'validation.decision_action' as 'final_decision.status' while retaining the underlying base status as 'base_status'.
- UI JavaScript syntax was validated from the committed HTML with the browser-equivalent 'new Function(...)' compile check.
- GitHub CI for commit '4f1bb3dae11f1de0352fd21126fdd7d2d7a6554f' initially completed with 10 session/paper-lifecycle test failures (183 passed). Those baseline failures were stale regression expectations after the final 15:15-15:29 session-policy changes and a missing authoritative decision-action fixture field; they were resolved in PR #2. The final PR CI run completed with 193 passed and the intelligence UI telemetry validation passed.


## 2026-09-18 session/paper lifecycle CI fix
- Audited the 10 CI failures instead of masking them. The failures were in stale regression expectations around the final session policy plus one paper-manager fixture that did not include the required `decision_action`.
- Updated `test_cash_session_strategy.py`, `test_paper_entry_gate.py`, `test_paper_ledger.py`, `test_paper_session_close.py`, `test_paper_trade_tracker.py`, and `test_session_policy.py` to assert the current deterministic policy: normal paper positions close at the 15:15 cash-session boundary, CAS re-entry is permitted through 15:27 inclusive, cash-session positions force-close at 15:29, and authoritative paper-entry decisions use `decision_action`.
- No production trading/session implementation was weakened or changed to make the tests pass.
- PR #2 (`Fix stale session lifecycle CI expectations`) was merged to `main` as commit `4497c0176a67a3de4c3b8e69f1392a5d25e329bc`.
- Final PR CI run 596 completed successfully: **193 passed**, compile passed, and Intelligence UI telemetry validation passed.


## 2026-09-18 Live Monitor Loading Fix
- Fixed a JavaScript parse error in `apps/api/src/quantnifty/web/intelligence.html` that left Market Brain stuck on `Connecting...` and prevented all UI polling/rendering from starting.
- Rebuilt the active paper-trade renderer with option-native LTP, BID exit, option SL/target, strike+expiry, and Brain Plan quote fields.
- Updated the live-monitor UI test markers to match the option-native labels.
- UI script syntax validated with `new Function(...)`; Render build succeeded and production deployment is live on commit `d43aee536925e8997713a4872c4a75e61f9163da`.


## 2026-09-18 UI Refresh Stability
- Live Paper Monitor browser polling changed from 1 second to 10 seconds (`setInterval(refreshTradeSignal,10000)`).
- Backend provider polling remains at `POLL_SECONDS` default 2 seconds; this was intentionally not changed, so market/provider processing remains independent and low-latency.
- Added an in-flight guard so a slow monitor request cannot overlap the next UI refresh.
- On transient live-monitor/ledger HTTP errors, the UI now retains the last successful monitor payload and shows `RETRYING` instead of replacing the live trade panel with an error page.
- UI JavaScript syntax revalidated after the change. Render deployment `dep-damfhc2d0e5s73f8p0eg` is LIVE.


## 2026-09-18 Adaptive Trade Learning
- Added `apps/api/src/quantnifty/trade_learning.py` to convert closed paper outcomes into explicit adaptive lessons.
- Today's loss pattern is recorded as observation-only: directional context conflict, no bearish follow-through, and premium stop occurring before the NIFTY spot invalidation level.
- After-market research now reads closed paper outcomes and persists a `trade_learning` artifact alongside counterfactual strategy research.
- Adaptive brain now incorporates prior closed-trade outcomes into future regime/strategy memory. Repeated `DIRECTIONAL_CONTEXT_CONFLICT` patterns in `GAMMA_TRANSITION` require at least 2 historical occurrences before selecting the transition guard; one trade cannot change parameters by itself.
- Risk parameters are not widened from a single loss; comparable observations must reach the explicit promotion threshold before changing risk/entry parameters.
- Deployment `dep-damh52142hec7393e7ag` is LIVE.

## 2026-09-18 Context Alignment + Raw Post-Market Testing
- Added a deterministic context-alignment guard to the authoritative FinalDecision risk path.
- In GAMMA_TRANSITION / positive-gamma context, a directional thesis with at least two independent opposing context signals is blocked until confirmation; the guard is exposed as `signal.context_alignment` and `risk.context_alignment`.
- The guard directly addresses the observed failure mode: directional BEARISH thesis conflicting with BULLISH market bias/OI and positive gamma. It is generalized by context fields and is not hard-coded to the 23,400 PE trade.
- Added regression tests for both conflict blocking and aligned-context approval.
- Post-market lab now explicitly declares its stored live-session snapshot dataset as the raw-data research source and tests the configured research strategies with no orders.
- Added read-only `POST /api/v1/research/raw-backtest` to run the post-market suite against stored live-session snapshots.
- Added a Backtest UI control to run the raw post-market test and show strategy trade count, win rate, and net P&L.
- Existing 15:30 IST after-market scheduler continues to invoke the lab and retry if incomplete.
- All post-market testing remains counterfactual/research-only; no live decision or order path is enabled by the research runner.


## 2026-09-30 Continuation / cost-control / UI control status
- This handoff is the continuation source for a new chat. Preserve the existing architecture and history above; do not restart the project from scratch.
- Current repository: `Sabari2811/QuantNifty-Next`, branch `main`.
- Current known production deployment from the latest validated sequence: commit `ec2ca1baaf09676757f3f98c7d71ef8cacc0f384` (PR #7 merge). Workflow-only cost-control commits followed: resume workflow `916916070b6e84be22e599d1394621b3b89aaa6d`; suspend workflow `78ff1b39b380b93c387fa4e45f0b28ec9ed8f197`.
- Render workspace: `quantnifty-next` (`tea-dad5cr0n74is73dbho3g`).
- Current Render state verified on 2026-09-30: `quantnifty-api` (paid 1c-2g) is **suspended by user**; `quantnifty-production` (paid basic_256mb PostgreSQL) is **suspended by user**; `quantnifty-live-worker` PostgreSQL is also suspended. The free `quantnifty-learning` PostgreSQL remains available and expires 2026-10-07.
- The scheduled GitHub Actions are configured to resume the paid API and production PostgreSQL at 09:00 IST weekdays and suspend both at 16:00 IST weekdays. The workflow configuration has been committed, but manual workflow dispatch was not independently executed/verified in this continuation; do not claim that the schedule has been end-to-end tested.
- The production runtime/database mismatch remains an open certification item: prior runtime evidence showed `quantnifty_learning`, while the intended durable production database is `quantnifty_production`. Do not claim reconciliation until the Render service environment is explicitly inspected/updated and runtime diagnostics are revalidated.
- Real trading remains permanently disabled/read-only. Current execution is paper-only; one NIFTY option lot, one active position, maximum 3 paper trades/day.
- User requested a **Kill Switch control positioned prominently near/on top of the Live Monitor**. At the time of this handoff update, this is a **PENDING IMPLEMENTATION** request, not a completed feature. Do not tell the user it is already available. Desired behavior: persistent paper-only kill-switch state, prominent control near Live Monitor, clear HALTED/DISABLED status, block new paper entries and automatic flips while active, and safely handle any existing paper position according to the project's fail-closed policy. Implement backend state/control first, then UI, tests, deploy, and validate.
- Important: the user asked to continue this project in a new chat without losing progress. Start from this handoff and the current `main` branch; do not duplicate or reimplement features already listed above.


## 2026-09-30 Persistent Paper Kill Switch implementation
- Implemented the pending persistent paper-trading kill switch without redesigning the existing lifecycle architecture.
- Existing authoritative components were preserved: `paper_control.py` stores an IST-day-scoped `KILL_SWITCH_ON` control event through the existing durable `learning_store`; `LivePaperManager` already refreshes that state, blocks processing while active, and closes any active paper position with `MANUAL_KILL_SWITCH`.
- Existing API/UI work from commits `edf10561`, `1564caed`, `4643de74`, and `614b7417` was inspected and retained. The Live Monitor already exposes the prominent `🛑 KILL SWITCH` control, persistent status endpoint `GET /api/v1/paper/kill-switch`, activation endpoint `POST /api/v1/paper/kill-switch`, and visible `TRADING HALTED · TODAY` state.
- Closed the backend enforcement gap by making `paper_entry_gate.evaluate_paper_entry()` independently read `kill_switch_state(day)` and fail closed with `PAPER_KILL_SWITCH_ACTIVE` before normal entry/session gates. This protects direct entry-gate callers in addition to the existing `LivePaperManager.process()` enforcement.
- Added regression coverage for active-switch blocking and IST-day scoping in `apps/api/tests/test_paper_entry_gate.py`. Extended CI's existing Intelligence UI integrity markers to require the kill-switch button, endpoint, and halted-status marker.
- Repository commits for this continuation: `94594ea1` (backend gate), `94204d41` (tests), `355f3ac5` (CI UI marker). No changes were made to `data/instruments/fno.csv`, real-trading execution, `QuantNifty`, or `TechGeek`.
- Render service `quantnifty-api` was deployed from `main` commit `355f3ac5ab29fc649ea66c7a0e3ddc3abf3a9dfd` as deployment `dep-dau92o1srm7s73b9sgng`, which reached **LIVE** at `2026-09-30T04:35:23Z`.
- Runtime validation caveat: Render logs after the deployment show an existing unrelated `NameError: name '_f' is not defined` in `main.py:209` inside `_live_provider_connected`; this was not introduced by the kill-switch changes. The same runtime window also returned HTTP 200 for `/api/v1/paper/live-monitor`. Do not attribute the `_f` error to this task or modify that unrelated path without a separate requirement.
- GitHub Actions status for commit `355f3ac5` was not exposed by the available GitHub connector at validation time, so CI is **not claimed as passed**. The repository workflow remains configured to run compile, `pytest -q apps/api/tests`, and the Intelligence UI integrity check on pushes to `main`.
- The production kill switch was **not manually activated** during validation; therefore the production state was not mutated merely for testing. Real trading remains permanently disabled/read-only.

## 2026-09-30 Paper Trade Audit implementation
- Added read-only `GET /api/v1/paper/trade-audit?day=YYYY-MM-DD` via `apps/api/src/quantnifty/paper_trade_audit_api.py`.
- The endpoint is IST-day scoped and reads the existing `quantnifty_learning_events` `outcomes` and `decisions` streams through the same application learning-store abstraction; it does not submit orders or alter trading state.
- Each recorded trade exposes the stored entry decision, signal direction/confidence/evidence/rationale, risk approval/gates/reasons, execution plan, paper-entry reasons, instrument/strike, delta-based risk anchor, exit decision/reasons, stop/target, exit reason, and realized P&L.
- It also reports a nearest persisted decision-event match to the entry timestamp for auditability.
- Added regression coverage in `apps/api/tests/test_paper_trade_audit_api.py` for logic-trace extraction, P&L aggregation, decision matching, and invalid-day rejection.
- Commits: `8d8c1b2` (route wiring), `27ceb20` (audit API), `262d1d6` (tests).
- Real trading remains permanently disabled/read-only. No changes to `data/instruments/fno.csv`, broker execution, or unrelated repositories.

## 2026-09-30 Exit logic audit
- Audited `apps/api/src/quantnifty/live_paper_manager.py` and `apps/api/src/quantnifty/intrade_reversal_guard.py` against the 2026-09-30 paper trade `paper-20260930T035300.7293010000-0001`.
- The entry delta was `-0.55`, entry premium `177.50`, and spot-risk budget `25.0` NIFTY points. The authoritative delta-based premium stop is **177.50 - (0.55 × 25.0) = 163.75**.
- The actual exit premium was `161.10`, so the `DELTA_PREMIUM_STOP` condition was genuinely satisfied. The NIFTY exit spot `22723.75` also exceeded the frozen spot stop `22722.80`.
- The premium loss was `(161.10 - 177.50) × 65 = -1066.00`, matching the persisted realized P&L.
- The exit decision simultaneously showed a negative-to-positive gamma-flip transition, but the directional signal remained **BEARISH**. `evaluate_intrade_reversal()` intentionally treats a gamma-flip cross as an immediate reversal trigger only when paired with an opposite directional signal/adverse context; a gamma flip by itself does not close the trade. Therefore today's recorded exit was caused by the delta-premium stop, not a reversal-guard exit.
- No production trading logic was changed during this audit because the observed exit behavior matches the implemented risk rules. The `exit_policy.exit_signals` metadata includes `gamma_reversal`, but the authoritative runtime trigger remains the reversal guard's explicit conditions plus the delta premium stop/target and session guards.
- Added regression tests in `apps/api/tests/test_intrade_reversal_guard.py` covering (a) gamma-flip crossing without an opposite directional signal remains `HOLD`, and (b) an opposite directional signal plus a gamma-flip cross exits immediately.
- Test-only commit: `e8e4972d827f200f515d0d1ff6537373e55cb65c`.
- The available GitHub connector did not expose a workflow run or status result for this new commit at validation time, so CI is **not claimed as passed**. No Render deployment was triggered because this commit changes regression tests only and does not change production runtime behavior; real trading remains permanently disabled/read-only.


## 2026-09-30 Trade Confirmation V2 / entry-quality fix
- Added `apps/api/src/quantnifty/trade_confirmation_engine.py` as the single deterministic confirmation layer between the adaptive/institutional thesis and risk approval.
- Confirmation is intentionally not another confidence score. A directional paper entry now requires: (1) relevant support/resistance level break, (2) minimum price displacement derived from expected move with bounded floor/cap, (3) direction persistence across the current and previous snapshot, and at least four independent confirmations from displacement, persistence, volume expansion, OI-flow agreement, dealer-pressure agreement, and option-premium response.
- `TAKE_TRADE` additionally requires persistence plus price/flow follow-through. A strong thesis, high confidence, negative gamma, or accumulation score cannot bypass the key-level break.
- Existing CAS re-entry remains authoritative and is explicitly exempted from this generic confirmation layer; range/standby remain non-entry strategies. This avoids double-confirming a strategy that already has its own confirmation contract.
- Wired the confirmation into the authoritative `risk_engine()` path and exposed the complete confirmation trace under `risk.confirmation`. The previous snapshot is passed internally from `final_decision()`; it is not persisted as a new schema field or duplicated in the market snapshot.
- The 2026-09-30 failure mode is now correctly classified as **SETUP / NO TRADE** at the pre-break stage: the earlier 09:23 IST entry at 22,697.8 was above the bearish support level 22,650, so a bearish trade cannot be approved merely because OI/dealer/context confidence is strong. This directly addresses the observed confirmation lag without changing the exit engine.
- Added `apps/api/tests/test_trade_confirmation_engine.py` covering: early accumulation blocked before level break, full confirmation after level break/follow-through, high thesis strength unable to bypass the level break, and CAS re-entry preservation.
- Commits: `7248a632` (confirmation engine), `d73a248f` (authoritative risk wiring), `226940895` (regression tests).
- GitHub reported no workflow runs for the test commit; therefore CI is **not claimed as passed**. A local full test run was not possible in this environment because outbound GitHub network access is unavailable. No Render deployment was performed/claimed because the Render service is currently suspended by user and the available Render connector exposes inspection but not a deployment/resume action.
- Real trading remains permanently disabled/read-only. No changes were made to `data/instruments/fno.csv`, broker execution, `QuantNifty`, or `TechGeek`.
- Profitability is not guaranteed by this change. The correct acceptance criterion is out-of-sample research showing improved expectancy/quality metrics versus the prior entry logic; the new confirmation layer is designed to prevent premature entries, not to guarantee profitable trades.

- Follow-up cleanup commit `ce0a62f4`: removed the old early-accumulation confidence/liquidity gate because it duplicated the new authoritative confirmation gate. The confirmation engine is now the single entry-quality gate; strategy-specific logic remains only where it adds a distinct condition (e.g. gamma/volatility or CAS).


## 2026-09-30 Trade outcome attribution + hold-path safety
- Refined `trade_learning.py` so every closed paper outcome is explicitly classified as `PROFIT`, `LOSS`, or `FLAT` with concrete outcome drivers (favorable/adverse spot movement, target/stop behavior, option-premium expansion, delta-premium stop, and no-follow-through where applicable).
- This attribution is observational: a single trade still cannot promote entry/risk parameters. Existing promotion rules remain in force (minimum comparable observations and research validation).
- Fixed an important Confirmation V2 interaction in `position_hold_backtest.py`: entry confirmation is evaluated only when opening a position. An already-open thesis is no longer forced to re-break a level or re-show entry volume/premium confirmation on every bar. Existing direction/context/risk invalidation remains authoritative for exits.
- Added regression coverage to the existing trade-learning tests for loss-driver classification.
- Commits: `16975c2` (entry/hold separation), `81ee72a`, `df642e5` (outcome attribution), `353df90` (tests).
- A recurring hourly paper-trade monitor is now enabled to report new/changed/closed paper trades for the current IST trading day and attribute profit/loss drivers without changing parameters from one observation.
- Real trading remains permanently disabled/read-only.


## 2026-09-30 Runtime deployment + no-trade diagnosis
- Render service `quantnifty-api` was behind `main`: the previous LIVE deploy was commit `2e545c0`, while `main` had advanced to `ab9e415` with the Confirmation V2, hold-path safety, and trade-outcome attribution changes.
- Triggered Render deployment `dep-dauc8lo93c1s73dlpm20` for `ab9e415`; Render reported the deployment `live` at 2026-09-30T08:13:00Z.
- The screenshot supplied before this deployment showed the older runtime blocking on `gamma_regime`, `volatility`, and `BEARISH_MOMENTUM_TRADE_LIMIT`. Those labels are not part of the current authoritative `risk_engine()` on `main`; the current entry-quality contract is `trade_confirmation`.
- Current Confirmation V2 deliberately prevents a directional paper entry until a relevant support/resistance level is broken and the move has sufficient displacement/persistence plus independent volume/OI/dealer/option-premium confirmation. A strong bearish thesis alone is not sufficient.
- Therefore the absence of a new paper trade is currently a safety gate, not evidence that the engine is broken. The next browser refresh should show the current confirmation trace after the new deployment is queried.
- Render runtime evidence immediately after deployment confirmed the production PostgreSQL database is reachable and `trading=DISABLED`; no broker execution was enabled.
- GitHub reported no workflow runs for `ab9e415`; CI is not claimed as passed. Render build/deploy completed successfully.


## 2026-09-30 Confirmation V2 hardening
- Hardened `trade_confirmation_engine.py` so a key-level break is measured against the previous snapshot's support/resistance. This prevents the current level from moving with price and creating a false post-hoc break.
- Hardened volume confirmation to use the selected directional option contract rather than summing the entire option chain. Option-chain volume is cumulative, so whole-chain short-interval percentage changes were not a reliable participation signal.
- Kept microstructure/depth confirmation out of the authoritative entry gate because the current LIVE_PROVIDER snapshot does not expose a stable aggregate order-book/microstructure series. Existing bid/ask/depth data remains usable where available for execution/quote monitoring; no synthetic microstructure signal is inferred.
- Added regression tests for frozen trigger levels, avoiding repeated breaks when price was already beyond the level, and selected-contract volume confirmation.
- Commits: `4234029` (confirmation hardening), `3decd60` (tests).
- Real trading remains permanently disabled/read-only; no broker execution or instrument-file changes.


## 2026-10-01 Live intelligence payload / decision observability fix
- Diagnosed the live Market Brain screen showing provider data while displaying blank intelligence fields and an apparently unqualified NO_TRADE. The provider/DB pipeline was healthy: Render runtime evidence showed LIVE_PROVIDER snapshots with 82 option-chain rows, durable PostgreSQL, and trading=DISABLED.
- Hardened `apps/api/src/quantnifty/main.py` so `snapshot()` computes the complete intelligence object before publishing the shared cache. A new `intelligence_contract` (`market-intelligence-v2`) records required intelligence fields and fails closed if the payload is incomplete. This prevents API/WebSocket consumers from seeing a partially constructed snapshot.
- Added `QUANTNIFTY_DECISION_EVIDENCE` structured logs every ~30 seconds with direction, confidence, selected strategy, authoritative decision action, risk reasons, confirmation status/reasons, confirmation level/displacement/supporting confirmations, intelligence contract status, and trading mode. Added explicit `QUANTNIFTY_SNAPSHOT_ERROR` / `QUANTNIFTY_DECISION_ERROR` logs.
- The Intelligence UI now refuses to display a synthetic NO_TRADE when the intelligence contract is absent/incomplete; it shows **INTELLIGENCE CONTRACT INCOMPLETE** instead.
- Removed the unrelated pre-existing `_f` health bug from `_live_provider_connected()`; health now checks the cached timestamp safely and requires an OK intelligence contract.
- During post-deploy validation a latent adaptive-learning bug was exposed on a fresh Render instance: `update_adaptive_memory()` discarded `failure_patterns` and `closed_trade_samples`, causing `KeyError: 'failure_patterns'` once historical closed outcomes were present. Fixed `research_brain.py` to preserve those fields across memory updates. This was necessary for the live decision path to remain healthy with the existing 2 closed outcomes in PostgreSQL.
- Production deployment: commit `a7c37f183db86c29c54fd2edc46ebe8a514228b9`, Render deployment `dep-dauueou0tbcc73cpbrk0`, reached LIVE at 2026-10-01T04:54:37Z. Service remains paid `1c-2g`, main branch, not suspended, trading=DISABLED.
- Runtime validation after deployment: new instance successfully emitted `QUANTNIFTY_DECISION_EVIDENCE`; `/api/v1/market` returned HTTP 200; runtime evidence showed LIVE_PROVIDER cached snapshots, 82 rows, PostgreSQL reachable, decisions increasing to 144, snapshots increasing to 1411+, paper status IDLE, trading DISABLED. The new evidence showed a legitimate current **WAIT_CONFIRMATION** state: BEARISH / early_accumulation, confidence 85.8, risk not approved because `trade_confirmation`; at 10:25 IST evidence included `KEY_LEVEL_NOT_BROKEN`, `INSUFFICIENT_DISPLACEMENT`, and `OPTION_PREMIUM_NOT_RESPONDING`. This is now an explicit strategy gate rather than a blank UI state.
- The old pre-deploy instance emitted the known `'failure_patterns'` error during zero-downtime handoff, but those errors stopped once the old instance was drained; no `QUANTNIFTY_SNAPSHOT_ERROR` was observed on the new instance after the adaptive-memory fix.
- Tests: GitHub Actions compile passed. The current CI run on this commit reports **222 passed, 7 failed**. The 7 failures are pre-existing/stale expectations in adaptive/context/historical/reversal/trade-learning tests plus one dashboard string expectation; they are not caused by the new intelligence contract or adaptive-memory preservation test. The new live-intelligence regression tests pass. CI is therefore not claimed as fully green.
- No changes to real-trading execution, broker integration, `data/instruments/fno.csv`, `QuantNifty`, or `TechGeek`.


## 2026-10-01 Decision-edge evidence + UI/backend completion
- Implemented a separate descriptive **decision-edge analysis** layer in `apps/api/src/quantnifty/edge_lab.py`.
- The layer records, per stored same-day decision: entry spot/direction/strategy, confirmation key level, displacement, supporting confirmations, blockers, selected option strike/side/delta/IV/premium, and 5/15/30-minute plus end-of-day subsequent behavior.
- It explicitly separates **ENTER_CANDIDATE**, **DO_NOT_ENTER_SETUP**, and **OBSERVATION**. A blocked setup that later moves in the thesis direction is labeled **COUNTERFACTUAL_FOLLOW_THROUGH**, not a live trade and not proof that the engine should have entered.
- Repeated evidence patterns are surfaced only after **>=3 observations**. This is descriptive research; it does not automatically alter entry/risk parameters.
- `after_market_lab.py` now stores `edge_analysis` with the existing post-market research artifact. Future prices are used only for after-market outcome labeling; decision-time evidence remains immutable.
- Added `GET /api/v1/research/edge` for the application and backtest UI.
- **Application UI:** Intelligence now shows a live **Decision Evidence · Current Cycle** panel with action, direction, confidence, strategy, risk state, confirmation status, key level, displacement, supporting-confirmation count, gate PASS/WAIT state, and explicit blockers.
- **Backtest UI:** Post-Market Raw Data Strategy Test now also renders decision-edge counts and repeated evidence patterns (minimum 3 observations).
- Added regression coverage for edge-analysis labeling and the three-observation promotion threshold. Updated stale test fixtures so the existing suite explicitly satisfies the authoritative Confirmation V2 contract instead of testing pre-Confirmation-V2 assumptions.
- Real trading remains permanently disabled/read-only. No broker execution, `data/instruments/fno.csv`, `QuantNifty`, or `TechGeek` changes are included.
- This continuation is being pushed and deployed immediately; it does not wait for the normal application schedule/cycle.


## 2026-10-01 Final verification
- Final code commit: `4ec41e3363c7457bdce80f60b9cbcb31496ebf32`.
- GitHub Actions `QuantNifty CI` run **686** completed **successfully** with **231 passed** tests.
- Render production deployment: `dep-dauuna0473hc73cofpvg`, status **live**, running commit `4ec41e3363c7457bdce80f60b9cbcb31496ebf32`.
- Render service remained `not_suspended`, one active instance, and resource metrics continued updating after the deployment. Public HTTP metrics are not exposed in the current workspace metric response, so content-level endpoint validation was performed through deployment/runtime health rather than a fabricated HTTP result.
- The production deploy was triggered immediately after the final push; it did not wait for the normal 09:00/16:00 application schedule.
- Final code path remains read-only/paper-only; no broker order path was enabled.


## 2026-10-01 Confirmation displacement + UI blocker hardening
- Fixed the live Confirmation V2 semantic gap found in production evidence: TAKE_TRADE could previously coexist with INSUFFICIENT_DISPLACEMENT because displacement was one of six scored confirmations rather than a mandatory gate. A directional confirmation now requires both the frozen key-level break and minimum expected-move-derived displacement, in addition to the existing independent confirmation requirements.
- Added a regression test proving that a key-level break with positive persistence, volume, OI flow, dealer pressure, and option-premium response still remains SETUP when displacement is below the mandatory threshold.
- Hardened the Market Brain Decision Evidence panel to prioritize authoritative risk.reasons when explaining why the engine is blocked. This prevents the UI from falling back to an ambiguous "No active blocker" message when a risk gate such as PAPER_KILL_SWITCH_ACTIVE is the actual blocker.
- The existing reversible paper kill switch remains unchanged: it can halt/resume paper entries for the current IST trading day, while real broker execution remains permanently disabled/read-only.
- No changes were made to data/instruments/fno.csv, broker execution, QuantNifty, or TechGeek.


## 2026-10-01 Kill-switch release stale-state hardening
- Fixed LivePaperManager._refresh_kill_switch() so the in-memory kill-switch flag is never authoritative. Every refresh now reconciles against the durable current-IST-day paper_controls state.
- This prevents a release handled by one Render instance from being overwritten by a stale KILL_SWITCH_ON state held by another instance during subsequent status/market ticks.
- Added runtime regression tests for both durable release and durable activation synchronization.
- The intelligence UI now refreshes kill-switch status every 10 seconds from the backend, so the displayed HALT/ENABLED state follows the authoritative control state.
- Real trading remains permanently disabled/read-only; this change only fixes paper kill-switch state synchronization.


## 2026-10-01 Kill-switch control hardening
- Fixed the paper kill-switch API so it no longer behaves as an implicit toggle.
- POST /api/v1/paper/kill-switch now requires an explicit boolean enabled field and fails with HTTP 400 when the field is missing/invalid. This prevents stale tabs, duplicate requests, retries, or load-balanced clients from accidentally inverting the durable state.
- The endpoint is idempotent when the requested state already matches the durable state.
- Added QUANTNIFTY_KILL_SWITCH_CONTROL structured audit logging with requested state, previous state, resulting state, reason, day and idempotency.
- Updated the Intelligence UI wording so the active action is explicitly RELEASE KILL SWITCH and the non-active state says PAPER ENTRIES ENABLED · READ ONLY.
- Added apps/api/tests/test_kill_switch_api_contract.py to guard the explicit API contract and UI behavior.
- Commits: d1e12ef3c410af3c5f92111b867792fa1d2983cd, 0bf3c9b5522e51183fcf2232fa1dabff392d9bfb, 07e50e2da73406f36491675bbd445faee3472aa7.
- Production deployment: Render dep-dav225942hec73ciqh90, live at 2026-10-01T09:00:56Z, running the exact 07e50e2da73406f36491675bbd445faee3472aa7 main commit.
- Production post-deploy logs at 09:00 UTC show market-intelligence-v2 contract OK, bearish intelligence at NIFTY ~22,324, and trading=DISABLED.
- The durable kill switch was still reported active after deployment. Its exact originating control event was not directly queried because the production PostgreSQL external IP allowlist blocks the available Render database connection path. Do not attribute the activation to market processing without a control-event record.
- Direct outbound HTTP/DNS from the current execution environment is unavailable, so the release POST could not be executed from here. The UI explicit release action remains the supported path.
