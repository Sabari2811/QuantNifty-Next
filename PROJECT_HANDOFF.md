# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-07  
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

Verified before this latest TLS fix:
- CI run `34148786448` for final commit `5cd65bf2...` completed **success**.
- Backtest Gate run `34148786444` for final commit `5cd65bf2...` completed **success**.
- Production Evidence run `34148786433` for final commit `5cd65bf2...` completed **success**, including production deployment wait, authenticated live-market/historical-replay evidence, and browser E2E.
- Render deployment `dep-dafep5n9r02s73fb83mg` served the prior Postgres-wired commit successfully.

The TLS fix is now committed and will trigger a fresh CI/deployment/evidence cycle. It must be verified on its resulting production deployment before this item is marked production-complete.

## Remaining verification / operational work
1. Verify CI for TLS-fix commit `1fbd51a7209fa6d7da3c4357ef64e2a170a98a3b`.
2. Verify Render deployment of the TLS-fix commit reaches `live`.
3. Verify the production learning store reports PostgreSQL availability rather than filesystem fallback.
4. Re-run the Render SQL verification once the connector can establish its required TLS connection; the previous query failed at the Render connector layer with `FATAL: SSL/TLS required`.
5. Verify `quantnifty_learning_events` creation and event counts after live data arrives.
6. Verify persistence across service restart/deploy.
7. Verify production live recorder → paper outcomes → after-market lab → policy persistence/load with PostgreSQL enabled.
8. Start the READ-ONLY learning/review period from the next live market session using **live data + same-day post-market stored data only**.
9. Accumulate live evidence naturally; no historical-day target is a learning gate.
10. Cleanup remaining deprecation/unused-import warnings.

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
