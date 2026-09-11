# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-11  
**Branch:** `main`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production:** https://quantnifty-api.onrender.com  
**Backtest:** https://quantnifty-api.onrender.com/backtest  
**Execution:** READ-ONLY; no real orders; `trading=DISABLED`.

## Product plan
QuantNifty-Next is a **Live Adaptive Brain + After-Market Research Lab**.

- Live decisions use only data available at decision time.
- Adaptive Brain: 09:20–15:15 IST.
- 15:15–15:30 IST: only already-produced live CAS may authorize `cas_reentry`.
- 15:30 IST: new decisions stop and all open paper trades must close as `SESSION_CLOSE`.
- No paper position may be carried into the next IST trading day.
- Learn only from `LIVE_PROVIDER` current/future observations and `STORED_DAY` same-day completed live observations.
- Historical learning/bootstrap/performance gates are removed completely.
- `data_Review.txt` and old recordings are replay/reference evidence only and must never seed, train, promote or influence live Adaptive memory/policy.
- After close, replay the stored live day only, test the research universe, extract scenarios and persist a future-safe policy candidate.

## Current UI / paper telemetry
The Market Intelligence page is read-only and separates **Current Brain Plan** from the actual **Active Paper Trade**. The paper monitor derives premium movement from entry premium to current mark, preserves the original entry quantity, and anchors spot SL/target to the immutable entry spot. New NIFTY paper trades default to one full lot (65 units) when the provider does not expose quantity. Real trading remains disabled.

## Trade Audit — 2026-09-11
A complete read-only paper-trade audit surface is now implemented at:

- UI: `/trade-audit`
- API: `/api/v1/paper/trade-audit`
- Filter parameters: `day=YYYY-MM-DD` and/or `trade_id=...`

The audit is assembled without hindsight by joining the durable paper outcome to the **exact same decision timestamp** used by the live loop:

`paper outcome entry_timestamp -> durable snapshot event timestamp -> durable decision event timestamp`

The audit UI exposes expandable sections for:

- Trade identity, entry/exit timestamps, direction, strategy, trigger and selected option.
- Entry premium/source, exit premium/source, quantity and realized P&L basis.
- Immutable entry spot, stop points, target points, R:R, SL spot, target spot and exit policy.
- Exact decision record: signal, confidence, evidence, rationale, Adaptive regime/strategy/readiness/reason, risk approval, risk gates, reasons and execution plan.
- Decision checklist with explicit PASS/FAIL values for recorded risk gates, direction, confidence threshold, risk approval, instrument selection and read-only execution.
- Frozen decision-time market evidence: spot, PCR, OI/OI flow, GEX, DEX, vanna proxy, IV/skew, ATM IV, gamma flip/walls, max pain, expected move, support/resistance, market structure, dealer flow, liquidity, directional scores, bias, data integrity and exact option-chain/strike-selection payload.
- Exit evidence and outcome.
- Learning provenance: same-day learning eligibility, explicit historical-learning exclusion and evidence source.
- Completeness status. Legacy trades whose original decision-time snapshot is not durably available are marked **INCOMPLETE**; later snapshots are never substituted and missing values are not fabricated.

Implementation is in `apps/api/src/quantnifty/recording_api.py` and `apps/api/src/quantnifty/web/trade_audit.html`. Regression coverage is in `apps/api/tests/test_trade_audit.py`.

The audit deliberately uses the already durable `snapshots`, `decisions` and `outcomes` stores rather than reconstructing an old trade from later market state. Historical/replay evidence is never used to manufacture live audit evidence or live Adaptive learning.

## Adaptive learning
- `learning_store.py` assigns event days using Asia/Kolkata trading day.
- Outcome event identity includes trade/lifecycle identity so OPEN/CLOSED events do not collide.
- Same-day runtime Adaptive memory consumes only current-IST-day `CLOSED` outcomes and only in explicit `LIVE` decision mode.
- Replay/backtest/research callers cannot inherit live same-day memory.
- Historical recordings and `data_Review.txt` remain reference/replay only.

## Risk / paper lifecycle
- At entry, the manager freezes entry spot, entry premium, selected instrument, trigger/mode, stop/target points, R:R and exit policy.
- Spot SL/target remain anchored to entry spot for the lifetime of the paper trade.
- Existing OPEN trades are recovered from durable evidence; no synthetic re-entry is created.
- Exit uses BID -> LAST -> ASK when an option mark is available; real orders are never submitted.
- No overnight paper positions.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Risk -> FinalDecision -> ExecutionPlan -> Paper Outcome -> Same-Day Adaptive Memory -> Learning Store -> After-Market Research Policy`

Core ownership: `main.py`, `institutional_engine.py`, `research_brain.py`, `session_policy.py`, `decision_validation.py`, `replay.py`, `backtest.py`, `recording_loader.py`, `recording_api.py`, `adaptive_learning.py`, `learning_store.py`, `after_market_lab.py`, `after_market_scheduler.py`, `paper_trade_tracker.py`, `live_paper_manager.py`, `scenario_engine.py`, `research_strategy_runner.py`, `adaptive_policy.py`, `policy_runtime.py`, and `web/*`.

## Validation state
Commit `cdcc7339fa8f3f37f5ff47dd3dd0f96d57da6217` is the current `main` head after the audit implementation and tests.

- QuantNifty CI run `34577711726`: **success** on the audit commit.
- QuantNifty Backtest Gate Evidence run `34577711746`: **success**.
- QuantNifty Paper Ledger Evidence run `34577711708`: **success**.
- Live Liveness Wake run `34577711642`: **success**.
- Live Validation Harness run `34577711625`: active/continuing live-session validation.
- Production Evidence run `34577711671`: active/awaiting production deployment evidence.

The Render production service is `quantnifty-api` (`srv-dad5e767bikc739oighg`) in workspace `quantnifty-next` (`tea-dad5cr0n74is73dbho3g`). Its last confirmed live deployment before the audit commits is `dep-dahpgrrm8hqs73crmkcg` on commit `bb1605fe4e18fcc2f714c3a1bb8c5cd924ec8a7b`. The audit source is on GitHub `main`; do not claim the audit UI/API is production-live until a Render deployment for the audit commit is observed and production evidence passes.

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts. Do not create temporary workflow hacks to mutate production source; use normal repository changes and existing validation workflows.
