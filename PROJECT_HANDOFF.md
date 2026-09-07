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
- Learn for a planned 3-month READ-ONLY period.
- Store live snapshots, decisions and paper outcomes separately from counterfactual research.
- After close, replay the stored day and test the full research strategy universe.
- Only closed, validated, future-safe outcomes may influence future policy.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Risk -> FinalDecision -> ExecutionPlan -> Paper Outcome -> Learning Store`

Core ownership: `main.py` provider/analytics/API/live refresh; `institutional_engine.py` signal/risk/FinalDecision/ExecutionPlan; `research_brain.py` adaptive regimes/selection/accumulation/exits and explicit research overrides; `session_policy.py` session/CAS; `decision_validation.py` validation; `backtest.py`/`replay.py` deterministic research; `historical.py` readiness; `recording_loader.py`/`recording_api.py` recorder/replay; `adaptive_learning.py` policy helpers; `learning_store.py` durable learning events; `after_market_lab.py` full-day research; `after_market_scheduler.py` orchestration; `paper_trade_tracker.py` read-only outcome lifecycle; `live_paper_manager.py` live outcome integration/restart recovery; `scenario_engine.py` scenario extraction; `research_strategy_runner.py` canonical research strategy routing; `adaptive_policy.py` policy validation; `policy_runtime.py` persistence/next-session loading; `web/backtest.html` UI.

Governance: FinalDecision is authoritative; Risk owns permission; ExecutionPlan never submits orders; actual and counterfactual experience remain separate; replay reuses the canonical pipeline; time must remain deterministic/injectable.

## Strategy universe
`directional`, `gamma_blast`, `early_accumulation`, `transition`, `range`, `breakout_watch`, `standby`, `cas_reentry`, `adaptive`.

Live API remains intentionally restricted to `directional`, `gamma_blast`, and `adaptive`. The after-market research runner now covers the seven research strategies plus adaptive and routes explicit research modes through the canonical Adaptive Brain/FinalDecision/Risk pipeline. This does not weaken live safeguards.

## Adaptive Brain
Early accumulation uses near-ATM OI expansion, premium behavior, active volume, quiet spot, controlled IV and expected-move-relative premium. States are `EARLY_ACCUMULATION`, `WATCH_ACCUMULATION`, `NO_CLEAR_ACCUMULATION`. Entry confirmation uses `EARLY_ACCUMULATION_CONFIRMATION` / `ACCUMULATION_THEN_BREAKOUT_CONFIRMATION`. Adaptive exit considers capital protection, favorable move, exhaustion/gamma reversal, profit lock and trailing. Current adaptive exit is primarily spot-based; richer option-premium/IV/Greeks/liquidity confirmation remains research work. No exact top/bottom prediction is claimed.

## Learning / storage
Live refresh now creates/updates a read-only paper trade lifecycle through `live_paper_manager.py`: one active hypothetical trade at a time, restart recovery from persisted open outcome, MFE/MAE tracking, option-premium P&L when the selected leg is available, spot proxy fallback, and session-close closure. No broker order is submitted.

`learning_store.py` supports PostgreSQL through `QUANTNIFTY_DATABASE_URL` or `DATABASE_URL`, with filesystem fallback. Render has a Postgres instance `quantnifty-learning` in Singapore, but the API service database environment variable still requires secure attachment and production persistence verification.

After-market loads the same day's stored snapshots, runs the full research strategy universe, persists the after-market research result and deterministic scenarios, then validates and persists a versioned future-safe Adaptive Policy candidate. `policy_runtime.py` loads only a prior-day policy with valid schema and future-safe/counterfactual metadata at service startup; current-day policy cannot be loaded.

## Historical readiness
Broader learning gate remains 252 trading days + 365 calendar days + valid recorded historical provenance. `data_Review.txt` is usable as historical/research evidence but remains uncommitted and is not a substitute for the one-year learning gate.

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
- One-year readiness gate/weekday counting.
- `APP_ARCHITECTURE.md` and persistent handoff.
- Live learning store and live Adaptive decision recording.
- After-market lab and scheduler.
- PostgreSQL-capable learning backend.
- Learning-store and lab regression tests.
- Read-only paper outcome tracker + MFE/MAE/boundary tests.
- Scenario extraction engine + tests.
- Versioned adaptive policy validation contract + promotion-gate tests.
- Live paper outcome integration with restart recovery.
- Full after-market strategy coverage through the canonical Adaptive pipeline.
- Scenario persistence through the durable research event store.
- Future-safe policy persistence and prior-day loading.

## Remaining verification / operational work
1. Attach/configure Render PostgreSQL securely and verify persistence across restart/deploy.
2. Run CI against the latest implementation and fix any failures.
3. Verify latest Render deployment is serving the latest `main` commit.
4. Run production evidence for live recorder → paper outcomes → after-market lab → policy persistence/load.
5. Start/continue the 3-month READ-ONLY learning period from the next market session.
6. Accumulate sufficient historical/live observations for the 252-day learning gate; do not claim one-year performance early.
7. Research richer option-premium/IV/Greeks/liquidity exit confirmation after sufficient observations.
8. Cleanup remaining deprecation/unused-import warnings.

## Verification state
Recent implementation commits include live paper integration, research strategy routing, scenario/policy persistence, and this handoff update. CI/production evidence from earlier commits cannot be reused as evidence for these latest changes; fresh verification is required.

## Non-negotiable rules
- Never commit `data_Review.txt`.
- Never commit API tokens/secrets.
- Never use future outcomes in live decisions.
- Never represent counterfactual research as actual trading.
- Never enable real order execution during learning/validation.
- Every implementation change updates this handoff.

## Continuation
Read this file and `APP_ARCHITECTURE.md`, inspect `main`, CI and Render, then continue from verification/operational work. Do not restart or redesign. Only mark work complete after tests and deployment/production evidence support it.
