# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-09  
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
- Learn continuously from live market observations; there is no historical-data startup gate.
- Store live snapshots, decisions and paper outcomes separately from counterfactual research.
- After close, replay **that stored live day only** and test the full research strategy universe.
- Only closed, validated, future-safe outcomes may influence future policy.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Risk -> FinalDecision -> ExecutionPlan -> Paper Outcome -> Learning Store`

Core ownership: `main.py` provider/analytics/API/live refresh; `institutional_engine.py` signal/risk/FinalDecision/ExecutionPlan; `research_brain.py` adaptive regimes/selection/accumulation/exits and explicit research overrides; `session_policy.py` session/CAS; `decision_validation.py` validation; `replay.py`/`backtest.py` deterministic research; `historical.py` snapshot normalization/provenance diagnostics only; `recording_loader.py`/`recording_api.py` recorder/replay; `adaptive_learning.py` policy helpers; `learning_store.py` durable learning events; `after_market_lab.py` full-day research; `after_market_scheduler.py` orchestration; `paper_trade_tracker.py` read-only outcome lifecycle; `live_paper_manager.py` live outcome integration/restart recovery; `scenario_engine.py` scenario extraction; `research_strategy_runner.py` canonical research strategy routing; `adaptive_policy.py` policy validation; `policy_runtime.py` persistence/next-session loading; `web/backtest.html` UI; `paper_ledger_api.py` read-only paper ledger and session decision summary.

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
- **Added production runtime observability:** `runtime_observability.py` exposes `/api/v1/runtime-evidence` and emits a structured `QUANTNIFTY_RUNTIME_EVIDENCE` heartbeat every 30 seconds containing cached LIVE_PROVIDER snapshot timestamp/spot/rows, data-integrity state, PostgreSQL learning durability/counts and paper-trade state.
- **Added Render-compatible startup observability:** `sitecustomize.py` attaches the runtime evidence heartbeat to the existing `uvicorn quantnifty.main:app` process without changing trading behavior. It also records a safe PostgreSQL connectivity diagnostic with credentials redacted.
- **Added read-only paper ledger API:** `/api/v1/paper/ledger` exposes closed paper trades for an IST trading day with entry/exit, quantity, exit reason, MFE/MAE, P&L basis and aggregated P&L, plus the same-day decision count/approval and signal distribution. Open trades are excluded from realized P&L. No broker charges are fabricated; `net_pnl` equals the stored paper P&L proxy until a broker cost model is explicitly implemented.
- Added paper-ledger aggregation regression test.

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
- `c39b2d128622f585b1770411fe36f56f5208dba6` — runtime observability endpoint and structured evidence heartbeat.
- `893892a3a468f249793333d2a2ab006ade4ec4cd` — Render Blueprint start command updated to run the observability wrapper.
- `3a7e2c8d8c869f8fd5966a8ad9adc0c6378c9a9d` — Render-compatible startup observability hook.
- `068a08b3e9cf11a9a33e45e60dae808d2c4fba81` — safe PostgreSQL connectivity diagnostic.
- `b982289f92c1be806a9041023295b1b1de2bb4e6` — read-only paper ledger API.
- `ecc040c200776311330291cfc2ca2b0036ba1d8e` — production app route wiring for paper ledger.
- `1c4bbab78a9716542bf2e40fe94426fc5c63be71` — paper ledger aggregation regression test.

## Live verification evidence — 2026-09-09
The production service is now producing application-owned runtime evidence during the live market session.

Verified from Render runtime logs:
- `cached_snapshot=true`
- `data_integrity=LIVE_PROVIDER`
- `rows=82`
- live NIFTY spot observed at `23546.0`, then `23549.45`, then `23560.7`, then `23556.75`
- snapshot timestamps advanced from `08:29:13Z` through `08:34:05Z`
- `paper_trade_status=OPEN`
- `trading=DISABLED`

Later runtime evidence also showed PostgreSQL reachable with `durability=POSTGRESQL`, numeric decision/snapshot counters and `outcomes=2` during the live session.

### Paper ledger verification surface
The production app now exposes a read-only ledger endpoint at `/api/v1/paper/ledger`. It returns only `CLOSED` outcomes for the requested IST day, excludes open trades from realized P&L, and includes the same-day decision summary. P&L is explicitly labeled as a paper proxy: option-premium P&L is used when both entry/exit option prices are available, otherwise the existing spot proxy is used. Broker charges are currently `0.0` because no cost model has been implemented; this is not presented as broker-realized net P&L.

### PostgreSQL blocker found and diagnosed
The same production evidence showed:
- `learning.configured=true`
- `durability=POSTGRESQL_CONFIGURED_UNAVAILABLE`
- `database_available=false`

The new safe diagnostic identified the exact cause: `DATABASE_URL` currently contains the literal text `${{quantnifty-learning.DATABASE_URL}}` rather than a resolved Postgres connection URL. The Render environment-variable API accepted that literal value; the application then correctly rejected it as invalid connection information. No secret was exposed.

Render's documented Blueprint mechanism is `fromDatabase: { name: quantnifty-learning, property: connectionString }`, which resolves the internal connection string during Blueprint sync. The manually managed service has not synchronized that Blueprint value, so its current `DATABASE_URL` must be replaced in the Render service Environment settings with the actual internal Postgres connection URL (do not paste the secret into chat).

The Render Postgres instance itself is `available`, but it remains on the Free plan and is scheduled to expire 2026-10-07.

## Remaining verification / operational work
1. Replace the literal `DATABASE_URL` reference in the Render service with the actual internal connection URL from `quantnifty-learning` (via Render Dashboard; never share the secret in chat).
2. Verify runtime evidence changes to `durability=POSTGRESQL`, `database_available=true`, and event counts are numeric.
3. Verify genuine live snapshots/decisions/paper outcomes increase PostgreSQL event counts.
4. Verify persistence across service restart/deploy.
5. Verify local live recorder → paper outcomes → after-market lab → policy persistence/load with PostgreSQL enabled.
6. Verify the 15:15–15:30 CAS window behavior from live evidence where a valid CAS signal exists; otherwise record the fail-closed standby evidence.
7. Verify the automatic after-market lab at/after 15:35 IST using today's stored live data only.
8. Verify the future-safe policy is persisted and loaded on the next eligible session.
9. Start/continue the READ-ONLY learning/review period using **live data + same-day post-market stored data only**.
10. Upgrade the Render API and Postgres compute plans if the user chooses always-on production durability; Free web services spin down after 15 minutes of no inbound traffic, and Free Postgres expires after 30 days.
11. Cleanup the temporary validation harness after today's evidence is captured, unless an always-on production compute plan is selected.
12. Cleanup remaining deprecation/unused-import warnings.

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
