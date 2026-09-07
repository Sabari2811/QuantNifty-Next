# QuantNifty-Next — Persistent Project Handoff

**Purpose:** Durable cross-chat project state. Always read this file and `APP_ARCHITECTURE.md`, then inspect current `main` before implementation. GitHub `main` is authoritative for code.

**Updated:** 2026-09-07  
**Current branch:** `main`  
**Current tracker commit:** this update  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production:** https://quantnifty-api.onrender.com  
**Backtest:** https://quantnifty-api.onrender.com/backtest  
**Execution:** READ-ONLY; `orders_placed=0`, `trading_enabled=false`.

---

## FINALIZED PLAN

QuantNifty is a **Live Adaptive Brain + After-Market Research Lab**.

- Live decisions use only data available at decision time.
- Normal Adaptive Brain: **09:20–15:15 IST**.
- **15:15–15:30 IST:** normal Brain stops; only valid already-produced live CAS may authorize `cas_reentry`.
- **15:30 IST:** all decisions stop.
- Learn continuously from live market data for the planned **3-month READ-ONLY learning period**.
- Store live snapshots and decisions.
- After close, replay the stored day and test every strategy that the execution engine exposes.
- Keep actual live experience separate from counterfactual research experience.
- Generate successful and failed scenarios.
- Only closed, validated, future-safe outcomes may influence future policy.

---

## ARCHITECTURE MAP

```text
INDSTOCKS / INDMONEY
        |
        v
LIVE MARKET SNAPSHOTS
        |
        v
+----------------------+       +----------------------+
| LIVE ADAPTIVE BRAIN  |       | AFTER-MARKET LAB     |
| 09:20 -> 15:15       |       | after 15:30          |
+----------+-----------+       +----------+-----------+
           |                              |
           v                              v
 Institutional/Risk/FinalDecision    deterministic replay
           |                              |
           v                    +---------+----------+
      READ-ONLY PLAN            |         |          |
                                v         v          v
                           Directional Gamma Blast Adaptive
                                |
                                v
                     Counterfactual research
                                |
                +---------------+----------------+
                v                                v
          LIVE MEMORY                    RESEARCH MEMORY
                \                                /
                 +-------------+----------------+
                               v
                       VALIDATED POLICY
                               |
                               v
                      FUTURE LIVE BRAIN
```

Live chain:

`Snapshot -> Analytics -> Institutional Signal -> Adaptive Selection -> Risk -> FinalDecision -> ExecutionPlan`

After-market chain:

`Stored Day -> Replay -> All Supported Strategies -> Metrics -> Scenarios -> Learning Memory -> Policy Validation`

---

## STRATEGIES / REGIMES

Target strategy universe:

`directional`, `gamma_blast`, `early_accumulation`, `transition`, `range`, `breakout_watch`, `standby`, `cas_reentry`, `adaptive`.

Currently directly exposed to the backtest/canonical decision routes:

`directional`, `gamma_blast`, `adaptive`.

The After-Market Lab currently tests those three and explicitly reports the other planned strategies as pending direct execution-engine exposure. It must never silently substitute one strategy for another.

Regimes/scenarios include trend, early accumulation, accumulation->breakout, false breakout->reversal, gamma blast, gamma transition, positive-gamma range, compression, liquidity risk, high/low volatility, expiry behavior, CAS re-entry and exhaustion.

---

## EARLY ACCUMULATION / EXIT

Accumulation detector uses near-ATM OI expansion, premium behavior, active volume, quiet/compressed spot, controlled IV and expected-move-relative premium.

States: `EARLY_ACCUMULATION`, `WATCH_ACCUMULATION`, `NO_CLEAR_ACCUMULATION`.

Entry confirmation includes `EARLY_ACCUMULATION_CONFIRMATION` and `ACCUMULATION_THEN_BREAKOUT_CONFIRMATION`.

Adaptive exit considers capital protection, favorable move, exhaustion/gamma reversal, profit lock, trailing and continued trend/accumulation. Current implementation is primarily spot-based with gamma/volume/pressure context; richer option-premium/IV/Greeks/liquidity exit confirmation remains future research.

The system does not claim exact top/bottom prediction.

---

## LIVE LEARNING

The live refresh loop now:

1. fetches live INDstocks option-chain data,
2. computes canonical analytics,
3. evaluates Adaptive `FinalDecision` using `LIVE` mode,
4. records the live snapshot,
5. records the live decision separately.

Learning event streams:

```text
snapshots
 decisions
 outcomes
 research
```

Event schema version: `adaptive-learning-event-v1`.

The learning store now supports:

- PostgreSQL when `QUANTNIFTY_DATABASE_URL` or `DATABASE_URL` is configured;
- filesystem JSONL fallback for development/testing.

PostgreSQL table is created automatically by the store on first use.

---

## AFTER-MARKET LAB

`after_market_lab.py` runs a stored-day replay for the currently exposed strategies:

- directional
- gamma_blast
- adaptive

It records a separate research event with metrics and ranking by net P&L. `after_market_scheduler.py` starts with the API service and runs once per weekday at/after **15:35 IST**.

No research result is represented as an actual live trade.

---

## LOOK-AHEAD / SAFETY

A decision at timestamp `T` may use only data available at or before `T`.

After-market results can affect only future decisions.

All learning/validation remains READ-ONLY.

---

## HISTORICAL READINESS

The existing historical gate requires:

- 252 trading days
- 365 calendar days
- weekends excluded from trading-day count
- valid recorded historical provenance

This remains useful for broader historical research but does not block starting the 3-month live-learning experiment.

---

## CURRENT SOFTWARE MAP

- `apps/api/src/quantnifty/main.py` — provider ingestion, analytics, live refresh/learning recorder, API
- `institutional_engine.py` — signal/risk/final decision/execution plan
- `research_brain.py` — adaptive regime/strategy/accumulation/exit logic
- `session_policy.py` — session/CAS policy
- `decision_validation.py` — validation/fail closed
- `backtest.py` — deterministic strategy backtest
- `replay.py` — replay
- `historical.py` — historical readiness
- `recording_loader.py` / `recording_api.py` — recorder/replay API
- `adaptive_learning.py` — research policy artifact/validation helpers
- `learning_store.py` — durable PostgreSQL-capable learning events + filesystem fallback
- `after_market_lab.py` — post-close strategy research
- `after_market_scheduler.py` — post-close orchestration
- `web/backtest.html` — backtest UI

Architecture rules: FinalDecision authoritative; Risk owns permission; ExecutionPlan never submits orders; replay uses canonical pipeline; actual and counterfactual experience remain separate; time is deterministic/injectable.

---

## IMPLEMENTATION STATUS

### Completed

- Canonical decision/risk/execution architecture
- Adaptive selector and regimes
- Early accumulation and breakout confirmation
- Adaptive exhaustion/trailing exit
- Day-by-day adaptive backtest memory
- 09:20 / 15:15 / 15:30 policy
- CAS-only late session
- Live data integrity and decision validation
- Replay/backtest consistency
- Adaptive API/UI
- Multipart strategy/config handling
- One-year readiness gate and weekday counting
- Persistent handoff + application architecture documents
- **Live learning event store**
- **Live Adaptive decision recording**
- **After-market lab for currently exposed strategies**
- **Daily after-market scheduler**
- **Separate live/research event streams**
- **PostgreSQL-capable durable storage backend**
- **Learning-store regression tests**
- **After-market lab coverage**

### Pending

1. Attach/configure the provisioned Render PostgreSQL instance to the API using a secure environment variable and verify persistence across restart/deploy.
2. Expand canonical execution/backtest exposure to `early_accumulation`, `transition`, `range`, `breakout_watch` so the lab can truly test the full target universe.
3. Resolve live decision outcomes into persistent MFE/MAE/P&L outcome events.
4. Build persistent scenario extraction/storage from research results.
5. Build persistent validated Adaptive Policy vN with promotion, rollback and fallback.
6. Add next-session policy loading and daily completeness checks.
7. Run complete production evidence for recorder + lab + policy flow.
8. Continue 3-month READ-ONLY learning period.
9. Research richer option-premium/IV/Greeks/liquidity exit confirmation.
10. Cleanup unused imports and non-blocking deprecation warnings.

---

## IMPORTANT COMMITS

- `ae08e46264493d8f8d687520a9d9d5ee43b5f324` — canonical decision-gate assertions
- `9a921a915ba20beaad56a0c1a70c54fe90a23fd3` — one-year learning readiness endpoint
- `3e9dd3216328be3b4360b0654a0b22961d03db9c` — weekday readiness count
- `3df4a6eaef0e905952e07a1969012c816d904fb8` — persistent handoff
- `a50b0f7571f2d84dc7ea05a986fe5c6f04738b2e` — app architecture/plan
- `1c605a3b091390a4bd2de58a620b9c5f233c5444` — learning store abstraction
- `d8b8cfdc1b436bd1a05d320068f33e96f9ceb60e` — after-market lab
- `064ff334fc4c8547da86901a6848bdbe95e195e3` — after-market scheduler
- `512169a12a1e034b91cb24b7dfe79750f53c53c9` — live recorder lifecycle
- `f83bc6a65f96169fc4b696225ed51a36e38dec58` — learning store tests
- `c5d66da14e0f7fff67e9a345fa8914b97f7277eb` — after-market lab tests
- `b2d04a6807644cf34aacfc323b855c2eee5e76f7` — PostgreSQL-capable learning store

Subsequent tracker commits are the current handoff state and must always be checked before continuing.

---

## CI / PRODUCTION RULE

Previously verified baseline CI: **77 passed, 6 warnings**. New learning-store/lab changes were pushed after that baseline; their CI must be rechecked before declaring them verified.

Render current production deployment must be rechecked before calling new code live. Auto-deploy is enabled on `main`.

---

## RENDER DATA TARGET

A Render Postgres instance named `quantnifty-learning` was provisioned in Singapore. It is currently a free database and Render reports an expiry date; do not treat it as the final long-term production plan until the storage plan is appropriate for the full learning period.

---

## NON-NEGOTIABLE DATA RULES

- Never commit `data_Review.txt`.
- Never commit API tokens/secrets.
- Never use future market outcomes in a live decision.
- Never represent counterfactual research as actual trading.
- Never enable real order execution during learning/validation.

---

## NEXT IMPLEMENTATION ORDER

```text
1. Verify CI for latest main
2. Verify Render deployment
3. Securely connect Render Postgres
4. Verify persistence across restart/deploy
5. Expose all planned strategies through canonical FinalDecision/Risk
6. Make After-Market Lab cover full target universe
7. Implement outcome/MFE/MAE/P&L lifecycle
8. Implement scenario engine
9. Implement persistent validated Adaptive Policy
10. Implement next-session policy load/fallback
11. Run complete production evidence
12. Begin/continue 3-month READ-ONLY learning
```

---

## NEW-CHAT CONTINUATION

> Read `PROJECT_HANDOFF.md` and `APP_ARCHITECTURE.md` from `QuantNifty-Next/main`, inspect the current repository, latest commit, CI and Render deployment, then continue implementation from the pending items. Do not restart or redesign. Update the tracker after every implementation. Only mark work complete after verification.
