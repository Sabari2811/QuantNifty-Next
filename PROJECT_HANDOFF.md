# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-17  
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
