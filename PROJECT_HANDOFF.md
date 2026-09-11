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

The Current Brain Plan risk display explicitly labels **Stop / Target as NIFTY spot-point distances**, not option-premium prices, and also displays the derived **Spot SL** and **Spot Target**. The active paper monitor separately displays the actual option premium `Entry → Current`. This prevents a spot-risk distance such as `164.31` from being mistaken for an option target premium of ₹164.31.

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
- **Option SL/target are now delta-driven:** the selected option's live Greek delta converts the NIFTY-point risk budget into option-premium distances using `abs(delta) × NIFTY points`.
- New entries require a valid option delta; if the selected option has no usable Greek delta, the paper entry is not opened rather than falling back to a spot-only or arbitrary premium risk model.
- The premium SL/target are anchored to the entry option premium but are recalculated on every live snapshot from the **current option delta**, so changing Greeks dynamically change the premium risk levels.
- The delta-driven levels are used by the paper lifecycle for `DELTA_PREMIUM_STOP` and `DELTA_PREMIUM_TARGET` exits when crossed; session-close and overnight protections remain in force.
- Entry audit evidence stores `entry_delta` and the delta-derived premium SL/target calculation. Closed evidence stores exit delta and the delta-derived levels at exit.
- The underlying NIFTY spot risk budget remains available as the source distance for conversion, but the active option risk decision is expressed in the selected contract's premium using its live delta.
- Spot SL/target remain available as reference boundaries and are not used as the primary option-premium SL/target.
- Existing OPEN trades that predate this delta evidence are not retroactively rewritten or fabricated; if their historical delta is unavailable, the audit marks that delta evidence unavailable.
- Existing OPEN trades are recovered from durable evidence; no synthetic re-entry is created.
- Exit uses BID -> LAST -> ASK when an option mark is available; real orders are never submitted.
- No overnight paper positions.

## Live entry scenarios
The application now exposes one explicit scenario contract for the live Adaptive entry layer. There are **5 supported entry-capable pathways**:

1. `EARLY_ACCUMULATION` → `early_accumulation` → `EARLY_ACCUMULATION_CONFIRMATION`
2. `DIRECTIONAL` → `directional` → directional confirmation, covering breakout/trend up and breakdown/trend down.
3. `NEGATIVE_GAMMA_EXPANSION` → `gamma_blast` → `GAMMA_BLAST_CONFIRMATION`
4. `GAMMA_TRANSITION` → `transition` → `GAMMA_TRANSITION_CONFIRMATION`
5. `CAS_REENTRY` → `cas_reentry` → `CAS_REENTRY_CONFIRMATION`, restricted to the late-session CAS authorization window.

`LIQUIDITY_RISK`, positive-gamma range, compression and generic transition/standby states are explicitly represented as **NO_ENTRY** states rather than being mistaken for entry scenarios. VWAP, EMA, PCR, OI flow, GEX/DEX, IV, confidence and liquidity remain evidence/gates inside these scenarios, not separate entry types.

The scenario contract is implemented in `apps/api/src/quantnifty/entry_scenarios.py` and surfaced by `decision_intelligence()` as `entry_scenario` plus the supported `entry_scenarios` registry. Regression coverage is in `apps/api/tests/test_entry_scenarios.py`.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Entry Scenario Contract -> Risk -> FinalDecision -> ExecutionPlan -> Delta-Driven Paper Risk -> Paper Outcome -> Same-Day Adaptive Memory -> Learning Store -> After-Market Research Policy`

Core ownership: `main.py`, `institutional_engine.py`, `research_brain.py`, `session_policy.py`, `decision_validation.py`, `replay.py`, `backtest.py`, `recording_loader.py`, `recording_api.py`, `adaptive_learning.py`, `learning_store.py`, `after_market_lab.py`, `after_market_scheduler.py`, `paper_trade_tracker.py`, `live_paper_manager.py`, `scenario_engine.py`, `entry_scenarios.py`, `research_strategy_runner.py`, `adaptive_policy.py`, `policy_runtime.py`, and `web/*`.

## Validation state
Delta-driven paper-risk implementation is on `main` as commits `ce37f1cff29259e88e2c7d492221a03920d25876` and `e925776bf64ed2e1afe41c02772dedaace8a183b`. The first CI run exposed one existing unit test fixture that did not provide option delta; the fixture was corrected to reflect the new mandatory delta-driven entry contract.

The explicit entry-scenario implementation is on `main` at the scenario-registry, market-brain integration, and regression-test commits immediately preceding this handoff update. Push-triggered live-validation run `34592415236` for the scenario test commit completed successfully. A full CI/production validation for the final handoff head is still required before claiming the complete application change is production-live.

The Render production service is `quantnifty-api` (`srv-dad5e767bikc739oighg`) in workspace `quantnifty-next` (`tea-dad5cr0n74is73dbho3g`). Do not claim the entry-scenario change is production-live until a Render deployment for the final validated source and production evidence are observed.

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts. Do not create temporary workflow hacks to mutate production source; use normal repository changes and existing validation workflows.
