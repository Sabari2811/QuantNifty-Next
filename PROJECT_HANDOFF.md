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
- 15:30 IST: decisions stop.
- Learn for a planned 3-month READ-ONLY period.
- Store live snapshots and decisions separately from counterfactual research.
- After close, replay the stored day and test every strategy actually exposed by the canonical engine.
- Only closed, validated, future-safe outcomes may influence future policy.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Risk -> FinalDecision -> ExecutionPlan`

- `main.py`: provider ingestion, analytics, live refresh, API.
- `institutional_engine.py`: institutional signal, risk, FinalDecision, execution plan.
- `research_brain.py`: regimes, adaptive strategy selection, accumulation, exits, learning memory.
- `session_policy.py`: 09:20/15:15/15:30 and CAS policy.
- `decision_validation.py`: fail-closed data/decision validation.
- `backtest.py` / `replay.py`: deterministic historical/replay path.
- `historical.py`: historical readiness contract.
- `recording_loader.py` / `recording_api.py`: recorded historical replay.
- `adaptive_learning.py`: research policy validation helpers.
- `learning_store.py`: PostgreSQL-capable durable learning events with filesystem fallback.
- `after_market_lab.py`: post-close counterfactual research.
- `after_market_scheduler.py`: weekday 15:35 IST orchestration.
- `paper_trade_tracker.py`: READ-ONLY live hypothetical outcome lifecycle with MFE/MAE; never submits orders.
- `web/backtest.html`: backtest UI.

Governance: FinalDecision is authoritative; Risk owns permission; ExecutionPlan never submits orders; actual and counterfactual experience remain separate; replay reuses the canonical pipeline; time must remain deterministic/injectable.

## Strategy universe
Target: `directional`, `gamma_blast`, `early_accumulation`, `transition`, `range`, `breakout_watch`, `standby`, `cas_reentry`, `adaptive`.

Current direct backtest/canonical exposure at this tracker revision remains: `directional`, `gamma_blast`, `adaptive`. The After-Market Lab explicitly reports other strategies as pending and never silently substitutes one strategy for another.

## Adaptive Brain
- Early accumulation uses near-ATM OI expansion, premium behavior, active volume, quiet spot, controlled IV and expected-move-relative premium.
- States: `EARLY_ACCUMULATION`, `WATCH_ACCUMULATION`, `NO_CLEAR_ACCUMULATION`.
- Entry confirmation: `EARLY_ACCUMULATION_CONFIRMATION` / `ACCUMULATION_THEN_BREAKOUT_CONFIRMATION`.
- Adaptive exit considers capital protection, favorable move, exhaustion/gamma reversal, profit lock and trailing.
- Current adaptive exit is primarily spot-based; richer option-premium/IV/Greeks/liquidity confirmation remains research work.
- No exact top/bottom prediction is claimed.

## Live learning
Live refresh records `snapshots`, `decisions`, `outcomes`, and `research` using schema `adaptive-learning-event-v1`.

Storage supports PostgreSQL through `QUANTNIFTY_DATABASE_URL` or `DATABASE_URL`, with JSONL fallback for development/testing. A Render Postgres instance named `quantnifty-learning` exists, but the API service still needs the database connection environment variable attached and persistence verified.

## After-market lab
Currently runs stored-day replay for `directional`, `gamma_blast`, and `adaptive`; records research rankings and `orders_placed=0`. Scheduler runs once per weekday at/after 15:35 IST. Research is counterfactual and cannot be represented as a live trade.

## New outcome lifecycle
`paper_trade_tracker.py` provides a read-only hypothetical trade object that tracks favorable/adverse movement and closes with a proxy spot move, MFE/MAE, exit reason, and explicit `execution=NONE`. Tests cover MFE/MAE and the 15:30 boundary. This module is intentionally non-executing; integration into the live recorder remains pending verification.

## Historical readiness
The broader learning gate requires 252 trading days and 365 calendar days with valid recorded historical provenance. Existing recorder evidence is much shorter and must not be used to claim one-year strategy performance.

## Completed
- Canonical decision/risk/execution architecture.
- Adaptive selector/regimes.
- Early accumulation and breakout confirmation.
- Adaptive exhaustion/trailing exit.
- Day-by-day adaptive backtest memory.
- Session/CAS policy.
- Data/decision validation.
- Replay/backtest consistency.
- Adaptive API/UI and multipart handling.
- One-year readiness gate with weekday counting.
- `APP_ARCHITECTURE.md` and persistent handoff.
- Live learning store and live Adaptive decision recorder.
- After-market lab and weekday scheduler.
- PostgreSQL-capable durable learning backend.
- Learning-store and after-market regression tests.
- Read-only paper outcome tracker + boundary/MFE/MAE tests.

## Pending implementation order
1. Attach/configure Render PostgreSQL securely and verify persistence across restart/deploy.
2. Expose `early_accumulation`, `transition`, `range`, `breakout_watch` through canonical FinalDecision/Risk for research/backtest without weakening live safeguards.
3. Integrate the read-only paper outcome lifecycle into live recording and persist closed MFE/MAE/P&L outcomes.
4. Build persistent scenario extraction/storage from validated research results.
5. Build persistent validated Adaptive Policy vN with promotion, rollback and fallback.
6. Add next-session policy loading and daily completeness checks.
7. Run complete production evidence for recorder + lab + policy flow.
8. Continue 3-month READ-ONLY learning.
9. Research richer option-premium/IV/Greeks/liquidity exit confirmation.
10. Cleanup unused imports/deprecation warnings.

## Verification state
Latest implementation commits:
- `06a2655603328e3a9da70cee64231c8e5c301a08` — read-only paper outcome tracker.
- `a93781341d7ae3157b19e38bd3b44c49de303ed7` — tracker regression tests.
- Current handoff update follows those changes.

CI and Production Evidence for prior tracker commit `64e2e0b75b2a23241dfbf740e11246bc4c3b3083` completed successfully. Render auto-deploy is enabled, but production must be rechecked against the latest commit before declaring new code live.

## Non-negotiable rules
- Never commit `data_Review.txt`.
- Never commit API tokens/secrets.
- Never use future outcomes in live decisions.
- Never represent counterfactual research as actual trading.
- Never enable real order execution during learning/validation.
- Every implementation change updates this handoff.

## Continuation
Read this file and `APP_ARCHITECTURE.md`, inspect `main`, CI and Render, then continue from the pending implementation order. Do not restart or redesign. Only mark an item complete after tests and deployment/production evidence support it.
