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
- **Normal paper strategy:** entries during the normal session; normal positions must close before the 15:15 cash-session influence window.
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
- `live_paper_manager.py` — one-lot sizing, paper-only lifecycle, recovery guard and read-only exits.
- `after_market_lab.py` — independent raw-snapshot research track.
- `after_market_scheduler.py` — starts post-market research at **15:30 IST** and retries until a durable completed stored-day result exists.
- `.github/workflows/render-service-resume.yml` — Render resume at 09:00 IST weekdays.
- `.github/workflows/render-service-suspend.yml` — Render suspend at 16:00 IST weekdays.
- `docs/RENDER_RUNTIME.md` — authoritative Render runtime/cost boundary.

## Post-market learning boundary
`after_market_lab.py` loads only the day's raw market snapshots and runs the configured research strategies counterfactually. It records `POST_MARKET`, `RAW_MARKET_SNAPSHOTS`, `READ_ONLY_AFTER_MARKET`, `research_only=true`, and `orders_placed=0`. It does not access live decision, paper-trade or live-outcome data. Any resulting policy information is for future deterministic adaptation and never changes an in-progress live decision.

## Render production architecture
Required production resources for this project:

1. `quantnifty-api` — paid application compute, active only 09:00-16:00 IST weekdays.
2. `quantnifty-production` — PostgreSQL, kept available for durable learning, paper and research history.
3. Separate `QuantNifty` services/workers are unrelated and must remain disabled.

Render service ID: `srv-dad5e767bikc739oighg`.

GitHub Actions use the non-secret service ID and the repository secret `RENDER_API_KEY`. The secret must never be committed or placed in source. Scheduler cron is UTC: `30 3 * * 1-5` for 09:00 IST resume and `30 10 * * 1-5` for 16:00 IST suspend. Scheduler jitter must not widen the application/provider windows because the application is fail-closed outside its defined windows.

**Important audit note:** `render.yaml` describes a free Render web service/database configuration that does not by itself prove the current production resource/plan. Do not treat that file as proof that the deployed `quantnifty-api` is paid or that the production database is `quantnifty-production`; verify the actual Render service/database state before claiming deployment parity.

## Validation status and current gaps
The repository contains extensive unit/contract tests for market boundaries, application runtime, cash strategy, paper lifecycle, learning isolation, UI telemetry, research and safety. The latest code changes added a regression test asserting post-market scheduling starts at 15:30 IST.

Local test execution could not be performed in this environment because outbound GitHub cloning/DNS was unavailable. The repository CI workflow is configured to compile the API and run `pytest -q apps/api/tests` on Python 3.11.

Production validation is still a live/deployment task: verify the actual Render service state, latest deploy, health/status endpoints, PostgreSQL durability, live-provider isolation, read-only trading state, and the 16:00 suspend / 09:00 resume lifecycle. Do not claim the Render scheduler is validated merely because its workflow files exist; a successful manual/scheduled run using the configured `RENDER_API_KEY` is required.

## Audit trail for this continuation
The latest audited `main` before continuation was commit `11e8908c13eeee1408a7b532a541a3bd6f7c99f8`. The continuation changed the post-market scheduler from 15:35 to **15:30 IST** and added a regression test. Runtime documentation was aligned to the same policy. No secrets or `data/instruments/fno.csv` were changed.

## Non-negotiable future rules
Always follow:

`inspect -> identify gaps -> implement -> test -> commit -> deploy -> validate -> update PROJECT_HANDOFF.md`

Never redesign the architecture without an explicit requirement. Never enable real trading. Never carry paper positions overnight. Never use future market outcomes in live decisions. Keep post-market research independent. Keep PostgreSQL available. Suspend/resume the **actual Render application service**, not merely the Python process.
