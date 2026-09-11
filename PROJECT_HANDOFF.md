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
A read-only API exposes `/api/v1/research/results?day=YYYY-MM-DD`, sourced from `STORED_DAY` research events and durable live-day snapshots. It remains research-only and places zero orders. Legacy fixed-TIME/counterfactual reports are not returned as the current report; when the latest stored research event is from the old engine, the endpoint regenerates the report from the durable stored-day snapshots through the current thesis-hold engine.

### Current thesis-hold P&L model — 2026-09-11
The research lifecycle now matches the requested position behavior:

`ENTRY CONFIRMED -> BUY ACTUAL STORED OPTION -> OPEN POSITION -> HOLD/MONITOR -> EXIT -> ONLY THEN ALLOW NEXT ENTRY`

- The first approved signal becomes the first research trade; same-direction signals while it is open are not additional entries.
- The option entry and exit prices are taken from the stored option-chain quotes at the actual entry/exit snapshots.
- Stop/target are **NIFTY spot points**, not percentages.
- Because stored snapshots are not candles, the engine uses a clearly labeled **20-snapshot close-to-close spot ATR proxy** as the volatility unit.
- Stop = `max(50, min(150, ATR_proxy × 4 × IV_multiplier))` NIFTY points.
- ATM IV multiplier: `0.90` below 12, `1.00` from 12 to <20, `1.20` at >=20.
- Target = `2R` (twice the stop distance).
- The stop/target are applied to the NIFTY spot while P&L is calculated from the actual CE/PE premium movement and 65-unit research lot.
- Other exits remain: Adaptive exhaustion/trail, thesis/risk invalidation, expiry and same-day session close.
- Every trade report now carries entry/exit timestamp, option premium entry/exit, spot entry/exit, stop/target points, ATR proxy, IV multiplier, exit reason and net P&L.

This is research-only and does not change live paper risk or submit orders.

## After-market research tuning — 2026-09-11
The first stored-day run exposed excessive repeated entries: 44 directional trades and 41 adaptive/early-accumulation trades were generated, with most exits classified as `TIME`. That result was counterfactual/read-only, not actual paper trading.

V3 thesis-hold lifecycle replaced that fixed-time behavior. The old aggregate/counterfactual JSON remains historical audit evidence and is not the current stored-day P&L.

## Live-market validation — 2026-09-11
Production runtime was validated against Render application evidence after the live session:

- The production service received `LIVE_PROVIDER` snapshots with **82 option-chain rows** and live NIFTY spot values.
- Snapshots advanced continuously during the session; the observed durable snapshot counter advanced through the live session.
- The live decision event gate emitted distinct decision events and suppressed repeated unchanged states, confirming that the gate is active rather than generating duplicate decision events every poll.
- A paper trade reached `OPEN` during the live session and later returned to `IDLE` after the market session; this confirms the live paper lifecycle was exercised by live-provider data.
- PostgreSQL learning storage was configured/reachable with `sslmode=require` and durable decision/outcome records increased during the session.
- Real execution remained `trading=DISABLED` throughout the observed runtime evidence.
- After the session, live-provider cache remained populated while paper status was `IDLE`, with no overnight paper position carried forward.

This validates that the implementation is connected to the live market feed and that the read-only paper lifecycle is actually executing on live observations. It does **not** constitute a claim of profitable live trading or real-money execution.

## Astra AI decision layer — 2026-09-11
GPT-6 Astra is integrated as a **LIVE-only review/veto layer** after the deterministic institutional signal and risk gate. The quantitative engine remains authoritative for direction, risk and execution safety.

- Model: `gpt-6-astra` through the OpenAI Responses API.
- Astra receives only the current supplied market/institutional/risk evidence; it is instructed not to invent data, future outcomes or external news.
- Astra returns strict structured output: `APPROVE`, `HOLD` or `REJECT`, confidence, direction, regime, setup quality, conflicts, invalidation and reason codes.
- Astra can only veto an already risk-approved live candidate; it cannot change the deterministic risk limits or submit broker orders.
- `BACKTEST`, `REPLAY` and research modes do not call Astra.
- Missing `OPENAI_API_KEY` or an Astra request failure fails open to the existing deterministic decision path and is explicitly exposed as `astra_review.status=UNAVAILABLE`.
- Repeated unchanged live states are fingerprint-cached so Astra is not called on every market poll. The cache refreshes when decision-relevant direction, strategy/regime, gamma/OI/volatility state, spot bucket, IV or risk approval changes.
- The integration is read-only and real trading remains disabled.

The Astra implementation is currently in PR `#1` from `feature/astra-decision-layer`. The CI workflow's baseline `main` run was already failing at the Tests step before this PR; the Astra-specific unit tests pass independently in the local validation harness, and the PR compile step also passed. Production deployment is intentionally held until the code is merged and the required `OPENAI_API_KEY` secret is configured.

## Architecture / ownership
`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Entry Scenario Contract -> Risk -> Astra Decision Review -> FinalDecision -> ExecutionPlan -> Delta-Driven Paper Risk -> Paper Outcome -> Same-Day Adaptive Memory -> Learning Store -> After-Market Research Policy`

Research lifecycle: `Stored-day snapshots -> canonical decision -> OPEN THESIS -> HOLD/MONITOR -> volatility point stop/target or invalidation/session exit -> research P&L -> policy candidate`.

## Validation state
- Thesis-hold implementation base: `823351703dd4e9360ce5171271e41f4dd20041b1`, `313f25ba0aa78032fcf6dcb036290d380d818d9e`, same-day safeguard `c234df4f92def0e212a9b94058c265e47dab28ee`.
- Point-based volatility risk implementation: `fb6a9e72ccfd4918817967c706fa787865bf563c`.
- Research persistence/legacy refresh fixes: `a7affa0343151c69b6e6dd02ea4ed8ba7385ac61` plus the research API refresh commit immediately before this handoff update.
- Decision event gate has dedicated regression coverage in `apps/api/tests/test_decision_event_gate.py`.
- Astra decision layer implementation: `8781e9c52124f6c2858a96b6ea3734870b59743a` plus live-decision integration `361dde08046bbcc714b1e33ffac756a21d1fac9e`; throttle `afa99add2c35f39c692035aa0f4c7e0225f5e531`.
- Astra unit coverage: `f8ddb38b04694be06b6ebc13633b9f814c40e438`.
- Production live-market validation completed 2026-09-11 using Render runtime evidence: LIVE_PROVIDER snapshots, live option-chain rows, live paper OPEN -> IDLE lifecycle, durable learning counters, and trading disabled.
- Production P&L must still be checked from the research endpoint after deployment and must show the current thesis-hold/point-risk metadata.
- Production service remains `quantnifty-api` (`srv-dad5e767bikc739oighg`) in workspace `quantnifty-next` (`tea-dad5cr0n74is73dbho3g`).

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts. Do not create temporary workflow hacks to mutate production source; use normal repository changes and existing validation workflows.
