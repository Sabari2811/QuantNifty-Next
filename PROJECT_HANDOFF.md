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

The audit is assembled without hindsight by joining the durable paper outcome to the **exact same decision timestamp** used by the live loop.

The audit deliberately uses durable `snapshots`, `decisions` and `outcomes` rather than reconstructing an old trade from later market state. Historical/replay evidence is never used to manufacture live audit evidence or live Adaptive learning.

## Adaptive learning
- `learning_store.py` assigns event days using Asia/Kolkata trading day.
- Outcome event identity includes trade/lifecycle identity so OPEN/CLOSED events do not collide.
- Same-day runtime Adaptive memory consumes only current-IST-day `CLOSED` outcomes and only in explicit `LIVE` decision mode.
- Replay/backtest/research callers cannot inherit live same-day memory.
- Historical recordings and `data_Review.txt` remain reference/replay only.

## Risk / paper lifecycle
- At entry, the manager freezes entry spot, entry premium, selected instrument, trigger/mode, stop/target points, R:R and exit policy.
- **Option SL/target are delta-driven:** the selected option's live Greek delta converts the NIFTY-point risk budget into option-premium distances using `abs(delta) × NIFTY points`.
- New entries require a valid option delta; if the selected option has no usable Greek delta, the paper entry is not opened rather than falling back to a spot-only or arbitrary premium risk model.
- The premium SL/target are anchored to the entry option premium but are recalculated on every live snapshot from the **current option delta**, so changing Greeks dynamically change the premium risk levels.
- The delta-driven levels are used by the paper lifecycle for `DELTA_PREMIUM_STOP` and `DELTA_PREMIUM_TARGET` exits when crossed; session-close and overnight protections remain in force.
- Existing OPEN trades that predate this delta evidence are not retroactively rewritten or fabricated.
- Exit uses BID -> LAST -> ASK when an option mark is available; real orders are never submitted.
- No overnight paper positions.

## Live entry scenarios
The application exposes one explicit scenario contract for the live Adaptive entry layer with 5 entry-capable pathways: `EARLY_ACCUMULATION`, `DIRECTIONAL`, `NEGATIVE_GAMMA_EXPANSION`, `GAMMA_TRANSITION`, and `CAS_REENTRY`. Non-entry liquidity-risk, positive-gamma range, compression and standby states remain explicit NO_ENTRY states.

## After-market stored-day P&L results
A read-only API exposes `/api/v1/research/results?day=YYYY-MM-DD`, sourced from `STORED_DAY` research events and durable live-day snapshots. It remains research-only and places zero orders.

## After-market research tuning — 2026-09-11
The first stored-day run exposed excessive repeated entries: the research backtest could close on a short maximum-hold window and immediately evaluate another entry even when the directional thesis had not materially invalidated.

The original tuned V2 profile used one full NIFTY lot (65), 8-bar maximum hold, 0.75% spot stop, 1.5% spot target, 5 bps slippage and ₹40 fixed cost per leg. The supplied 2026-09-11 JSON showed 44 directional trades and 41 adaptive/early-accumulation trades, with most exits classified as `TIME`; the combined research result was counterfactual/read-only, not actual paper trading.

A research-only **V3 thesis-hold lifecycle** is now implemented:

- `apps/api/src/quantnifty/position_hold_backtest.py` owns the new research position lifecycle.
- The canonical decision engine and existing risk/analytics stack are reused.
- Once an entry is opened, same-direction approved signals do **not** create another position.
- The position remains open until spot stop/target, adaptive exhaustion/trail, thesis/risk invalidation, expiry or session close.
- The old fixed maximum-hold exit is not the primary exit mechanism for this research profile.
- The next entry is evaluated only after the current position closes, enforcing one-position-at-a-time and suppressing repeated entries while the thesis is active.
- This is research-only; live Brain, live paper manager, delta-driven paper risk, broker execution and trading-disabled safeguards are unchanged.

The research runner now uses `INTRADAY_OPTION_RESEARCH_V3_THESIS_HOLD` and calls the thesis-hold engine for all research strategies. Regression coverage is in `apps/api/tests/test_position_hold_backtest.py` plus the existing research runner tests.

**Important validation limitation:** the user-supplied research JSON contains aggregate research results and counterfactual scenario records, not the full underlying stored option-chain/premium snapshot stream required to recompute the thesis-hold P&L. Therefore the V3 code can be validated structurally in CI, but the exact post-change 2026-09-11 P&L must be generated from the durable stored-day snapshots by the after-market research endpoint; it must not be inferred from the old aggregate JSON.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Entry Scenario Contract -> Risk -> FinalDecision -> ExecutionPlan -> Delta-Driven Paper Risk -> Paper Outcome -> Same-Day Adaptive Memory -> Learning Store -> After-Market Research Policy`

Research position lifecycle: `Stored-day snapshots -> canonical decision -> OPEN THESIS -> HOLD/MONITOR -> risk/target/invalidation/session exit -> realized research P&L -> policy candidate`.

## Validation state
- Thesis-hold implementation commits: `823351703dd4e9360ce5171271e41f4dd20041b1` and `313f25ba0aa78032fcf6dcb036290d380d818d9e`.
- Thesis-hold regression tests commit: `fca885dc6e6c407d797e536821c0d55f30ae86cb`.
- CI/deployment validation must complete before the V3 endpoint is treated as production-active.
- Production service remains `quantnifty-api` (`srv-dad5e767bikc739oighg`) in workspace `quantnifty-next` (`tea-dad5cr0n74is73dbho3g`).

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts. Do not create temporary workflow hacks to mutate production source; use normal repository changes and existing validation workflows.
