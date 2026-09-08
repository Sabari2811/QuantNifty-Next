# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-08  
**Branch:** `main`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production:** https://quantnifty-api.onrender.com  
**Backtest:** https://quantnifty-api.onrender.com/backtest  
**Execution:** READ-ONLY; no real orders; `orders_placed=0`, `trading_enabled=false`.

## Finalized product plan
QuantNifty is a **Live Adaptive Brain + After-Market Research Lab**.

- Live decisions use only data available at decision time.
- Adaptive Brain: 09:20–15:15 IST.
- 15:15–15:30 IST: normal Brain stops; only already-produced live CAS may authorize `cas_reentry`.
- 15:30 IST: decisions stop and open paper trades must be closed as `SESSION_CLOSE`.
- Learn continuously from live market observations; the planned learning/review horizon is approximately three months, with no historical-data startup gate.
- Store live snapshots, decisions and paper outcomes separately from counterfactual research.
- After close, replay **that stored live day only** and test the full research strategy universe.
- Only closed, validated, future-safe outcomes may influence future policy.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Risk -> FinalDecision -> ExecutionPlan -> Paper Outcome -> Learning Store`

Core ownership: `main.py` provider/analytics/API/live refresh; `institutional_engine.py` signal/risk/FinalDecision/ExecutionPlan; `research_brain.py` adaptive regimes/selection/accumulation/exits and explicit research overrides; `session_policy.py` session/CAS; `decision_validation.py` validation; `replay.py`/`backtest.py` deterministic research; `historical.py` snapshot normalization/provenance diagnostics only; `recording_loader.py`/`recording_api.py` recorder/replay; `adaptive_learning.py` policy helpers; `learning_store.py` durable learning events; `after_market_lab.py` full-day research; `after_market_scheduler.py` orchestration; `paper_trade_tracker.py` read-only outcome lifecycle; `live_paper_manager.py` live outcome integration/restart recovery; `scenario_engine.py` scenario extraction; `research_strategy_runner.py` canonical research strategy routing; `adaptive_policy.py` policy validation; `policy_runtime.py` persistence/next-session loading; `web/backtest.html` UI.

Governance: FinalDecision is authoritative; Risk owns permission; ExecutionPlan never submits orders; actual and counterfactual experience remain separate; replay reuses the canonical pipeline; time must remain deterministic/injectable.

## Strategy universe
`directional`, `gamma_blast`, `early_accumulation`, `transition`, `range`, `breakout_watch`, `standby`, `cas_reentry`, `adaptive`.

Live API remains intentionally restricted to `directional`, `gamma_blast`, and `adaptive`. The after-market research runner covers the seven research strategies plus adaptive and routes explicit research modes through the canonical Adaptive Brain/FinalDecision/Risk pipeline. This does not weaken live safeguards.

## Adaptive Brain
Early accumulation uses near-ATM OI expansion, premium behavior, active volume, quiet spot, controlled IV and expected-move-relative premium. States are `EARLY_ACCUMULATION`, `WATCH_ACCUMULATION`, `NO_CLEAR_ACCUMULATION`. Entry confirmation uses `EARLY_ACCUMULATION_CONFIRMATION` / `ACCUMULATION_THEN_BREAKOUT_CONFIRMATION`. Adaptive exit considers capital protection, favorable move, exhaustion/gamma reversal, profit lock and trailing. Current adaptive exit is primarily spot-based; richer option-premium/IV/Greeks/liquidity confirmation remains optional research work. No exact top/bottom prediction is claimed.

## Learning / storage
Live refresh creates/updates a read-only paper trade lifecycle through `live_paper_manager.py`: one active hypothetical trade at a time, restart recovery from persisted open outcome, MFE/MAE tracking, option-premium P&L when the selected leg is available, spot proxy fallback, and session-close closure. No broker order is submitted.

`learning_store.py` supports PostgreSQL through `QUANTNIFTY_DATABASE_URL` or `DATABASE_URL`, with filesystem fallback. PostgreSQL connections explicitly require TLS (`sslmode=require`) because Render Postgres enforces SSL/TLS. Render has Postgres instance `quantnifty-learning` in Singapore. Render wiring is implemented declaratively in `render.yaml`: the API service receives `DATABASE_URL` from the database's internal `connectionString`, and the database is declared in the Blueprint as the existing `quantnifty-learning` resource. No credential or connection string is committed.

Every live session continuously stores the live market snapshot and live decision evidence. Closed read-only paper outcomes store strategy, direction, entry/exit, P&L when available, MFE/MAE, exit reason and execution-disabled markers. The stored snapshot preserves the canonical market payload rather than training from an external historical bootstrap.

After-market training runs automatically on trading weekdays at/after 15:35 IST. It loads only the completed same-day stored live snapshots, runs the full research strategy universe, extracts deterministic scenarios, validates/persists the future-safe policy candidate, and then persists one complete daily research/training record containing the strategy results, rankings, scenarios and policy reference. A scheduler day is marked complete only after the lab returns `COMPLETED`; `NO_DATA` and exceptions remain retryable. On service restart, a durable completed research record prevents duplicate daily training.

## Learning source policy — finalized
**Historical learning is removed completely.** There is no 252-trading-day gate, 365-calendar-day gate, historical bootstrap requirement, or historical performance requirement for Adaptive learning.

The only learning sources are:

1. **LIVE_PROVIDER:** live market data captured during the current/future market session. Live decisions may use only information available at that timestamp.
2. **STORED_DAY:** the immutable live data recorded during that same completed trading day, used after market close for replay, counterfactual research, scenario extraction and future-safe policy generation.

`data_Review.txt` and any other pre-existing historical recordings are **replay/reference evidence only**. They must not train, seed, initialize, promote, or influence the live Adaptive Brain or its policy memory.

The planned three-month READ-ONLY learning/review period begins from the next live market session. Evidence accumulates naturally from live sessions and their post-market stored-day research. A large historical dataset is not a prerequisite to start learning.

The legacy `adaptive_learning.py` policy helper is aligned with this rule: it accepts only live-provider evidence for policy-building, has no one-year gate, and rejects pre-existing `RECORDED_HISTORICAL` provenance. Live-policy validation also rejects historical provenance and still fails closed on future training timestamps.

## Finalized daily learning workflow

### During market hours
- Capture the live provider snapshot on every refresh.
- Preserve the complete available market payload, including option-chain fields and analytics available from the provider (OI, previous OI, volume, IV, bid/ask and Greeks such as Delta/Gamma/Theta/Vega where supplied).
- Run the canonical Adaptive Brain → Signal → Risk → FinalDecision path using only current/previous live observations.
- Persist the decision separately from the snapshot.
- Maintain the read-only paper trade lifecycle and persist closed outcomes including P&L/MFE/MAE where determinable.

### After market close
- At/after 15:35 IST, freeze the completed same-day stored observations for research.
- Run all configured research strategies against the same stored-day information.
- Calculate strategy results and trade-level counterfactuals.
- Generate and persist scenarios, including failed/negative cases.
- Validate and persist a future-safe policy candidate.
- Persist a complete daily training/research event only after policy/scenario enrichment.
- Never rewrite the original live decision.

### Accumulation
Each trading day adds new events to the durable learning store. Existing days are retained; learning is incremental rather than overwritten. PostgreSQL is the production durability target, with JSONL fallback for local/testing operation.

## Completed
- Canonical decision/risk/execution architecture.
- Adaptive selector/regimes.
- Early accumulation/breakout confirmation.
- Adaptive exhaustion/trailing exit.
- Day-by-day adaptive backtest memory.
- Session/CAS policy.
- Data/decision validation.
- Replay/backtest consistency.
- Adaptive API/UI and multipart handling.
- **Removed the one-year historical learning gate.**
- Live learning store and live Adaptive decision recording.
- After-market lab and weekday scheduler.
- PostgreSQL-capable learning backend.
- Learning-store and lab regression tests.
- Read-only paper outcome tracker + MFE/MAE/boundary tests.
- Scenario extraction engine + tests.
- Versioned adaptive policy validation contract + promotion-gate tests.
- Live paper outcome integration with restart recovery.
- Full after-market strategy coverage through the canonical Adaptive pipeline.
- Scenario persistence through the durable research event store.
- Future-safe policy persistence and prior-day loading.
- Render Blueprint wiring for secure Postgres connection injection.
- **Daily after-market training persistence ordering fixed:** the durable daily research event now includes policy/scenario enrichment.
- **Daily scheduler reliability fixed:** successful completion is required before a day is marked trained; failed/no-data runs remain retryable; persisted completed days are recognized after restart.
- Added scheduler completion-state regression tests.
- Added complete after-market training persistence regression test.
- **Removed the remaining legacy historical-learning dependency from `adaptive_learning.py`; tests now enforce live-only policy construction and rejection of pre-existing historical recordings.**
- **Updated `APP_ARCHITECTURE.md` to make the live-only/same-day learning-source policy, daily persistence/retry semantics, and no-historical-bootstrap rule authoritative.**
- **Fixed Render PostgreSQL TLS connection handling:** the learning store now explicitly uses `sslmode=require` for PostgreSQL connections.
- **Added production evidence assertion:** `/api/v1/status` must report PostgreSQL learning durability and database availability, preventing a production deployment from being declared healthy while silently falling back to filesystem storage.
- **Added temporary live-validation runtime harness:** `.github/workflows/live-validation-harness.yml` keeps the current free Render web service awake during today's validation window and polls `/health` and `/api/v1/status`, recording live snapshot freshness, PostgreSQL durability, database availability and paper-trade status. It is READ-ONLY and never submits orders.
- **Hardened live-validation evidence:** the harness now performs a real `/api/v1/market` provider read each cycle, requires `LIVE_PROVIDER` data with a valid spot and option-chain rows, requires a fresh cached snapshot (`<=90s`), requires PostgreSQL durability/database availability, and fails closed if these conditions are not met. This removes the previous false-green state where a healthy web process could be mistaken for successful live ingestion/learning.
- **Added local live-validation bootstrap:** `.env.example` documents the required non-secret local runtime variables, and `scripts/run_local.ps1` installs the existing API package and starts the existing FastAPI app in READ-ONLY mode on `127.0.0.1:8000`. It requires both `INDSTOCKS_API_TOKEN` and `DATABASE_URL` so local validation does not silently fall back to filesystem learning storage.

## Verification state
Implementation commits for the finalized daily-learning work:
- `98ff9c041e31fdccbee70fbf875b470a816f1b83` — retryable/durable scheduler completion.
- `6244fb3fb3f342d9adae7e3ac9f9954bfd55eb11` — complete daily after-market training persistence.
- `46a6f10961fbf7e049aeb2057ac8a66aa76ce163` — scheduler completion regression tests.
- `3d69f0ee6472a6dcd82d6f63d380823cffcd54ba` — after-market persistence regression test.
- `4c566ec94b036d896c2f202eb8a0936cd9866492` — legacy historical-learning dependency removed from adaptive policy helper.
- `d23da5dde3f3a1ba9c957fb949fb6d86c2e6f8ec` — adaptive policy tests aligned with live-only learning.
- `1b4c334a5b52002bf0b9aa697bc2711aef788619` — architecture documentation aligned with finalized learning plan.
- `1fbd51a7209fa6d7da3c4357ef64e2a170a98a3b` — Render PostgreSQL TLS connection fix.
- `50588241c9f029f0c3072dd85c02a3023d98807b` — production PostgreSQL durability evidence assertion.
- `3bf1662ae8e964df4a624c3f54d9816b7c07977f` — temporary live-validation runtime harness.
- `577f2e905e6ce886b1c66c3b8ff5b602bc8bc244` — strict live-provider/snapshot/learning validation harness.
- `0515b828573bea57b4cfad4c1d8f39cc134669e3` — safe local runtime environment template.
- `ec6078b36d735088a6b6bcc1b38b22afbeee4818` — read-only local runner.

Verification observed for the current code path:
- CI run `34150970969` completed **success** for the current production code before the runtime harness addition.
- Backtest Gate run `34150970991` completed **success** for the same production code.
- Render Postgres instance is `quantnifty-learning`, status `available`, PostgreSQL 18.
- The latest Render deployment for commit `a0b585e52a8c772e4533b24f2786c4d57c0ace33` is live.
- Before the harness fix, Render runtime logs and service metrics showed no runtime evidence during today's market window. The service is configured as a **Free** web service, and Render documents that Free web services spin down after 15 minutes without inbound traffic. This is incompatible with an always-on background market recorder unless the service is kept active or moved to a paid always-on compute plan.
- The current `render.yaml` declares `/health`, but the existing Render service configuration reported an empty health-check path; Blueprint synchronization has not been independently confirmed. The application itself exposes `/health` and `/api/v1/status`.
- Render deployment `dep-daft1ldbedkc73fsk4q0` for commit `88287cb0e42ac7ec9e7e33d0750adbcea9b09983` is **LIVE**. Runtime logs show successful `/health` and `/api/v1/status` requests every minute from the validation harness.
- A direct Render SQL diagnostic query currently fails because the Render SQL connector itself does not negotiate the database TLS requirement; this does **not** prove application-side PostgreSQL failure because `learning_store.py` explicitly uses `sslmode=require`. The production application must therefore be verified through `/api/v1/learning/status`, which uses the application's TLS-capable connection path.
- Local validation is now supported by the repository, but it has **not yet been run on the user's Windows machine**, so no local live-ingestion or PostgreSQL evidence is claimed yet.

## Remaining verification / operational work
1. Run the local READ-ONLY app on the user's Windows machine with a real `INDSTOCKS_API_TOKEN` and the Render Postgres external connection string.
2. Verify local `/health`, `/api/v1/market`, and `/api/v1/status` during the next live market session.
3. Verify production `/api/v1/status` learning block reports `durability=POSTGRESQL` and `database_available=true` through the application connection path.
4. Verify genuine live snapshots/decisions/paper outcomes are being persisted in PostgreSQL.
5. Verify `quantnifty_learning_events` creation and event counts after genuine live data arrives.
6. Verify persistence across service restart/deploy.
7. Verify local live recorder → paper outcomes → after-market lab → policy persistence/load with PostgreSQL enabled.
8. Verify the 15:15–15:30 CAS window behavior from live evidence where a valid CAS signal exists; otherwise record the fail-closed standby evidence.
9. Verify the automatic after-market lab at/after 15:35 IST using today's stored live data only.
10. Verify the future-safe policy is persisted and loaded on the next eligible session.
11. Start/continue the READ-ONLY learning/review period using **live data + same-day post-market stored data only**.
12. Cleanup the temporary validation harness after today's evidence is captured, unless an always-on production compute plan is selected.
13. Cleanup remaining deprecation/unused-import warnings.

## Non-negotiable rules
- Never commit `data_Review.txt` or use it as a learning source.
- Never commit API tokens/secrets.
- Never use future information in live decisions.
- Never use after-market results to modify the already-issued live decision.
- Never represent counterfactual research as actual trading.
- Never enable real order execution during learning/validation.
- Every implementation change updates this handoff.

## Continuation
Read this file and `APP_ARCHITECTURE.md`, inspect `main`, CI and Render, then continue from verification/operational work. Do not restart or redesign. Only mark an item complete after the relevant tests and deployment/production evidence support it.
