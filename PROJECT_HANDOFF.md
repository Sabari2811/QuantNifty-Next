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

Core ownership: `main.py` provider/analytics/API; `institutional_engine.py` signal/risk/FinalDecision/ExecutionPlan; `research_brain.py` adaptive regimes/selection/accumulation/exits; `session_policy.py` session/CAS; `decision_validation.py` validation; `backtest.py`/`replay.py` deterministic research; `historical.py` readiness; `recording_loader.py`/`recording_api.py` recorder/replay; `adaptive_learning.py` policy helpers; `learning_store.py` durable learning events; `after_market_lab.py` research; `after_market_scheduler.py` orchestration; `paper_trade_tracker.py` read-only outcome lifecycle; `scenario_engine.py` scenario extraction; `adaptive_policy.py` policy validation/promotion gates; `web/backtest.html` UI.

Governance: FinalDecision is authoritative; Risk owns permission; ExecutionPlan never submits orders; actual and counterfactual experience remain separate; replay reuses the canonical pipeline; time must remain deterministic/injectable.

## Strategy universe
Target: `directional`, `gamma_blast`, `early_accumulation`, `transition`, `range`, `breakout_watch`, `standby`, `cas_reentry`, `adaptive`.

Current direct backtest/canonical exposure remains `directional`, `gamma_blast`, `adaptive`. The After-Market Lab explicitly reports other strategies as pending and never silently substitutes one strategy for another.

## Adaptive Brain
Early accumulation uses near-ATM OI expansion, premium behavior, active volume, quiet spot, controlled IV and expected-move-relative premium. States are `EARLY_ACCUMULATION`, `WATCH_ACCUMULATION`, `NO_CLEAR_ACCUMULATION`. Entry confirmation uses `EARLY_ACCUMULATION_CONFIRMATION` / `ACCUMULATION_THEN_BREAKOUT_CONFIRMATION`. Adaptive exit considers capital protection, favorable move, exhaustion/gamma reversal, profit lock and trailing. Current adaptive exit is primarily spot-based; richer option-premium/IV/Greeks/liquidity confirmation remains research work. No exact top/bottom prediction is claimed.

## Learning / storage
Live refresh records `snapshots`, `decisions`, `outcomes`, and `research` under `adaptive-learning-event-v1`. PostgreSQL is supported through `QUANTNIFTY_DATABASE_URL` or `DATABASE_URL`, with JSONL fallback. Render has a Postgres instance `quantnifty-learning` in Singapore, but the API service still needs its database environment variable attached and persistence verified.

After-market currently replays `directional`, `gamma_blast`, `adaptive` at/after 15:35 IST and keeps research counterfactual. `paper_trade_tracker.py` now provides non-executing hypothetical trade MFE/MAE/close lifecycle; its integration into the live recorder remains pending.

`scenario_engine.py` now extracts deterministic counterfactual scenarios such as accumulation breakout, gamma blast, gamma transition, positive-gamma range, compression/breakout watch, liquidity risk, failed direction, and exhaustion/profit-lock.

`adaptive_policy.py` now defines a versioned policy contract with anchor fallback, minimum sample gate, minimum improvement gate, and explicit future-safe/counterfactual metadata. It does not yet persist or load policies; promotion integration remains pending.

## Historical readiness
Broader learning gate: 252 trading days + 365 calendar days + valid recorded historical provenance. Existing recorder evidence is far shorter; do not claim one-year strategy performance.

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

## Pending implementation order
1. Attach/configure Render PostgreSQL securely and verify persistence across restart/deploy.
2. Expose `early_accumulation`, `transition`, `range`, `breakout_watch` through canonical FinalDecision/Risk for research/backtest without weakening live safeguards.
3. Integrate paper outcome lifecycle into live recording and persist closed MFE/MAE/P&L outcomes.
4. Persist scenario results from after-market research.
5. Persist validated Adaptive Policy vN with promotion, rollback and fallback; then load it only for future sessions.
6. Add next-session policy loading and daily completeness checks.
7. Run complete production evidence for recorder + lab + policy flow.
8. Continue 3-month READ-ONLY learning.
9. Research richer option-premium/IV/Greeks/liquidity exit confirmation.
10. Cleanup unused imports/deprecation warnings.

## Verification state
Implementation commits in this pass:
- `06a2655603328e3a9da70cee64231c8e5c301a08` — read-only paper outcome tracker.
- `a93781341d7ae3157b19e38bd3b44c49de303ed7` — outcome tracker tests.
- `84bccb0502b9033a74b7397ab0efb375a0b407a7` — scenario engine.
- `5c206e409fc42b0bd97ac1b1194cae2031069beb` — adaptive policy contract.
- `0fd2d8a5777e9ee890726a6463a4ca3ba26c81fa` — scenario/policy tests.
- Current handoff update follows these changes.

CI and Production Evidence for prior tracker commit `64e2e0b75b2a23241dfbf740e11246bc4c3b3083` completed successfully. New commits after that verification require a fresh CI run before completion is claimed. Render auto-deploy is enabled, but production must be rechecked against the latest commit before declaring new code live.

## Non-negotiable rules
- Never commit `data_Review.txt`.
- Never commit API tokens/secrets.
- Never use future outcomes in live decisions.
- Never represent counterfactual research as actual trading.
- Never enable real order execution during learning/validation.
- Every implementation change updates this handoff.

## Continuation
Read this file and `APP_ARCHITECTURE.md`, inspect `main`, CI and Render, then continue from pending items. Do not restart or redesign. Only mark work complete after tests and deployment/production evidence support it.
