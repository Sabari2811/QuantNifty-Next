# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-10  
**Branch:** `main`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production:** https://quantnifty-api.onrender.com  
**Backtest:** https://quantnifty-api.onrender.com/backtest  
**Execution:** READ-ONLY; no real orders; `trading=DISABLED`.

## Product plan
QuantNifty is a **Live Adaptive Brain + After-Market Research Lab**.

- Live decisions use only data available at decision time.
- Adaptive Brain: 09:20–15:15 IST.
- 15:15–15:30 IST: only already-produced live CAS may authorize `cas_reentry`.
- 15:30 IST: new decisions stop and open paper trades close as `SESSION_CLOSE`.
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

## Adaptive Brain
Early accumulation uses near-ATM OI expansion, premium behavior, active volume, quiet spot, controlled IV and expected-move-relative premium. States: `EARLY_ACCUMULATION`, `WATCH_ACCUMULATION`, `NO_CLEAR_ACCUMULATION`. Adaptive exits consider capital protection, favorable move, exhaustion/gamma reversal, profit lock and trailing. No exact top/bottom prediction is claimed.

## Learning / storage
PostgreSQL is the production durability target through `DATABASE_URL`/`QUANTNIFTY_DATABASE_URL`, with TLS explicitly required (`sslmode=require`) and JSONL fallback for local/testing. Render resource: `quantnifty-learning` in Singapore. No credentials are committed.

Live refresh persists immutable market snapshots and a read-only paper lifecycle. Closed outcomes include entry/exit, P&L basis, MFE/MAE and exit reason where determinable. After-market training runs on trading weekdays at/after 15:35 IST, uses only that completed same-day stored data, persists scenarios and a future-safe policy candidate, and marks a day complete only after successful research persistence. Failed/`NO_DATA` runs remain retryable.

## Decision-event model — finalized
**Snapshots and decision events are separate concepts.** Every live provider refresh continues to be processed and may be stored as a snapshot. The durable `decisions` ledger emits only when the actionable state changes, instead of recording an identical decision on every polling cycle.

`decision_event_gate.py` owns the event signature. The signature includes:
- market direction (`BULLISH`, `BEARISH`, `NEUTRAL`)
- strategy
- risk approval state
- selected sub-strategy
- session phase

Repeated identical states are not persisted as new decision events. State transitions are persisted. This does **not** suppress the live decision pipeline, analytics, risk evaluation, or paper-position management; it only reduces duplicate decision-event persistence.

The gate is now **restart-safe for the same IST trading day**: production startup restores the latest same-day persisted decision signature before live polling resumes. It also exposes emitted/suppressed counters in runtime evidence, making deduplication directly auditable without changing trading behavior.

## Paper ledger
`/api/v1/paper/ledger` is read-only. It returns closed paper trades for an IST day, excludes open trades from realized P&L, and provides same-day decision summary. P&L is explicitly a paper proxy: option-premium P&L when both entry/exit option prices exist, otherwise spot proxy. Broker charges are not fabricated.

## Completed
- Canonical decision/risk/execution architecture.
- Adaptive selector/regimes, accumulation and exits.
- Session/CAS policy and boundary tests.
- Data/decision validation.
- Replay/backtest consistency.
- Live-only Adaptive learning; legacy historical-learning gate/dependency removed.
- Live learning store and PostgreSQL durability support.
- After-market lab/scheduler with retryable completion state.
- Paper outcome tracker, MFE/MAE and restart recovery.
- Scenario extraction and future-safe policy persistence/loading.
- Production runtime observability and PostgreSQL diagnostics.
- Read-only paper ledger API and aggregation tests.
- Decision-event deduplication with regression coverage.
- **Restart-safe decision-event deduplication:** same-day latest decision seeding plus runtime emitted/suppressed counters.
- **Market-session liveness protection:** scheduled production `/health` wake/verification workflow added for the free Render web service during NSE weekdays; it performs no trading action.

## Verification / implementation commits
- `4c566ec94b036d896c2f202eb8a0936cd9866492` — historical learning dependency removed.
- `d23da5dde3f3a1ba9c957fb949fb6d86c2e6f8ec` — live-only adaptive tests.
- `1b4c334a5b52002bf0b9aa697bc2711aef788619` — architecture alignment.
- `1fbd51a7209fa6d7da3c4357ef64e2a170a98a3b` — PostgreSQL TLS fix.
- `50588241c9f029f0c3072dd85c02a3023d98807b` — production DB durability assertion.
- `3bf1662ae8e964df4a624c3f54d9816b7c07977f` / `577f2e905e6ce886b1c66c3b8ff5b602bc8bc244` — live validation harness/evidence hardening.
- `c39b2d128622f585b1770411fe36f56f5208dba6` / `3a7e2c8d8c869f8fd5966a8ad9adc0c6378c9a9d` — runtime observability.
- `b982289f92c1be806a9041023295b1b1de2bb4e6` / `ecc040c200776311330291cfc2ca2b0036ba1d8e` / `1c4bbab78a9716542bf2e40fe94426fc5c63be71` — paper ledger API/wiring/tests.
- `4e6364646f97448db0424e5ce5d957749337cca4` — decision event gate.
- `26faf74ef564b3f48b7da9207f379da248fa412c` — decision event gate tests.
- `3eafdd469969f295fc2e83e33d23234f51cf3942` — production startup wiring for decision-event gate.
- `eba092527ae2ba7e4bc69425a2cc7a7c90761639` — restart-safe gate state/counters.
- `2832a36054c1da684cc28cf171a0b9ac51cc4e78` — production wiring, same-day seeding and runtime gate observability.
- `d7728e491d424b3f2c7fd1e7ec6faa7ed5a425d3` — restart/dedup regression coverage.
- `00880f50c5184a8118316bc8414ca350c5108b1b` — market-session liveness wake/verification workflow.

## Live evidence — 2026-09-10
Production startup after the API token update and latest deployment showed the decision-event gate enabled. Live provider ingestion was active with `LIVE_PROVIDER`, 82 option-chain rows and NIFTY spot around 23,418. PostgreSQL was reachable with TLS and `durability=POSTGRESQL`; `trading=DISABLED`. At the observed window, persisted counters advanced to 797 snapshots, 628 decisions and 13 outcomes, with 2 research runs. The gate itself was enabled in the running process. A full same-day behavioral dedup ratio still requires observing the session through its market-state transitions; it must not be inferred from counters alone.

The Render service is on the free plan and had a clean idle shutdown at 07:33:18Z. The new liveness workflow is intended to prevent that sleep during the NSE session, but this workflow change is **not yet production-verified**; its first successful scheduled execution must be observed before the uptime item can be marked complete.

## Remaining verification
1. Observe a full live session and verify repeated identical actionable states produce many snapshots but only one persisted decision event.
2. Verify direction/approval/strategy/sub-strategy/session transitions each create exactly one new decision event.
3. Reconcile approved decisions with paper-position lifecycle and closed outcomes/P&L, including the 1-lot validation scenario.
4. Verify automatic same-day after-market research completion/persistence after the live session.
5. Verify restart/deploy during an active trading day does not duplicate the latest same-day decision signature.
6. Verify the new market-session liveness workflow executes successfully and keeps `quantnifty-api` awake during the NSE session.

## Non-negotiable rules
- Never commit API tokens/secrets or `data_Review.txt`.
- Never use future outcomes in live decisions.
- Never use historical recordings for live Adaptive memory/policy.
- Never represent counterfactual research as actual trading.
- Never submit real orders; execution remains READ-ONLY.
- Do not touch `data/instruments/fno.csv` or unrelated untracked audit/backup artifacts.
