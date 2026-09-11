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

The Current Brain Plan risk display explicitly labels **Stop / Target as NIFTY spot-point distances**, not option-premium prices, and also displays the derived **Spot SL** and **Spot Target**. The active paper monitor separately displays the actual option premium `Entry → Current`.

## Trade Audit — 2026-09-11
A complete read-only paper-trade audit surface is implemented at `/trade-audit` with API `/api/v1/paper/trade-audit`, filtered by day and/or trade ID. It joins durable outcome -> exact entry snapshot -> exact decision timestamp without hindsight and marks legacy missing evidence INCOMPLETE rather than fabricating fields.

## Adaptive learning
- `learning_store.py` assigns event days using Asia/Kolkata trading day.
- Outcome event identity includes trade/lifecycle identity so OPEN/CLOSED events do not collide.
- Same-day runtime Adaptive memory consumes only current-IST-day `CLOSED` outcomes and only in explicit `LIVE` decision mode.
- Replay/backtest/research callers cannot inherit live same-day memory.
- Historical recordings and `data_Review.txt` remain reference/replay only.

## Risk / paper lifecycle
- At entry, the manager freezes entry spot, entry premium, selected instrument, trigger/mode, stop/target points, R:R and exit policy.
- **Option SL/target are delta-driven:** the selected option's live Greek delta converts the NIFTY-point risk budget into option-premium distances using `abs(delta) × NIFTY points`.
- New entries require a valid option delta; unavailable delta blocks a new entry.
- Premium SL/target are anchored to entry premium but recalculated every live snapshot from current option delta.
- Delta-driven exits, session-close and overnight protections remain in force.
- Existing OPEN trades without historical delta evidence are not rewritten or fabricated.
- Real orders are never submitted and no overnight paper positions are allowed.

## Live entry scenarios
The live Adaptive entry layer exposes 5 entry-capable pathways: `EARLY_ACCUMULATION`, `DIRECTIONAL`, `NEGATIVE_GAMMA_EXPANSION`, `GAMMA_TRANSITION`, and `CAS_REENTRY`. Liquidity-risk, positive-gamma range, compression and standby states are explicit NO_ENTRY states.

## After-market stored-day P&L results
A read-only API exposes `/api/v1/research/results?day=YYYY-MM-DD`, sourced from `STORED_DAY` research events and durable live-day snapshots. It remains research-only and places zero orders.

## After-market research tuning — 2026-09-11
The first stored-day run exposed excessive repeated entries: 44 directional trades and 41 adaptive/early-accumulation trades were generated, with most exits classified as `TIME`. That result was counterfactual/read-only, not actual paper trading.

V2 tuned the research profile to one full NIFTY lot (65), 8-bar maximum hold, 0.75% spot stop, 1.5% spot target, 5 bps slippage and ₹40 fixed cost per leg. Scenario streams were filtered to their actual regimes.

### V3 thesis-hold lifecycle
The research engine now models the user's intended position lifecycle:

`ENTRY CONFIRMED -> OPEN POSITION -> HOLD/MONITOR -> EXIT -> ONLY THEN ALLOW NEXT ENTRY`

Implemented in `apps/api/src/quantnifty/position_hold_backtest.py` and selected by `research_strategy_runner.py`.

Rules:
- Same-direction signals while a position is open are **not new trades**.
- The position remains open until stop, target, adaptive exhaustion/trail, thesis/risk invalidation, expiry or session close.
- The old short fixed maximum-hold exit is no longer the primary exit mechanism in V3.
- A position is explicitly closed before moving to another entry decision.
- Same-day boundary is enforced so the research lifecycle cannot carry a position into the next IST trading day.
- The implementation is research-only; live Brain, paper execution and delta-driven live risk are unchanged.

**Validation limitation:** the supplied 2026-09-11 JSON is an aggregate/counterfactual research result and does not contain the complete underlying option-chain/premium snapshots. It is therefore impossible to truthfully calculate the new V3 P&L from that JSON alone. The exact V3 result must come from the durable stored-day snapshot stream through the after-market research endpoint.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Entry Scenario Contract -> Risk -> FinalDecision -> ExecutionPlan -> Delta-Driven Paper Risk -> Paper Outcome -> Same-Day Adaptive Memory -> Learning Store -> After-Market Research Policy`

Research lifecycle: `Stored-day snapshots -> canonical decision -> OPEN THESIS -> HOLD/MONITOR -> risk/target/invalidation/session exit -> research P&L -> policy candidate`.

## Validation state
- Thesis-hold implementation: `823351703dd4e9360ce5171271e41f4dd20041b1`, `313f25ba0aa78032fcf6dcb036290d380d818d9e`, and same-day safeguard `c234df4f92def0e212a9b94058c265e47dab28ee`.
- Regression tests: `fca885dc6e6c407d797e536821c0d55f30ae86cb`.
- GitHub status for the final handoff commit has not yet exposed CI checks, so V3 is not claimed production-validated yet.
- Production service remains `quantnifty-api` (`srv-dad5e767bikc739oighg`) in workspace `quantnifty-next` (`tea-dad5cr0n74is73dbho3g`).

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts. Do not create temporary workflow hacks to mutate production source; use normal repository changes and existing validation workflows.
