# QuantNifty-Next — Persistent Project Handoff

**Purpose:** Durable cross-chat handoff/state document. A new chat must read this file first, then inspect current `main` before changing code. GitHub `main` is authoritative for implementation.

**Last updated:** 2026-09-07  
**Current branch:** `main`  
**Latest implementation commit at this tracker update:** `c5d66da14e0f7fff67e9a345fa8914b97f7277eb`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production service:** `quantnifty-api` on Render  
**Production URL:** https://quantnifty-api.onrender.com  
**Backtest UI:** https://quantnifty-api.onrender.com/backtest  
**Execution mode:** READ-ONLY; no real orders.

---

## 1. FINALIZED PRODUCT DIRECTION

QuantNifty is a **Live Adaptive Brain + After-Market Research Lab**.

The Brain must:

1. Make live decisions using only data available at decision time.
2. Operate normally from **09:20 IST through 15:15 IST**.
3. At **15:15 IST**, stop normal Adaptive Brain decisions.
4. From **15:15 to 15:30 IST**, allow only **CAS-controlled re-entry** when valid, already-produced live CAS data is present.
5. At **15:30 IST**, stop all decisions.
6. Learn continuously from live market outcomes during the planned 3-month learning period.
7. Store live market/session evidence for later evaluation.
8. After market close, replay the complete stored day and test all strategies that are actually exposed by the execution engine.
9. Keep actual live experience separate from counterfactual/research experience.
10. Generate reusable successful and failed market scenarios.
11. Update adaptive statistics/policy only after outcomes are known and only for future decisions.
12. Remain READ-ONLY throughout learning and validation.

The 3-month live-learning approach allows learning to start without waiting for a pre-existing one-year option-chain dataset. One-year historical data remains useful for broader research and validation.

---

## 2. APP ARCHITECTURE MAP

```text
                         INDSTOCKS / INDMONEY
                                  |
                    +-------------+-------------+
                    |                           |
               LIVE MARKET                 HISTORICAL/API
                    |                           |
                    v                           v
             MARKET RECORDER              RESEARCH INPUTS
                    |
          immutable live snapshots
                    |
          +---------+----------+
          |                    |
          v                    v
   LIVE ADAPTIVE BRAIN     AFTER-MARKET LAB
   09:20 -> 15:15         after 15:30
          |                    |
          |              replay complete day
          |                    |
          |       +------------+-------------+
          |       |      |       |      |     |
          |       v      v       v      v     v
          |   Directional Gamma  Adaptive  Transition/Range/etc.
          |                    |
          |             counterfactual results
          |                    |
          +---------+----------+
                    |
                    v
             LEARNING MEMORY
                    |
                    v
             VALIDATED POLICY
                    |
                    v
             FUTURE LIVE BRAIN
```

### Live decision chain

```text
Live Snapshot
 -> Analytics
 -> Institutional Signal
 -> Adaptive Strategy Selection
 -> Risk Engine
 -> FinalDecision
 -> ExecutionPlan
 -> READ-ONLY output
```

### After-market chain

```text
Stored Day
 -> deterministic replay
 -> run every supported strategy
 -> calculate P&L / MFE / MAE / drawdown
 -> compare by regime and time
 -> identify successes and failures
 -> generate scenarios
 -> update research memory
 -> validate future policy changes
```

---

## 3. STRATEGY UNIVERSE

Target Adaptive Brain strategy universe:

- `directional`
- `gamma_blast`
- `early_accumulation`
- `transition`
- `range`
- `breakout_watch`
- `standby`
- `cas_reentry` (15:15–15:30 only)
- `adaptive` top-level selector

**Current execution-engine coverage:** `directional`, `gamma_blast`, and `adaptive` are currently directly exposed to `run_backtest`/canonical decision routes. The After-Market Lab explicitly reports the remaining strategy names as pending engine exposure rather than silently substituting another strategy.

The Brain must select using current regime + current evidence + validated learned performance, with conservative fallback to an anchor strategy.

---

## 4. MARKET REGIMES / SCENARIOS

Important regimes:

- Trend / directional
- Early accumulation
- Accumulation -> breakout
- False breakout -> reversal
- Gamma blast
- Gamma transition / gamma flip
- Positive-gamma range
- Compression
- Liquidity risk
- High volatility
- Low volatility
- Expiry-day behavior
- CAS-controlled late-session re-entry
- Exhaustion / trend termination

Scenario learning must retain both positive and negative examples.

---

## 5. EARLY ACCUMULATION

Current detector uses near-ATM options, OI expansion, premium behavior, active volume, quiet/compressed spot, controlled IV, and expected-move-relative premium conditions.

States:

- `EARLY_ACCUMULATION`
- `WATCH_ACCUMULATION`
- `NO_CLEAR_ACCUMULATION`

The Brain does not claim exact bottom/top prediction. It identifies early evidence, waits for appropriate confirmation, and manages risk adaptively.

---

## 6. ADAPTIVE ENTRY / EXIT

Early accumulation entry uses:

- `EARLY_ACCUMULATION_CONFIRMATION`
- `ACCUMULATION_THEN_BREAKOUT_CONFIRMATION`

Adaptive exit currently considers:

- capital protection
- favorable move
- exhaustion / gamma reversal
- profit lock
- trailing stop
- continued trend/accumulation support

Current exit implementation is primarily spot-movement based with gamma/volume/pressure context. Option-premium/IV/Greeks/liquidity confirmation remains a research enhancement.

---

## 7. SESSION / CAS POLICY

All times are IST:

```text
Before 09:20       PRE_OPEN        no decision
09:20–15:15        NORMAL_ADAPTIVE normal Brain
15:15–15:30        CAS_REENTRY     CAS only
15:30 onward       CLOSED          no decision
```

Exact boundaries:

- 09:19:59 -> blocked
- 09:20:00 -> allowed
- 15:14:59 -> normal adaptive
- 15:15:00 -> CAS-only
- 15:29:59 -> CAS-only
- 15:30:00 -> closed

CAS must be already-produced live CAS data. The session policy must not synthesize CAS.

---

## 8. DATA INTEGRITY / LOOK-AHEAD

Live decisions require live-provider data and pass the live data-integrity gate.

Replay/backtest may use recorded historical data.

A decision at time `T` may use only information available at or before `T`.

```text
TODAY 10:00  -> decision frozen
TODAY 15:30+ -> research learns outcome
NEXT SESSION -> validated learning may influence future decisions
```

---

## 9. THREE-MONTH LIVE LEARNING PLAN

During the three-month READ-ONLY experiment:

```text
09:20
 -> capture live snapshots
 -> calculate analytics
 -> Adaptive Brain decision
 -> record decision
 -> track hypothetical lifecycle
 -> resolve MFE / MAE / outcome

15:15
 -> stop normal Brain
 -> CAS-only

15:30
 -> freeze live day
 -> run After-Market Lab
```

Learning influence must be conservative while sample sizes are small.

---

## 10. AFTER-MARKET STRATEGY LAB

After 15:30 the system must replay the stored day and compare strategies using the same market data.

Current implementation now includes `after_market_lab.py` and `after_market_scheduler.py`.

The lab currently executes:

- `directional`
- `gamma_blast`
- `adaptive`

and explicitly reports these planned strategies as pending direct execution-engine exposure:

- `early_accumulation`
- `transition`
- `range`
- `breakout_watch`

This is intentional: unsupported strategies are **not** falsely mapped to another strategy.

For tested strategies collect:

- opportunities
- trades
- wins/losses
- gross P&L
- costs
- net P&L
- win rate
- profit factor
- expectancy
- maximum drawdown
- MFE
- MAE
- holding time
- regime performance
- time-of-day performance
- expiry behavior
- false-breakout behavior where available

---

## 11. LIVE MEMORY VS RESEARCH MEMORY

**LIVE_MEMORY:** actual live Adaptive Brain decisions and hypothetical/read-only lifecycle outcomes.

**RESEARCH_MEMORY:** after-market counterfactual results for strategies that were not selected live.

Counterfactual results must never be represented as actual live trades.

The current learning store writes separate JSONL streams for:

```text
snapshots.jsonl
decisions.jsonl
outcomes.jsonl
research.jsonl
```

Each event carries `schema_version` and storage metadata.

---

## 12. SCENARIO / EXPERIENCE LIBRARY

Future research records should capture:

```text
scenario_id
start_timestamp
end_timestamp
regime
market_structure
direction
accumulation_state
GEX / DEX
IV / OI / volume context
selected_live_strategy
counterfactual_strategy_results
best_strategy
entry characteristics
exit characteristics
MFE
MAE
breakout outcome
false_breakout flag
exhaustion evidence
CAS state
outcome classification
```

Both successful and failed scenarios are valuable.

---

## 13. LEARNING / POLICY PROMOTION

```text
RAW EXPERIENCE
 -> VALIDATED EXPERIENCE
 -> LEARNED STATISTICS
 -> WALK-FORWARD / OOS VALIDATION
 -> POLICY CANDIDATE
 -> POLICY vN
 -> FUTURE LIVE READ-ONLY BRAIN
```

A policy may influence future live decisions only after the relevant outcome is closed, data is validated, no look-ahead exists, and minimum evidence thresholds are satisfied.

If a learned policy is unavailable/invalid/insufficient, fall back to the anchor strategy or standby.

---

## 14. CURRENT SOFTWARE ARCHITECTURE

Key modules:

- `main.py` — live provider ingestion, analytics, API, live recorder loop
- `institutional_engine.py` — Institutional Signal -> Risk -> FinalDecision -> ExecutionPlan
- `research_brain.py` — regime detection, accumulation, adaptive selection and exit
- `session_policy.py` — session/CAS timing policy
- `decision_validation.py` — fail-closed validation
- `replay.py` — deterministic replay
- `backtest.py` — backtest/validation execution
- `historical.py` — canonical historical contract and one-year readiness
- `recording_loader.py` — recorder ingestion
- `recording_api.py` — historical validation API
- `learning_store.py` — live learning event persistence abstraction
- `after_market_lab.py` — after-market multi-strategy research
- `after_market_scheduler.py` — daily post-close orchestration
- `adaptive_learning.py` — research policy artifact/validation helpers
- `web/backtest.html` — Backtest UI

Architecture rules remain:

- one canonical owner per domain concept
- `StrategySignal` cannot bypass Decision/Risk
- `FinalDecision` is authoritative
- Risk owns permission to trade
- ExecutionPlan describes execution only and never submits orders
- actual trade lifecycle is separate from signal/decision state
- performance consumes actual trade records
- replay reuses analytics -> decision -> risk
- UI uses stable view models
- configuration is not embedded in business logic
- time is deterministic/injectable for tests

---

## 15. LIVE RECORDER IMPLEMENTATION STATUS

Implemented:

- background live market refresh already existed and remains the source of live snapshots
- each successful live-provider snapshot is now recorded
- each live snapshot is evaluated through canonical Adaptive `FinalDecision` and recorded separately
- `/api/v1/learning/status` exposes recorder counts
- `/api/v1/status` exposes learning state
- local JSONL fallback is available for development/runtime testing
- storage is explicitly marked `FILESYSTEM_ONLY` until a durable production store is attached

**Important production limitation:** Render's current web service is a free service and the new learning store currently writes to its local filesystem. This is not sufficient as a three-month durable production data store across service replacement/deployment. A durable Render Postgres/other persistent store must be wired before relying on this as the authoritative three-month dataset.

A Render Postgres instance named `quantnifty-learning` was provisioned in Singapore as a persistence target, but application wiring/connection configuration still needs to be completed and verified.

---

## 16. AFTER-MARKET SCHEDULER STATUS

Implemented:

- scheduler starts with the API service
- weekdays only
- first run at/after **15:35 IST**
- runs once per day
- loads stored snapshots for the current day
- executes the current supported backtests
- records research results separately
- remains READ-ONLY

Pending hardening:

- durable shared store
- restart/idempotency audit beyond in-process day guard
- complete direct strategy exposure for planned sub-strategies
- richer scenario extraction

---

## 17. HISTORICAL READINESS

Software gate:

- minimum learning trading days: **252**
- minimum calendar span: **365 days**
- weekends excluded from trading-day count
- valid recorded historical provenance required
- statuses include `READY_FOR_1Y_LEARNING` and `INSUFFICIENT_1Y_DATA`

The finalized live-learning plan does not wait for this gate before collecting new live data.

---

## 18. CURRENT VALIDATION / BACKTEST SEMANTICS

Replay diagnostics and execution-loop counters have different scopes.

- **Risk Gate:** all decision observations evaluated by replay diagnostics.
- **Execution Gate:** opportunities actually considered by the backtest execution loop.

Known sample:

```text
Decision observations: 22
Risk Gate:             3 approved / 19 blocked
Execution Gate:        1 approved / 18 blocked
Actual trades:         1
```

Blocked reason counts may overlap because they are reason flags.

---

## 19. CURRENT PROJECT STATUS

### Completed / implemented

- canonical decision/risk/execution architecture
- Institutional Signal / Risk / FinalDecision / ExecutionPlan
- Adaptive selector
- market regime detection
- early accumulation detection
- accumulation -> breakout confirmation
- direction-aware selection
- adaptive exhaustion/trailing exit
- day-by-day adaptive memory in backtest
- 09:20 / 15:15 / 15:30 session policy
- CAS-only late session
- live data-integrity protection
- decision-stage validation
- replay/backtest consistency fixes
- Adaptive API/UI
- multipart strategy/config handling
- one-year readiness contract
- weekday-only readiness counting
- exact session boundary tests
- READ-ONLY execution protection
- CI regression coverage
- persistent project handoff documentation
- application architecture documentation
- **live learning recorder implementation**
- **live Adaptive decision recording**
- **after-market scheduler implementation**
- **after-market research lab implementation for currently supported strategies**
- **separate live/research event streams**
- **learning status endpoint**

### Pending major items

1. **Durable production learning storage**
   - wire the provisioned Render Postgres to the application
   - verify persistence across deployment/restart
   - migrate/retain JSONL fallback only for development

2. **Complete strategy execution exposure for After-Market Lab**
   - directly expose/test `early_accumulation`, `transition`, `range`, `breakout_watch` through the same canonical pipeline
   - never substitute another strategy silently

3. **Scenario engine**
   - extract reusable successful/failure scenarios from research results
   - persist scenario records

4. **Outcome lifecycle completion**
   - connect live decision records to resolved MFE/MAE/P&L outcomes
   - record outcomes only after resolution

5. **Persistent Adaptive Policy**
   - build/version learned policy from validated live + research evidence
   - promotion gate
   - rollback/fallback
   - insufficient-training state

6. **Three-month orchestration hardening**
   - daily completeness checks
   - restart/idempotency recovery
   - missing-data detection
   - policy load before next session

7. **Production evidence**
   - verify latest deployment
   - verify live provider -> Brain -> Risk -> FinalDecision
   - verify session boundaries and CAS
   - verify recorder persistence
   - verify after-market job
   - verify READ-ONLY guarantee

8. **Adaptive exit research**
   - evaluate option premium / IV / Greeks / liquidity confirmation using accumulated data

9. **Cleanup**
   - unused imports
   - framework deprecation warnings where appropriate

---

## 20. RECENT IMPLEMENTATION COMMITS

| Commit | Purpose |
|---|---|
| `7494bd38ebf41e4398625b4aa7955e0cb4b091ef` | Multipart/API regression baseline; CI 58 passed |
| `ae08e46264493d8f8d687520a9d9d5ee43b5f324` | Canonical decision-gate contract assertions |
| `9a921a915ba20beaad56a0c1a70c54fe90a23fd3` | One-year adaptive learning readiness endpoint |
| `3e9dd3216328be3b4360b0654a0b22961d03db9c` | Weekday-only one-year readiness count |
| `3df4a6eaef0e905952e07a1969012c816d904fb8` | Persistent project handoff + Adaptive plan |
| `a50b0f7571f2d84dc7ea05a986fe5c6f04738b2e` | Application architecture + master plan documentation |
| `1c605a3b091390a4bd2de58a620b9c5f233c5444` | Durable learning-store abstraction |
| `d8b8cfdc1b436bd1a05d320068f33e96f9ceb60e` | After-market multi-strategy research lab |
| `064ff334fc4c8547da86901a6848bdbe95e195e3` | Daily after-market scheduler |
| `512169a12a1e034b91cb24b7dfe79750f53c53c9` | Wire live Adaptive learning recorder |
| `f83bc6a65f96169fc4b696225ed51a36e38dec58` | Learning-store regression tests |
| `c5d66da14e0f7fff67e9a345fa8914b97f7277eb` | After-market lab coverage |

The tracker update itself is a separate commit after the implementation commits.

---

## 21. CI / DEPLOYMENT EVIDENCE

Previously verified CI:

- run `34076388908`
- job `101603230111`
- **77 passed, 6 warnings**
- compileall passed

The new learning-store/lab commits have been pushed after that verification. Their CI and production deployment must be checked before calling this implementation production-validated.

Do not claim a Render deployment is live without checking current Render deployment state.

---

## 22. DATA / SECRET RULES

- `data_Review.txt` must not be committed.
- Raw market recordings belong in durable external storage, not source control.
- API tokens/secrets must never be committed.
- Provider token environment variable: `INDSTOCKS_API_TOKEN`.

---

## 23. RENDER / PRODUCTION

Workspace: `quantnifty-next`  
Service: `quantnifty-api`  
Region: Singapore  
Production: https://quantnifty-api.onrender.com  
Backtest: https://quantnifty-api.onrender.com/backtest

Render auto-deploys `main`.

A Render Postgres target named `quantnifty-learning` was created in Singapore on 2026-09-07. It is currently a free database with an expiry shown by Render; it must not be treated as the final long-term three-month production store until an appropriate durable plan/configuration is confirmed.

---

## 24. NEXT IMPLEMENTATION ORDER

Do not redesign the project.

```text
1. Verify CI for the new recorder/lab commits
2. Verify latest Render deployment
3. Wire durable production storage
4. Verify recorder persistence across restart/deploy
5. Complete direct exposure of every planned strategy through canonical FinalDecision/Risk
6. Make After-Market Lab test every planned strategy
7. Implement scenario extraction/persistence
8. Implement resolved live outcome/MFE/MAE/P&L lifecycle
9. Implement persistent validated Adaptive Policy
10. Add daily policy load/fallback
11. Add full production evidence
12. Begin 3-month READ-ONLY learning period
13. Review evidence before any execution enablement
```

### Non-negotiable

`orders_placed = 0` and `trading_enabled = false` throughout learning/validation until separately authorized.

---

## 25. NEW-CHAT CONTINUATION INSTRUCTION

Use:

> **Read `PROJECT_HANDOFF.md` and `APP_ARCHITECTURE.md` from QuantNifty-Next main. Inspect the current repository, latest commit, CI and Render deployment. Continue implementation from the documented pending items. Do not restart or redesign the project. Update the tracker after every implementation and only mark work complete after verification.**

The tracker is persistent project context, not a substitute for inspecting current source code.
