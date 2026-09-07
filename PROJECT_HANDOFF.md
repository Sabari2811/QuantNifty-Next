# QuantNifty-Next — Persistent Project Handoff

**Purpose:** This file is the durable handoff/state document for continuing QuantNifty-Next across chats. A new chat should read this file first, then inspect the current `main` branch before changing code. GitHub `main` remains the authoritative source of implementation.

**Last updated:** 2026-09-07  
**Current branch:** `main`  
**Current latest commit at handoff creation:** `3e9dd3216328be3b4360b0654a0b22961d03db9c` — `Make one-year readiness count trading weekdays only`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production service:** `quantnifty-api` on Render  
**Production URL:** https://quantnifty-api.onrender.com  
**Backtest UI:** https://quantnifty-api.onrender.com/backtest  
**Execution mode:** READ-ONLY; no real orders.

---

## 1. FINALIZED PRODUCT DIRECTION

QuantNifty is evolving into a **Live Adaptive Brain + After-Market Research Lab**.

The Brain must:

1. Make live decisions using only data available at decision time.
2. Operate normally from **09:20 IST through 15:15 IST**.
3. At **15:15 IST**, stop normal Adaptive Brain decisions.
4. From **15:15 to 15:30 IST**, allow only **CAS-controlled re-entry** when valid, already-produced live CAS data is present.
5. At **15:30 IST**, stop all decisions because the market session is closed.
6. Learn continuously from live market outcomes during the planned 3-month learning period.
7. Store the complete live market/session evidence needed to evaluate decisions later.
8. After market close, replay the entire stored day and test **all supported strategies**, not only the strategy selected live.
9. Separate actual live experience from counterfactual/research experience.
10. Generate reusable market scenarios from successful and failed patterns.
11. Update adaptive statistics/policy only after the relevant outcome is known and only for future decisions.
12. Remain READ-ONLY throughout the learning/validation period.

The 3-month live-learning approach replaces the requirement to wait for a pre-existing one-year option-chain dataset before the Brain can start learning. A one-year historical dataset remains useful for broader research, but it is **not required to start this live-learning experiment**.

---

## 2. CORE ARCHITECTURE MAP

```text
                         INDSTOCKS / INDMONEY
                                  |
                    +-------------+-------------+
                    |                           |
               Live market                 Historical/API
                 inputs                     research inputs
                    |
                    v
             +----------------+
             | Market Recorder|
             +----------------+
                    |
             immutable snapshots
                    |
          +---------+----------+
          |                    |
          v                    v
   LIVE ADAPTIVE BRAIN     AFTER-MARKET LAB
   09:20 -> 15:15         after 15:30
          |                    |
          |              replay entire day
          |                    |
          |       +------------+-------------+
          |       |      |       |      |     |
          |       v      v       v      v     v
          |   Directional Accumulation Gamma Transition Range
          |       |      |       |      |     |
          |       +------+-------+------+-----+
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
Stored day
    -> deterministic replay
    -> run every strategy
    -> calculate trade outcomes
    -> MFE / MAE / P&L / win/loss / drawdown
    -> compare strategies by regime
    -> identify successful/failure scenarios
    -> update research memory
    -> validate policy changes
```

---

## 3. STRATEGY UNIVERSE

Current Adaptive Brain strategy candidates:

- `directional`
- `gamma_blast`
- `transition`
- `early_accumulation`
- `range`
- `breakout_watch`
- `standby`
- `cas_reentry` during 15:15–15:30 only
- `adaptive` as the top-level selector

The Brain should not blindly choose the historically best strategy. It should choose based on **current regime + current evidence + validated learned performance**, with conservative fallback to the anchor strategy.

---

## 4. MARKET REGIMES / SCENARIOS

Important regimes include:

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

Scenario learning should capture both **success and failure** patterns.

Example:

```text
ACCUMULATION -> BREAKOUT -> EXHAUSTION
```

and:

```text
ACCUMULATION -> BREAKOUT -> FAILED BREAKOUT -> REVERSAL
```

The latter is especially valuable for improving confirmation gates and avoiding fake breakouts.

---

## 5. EARLY ACCUMULATION LOGIC

The Brain is designed to detect possible accumulation **before a confirmed breakout**, rather than waiting for the entire move.

Current evidence includes:

- near-ATM option rows
- OI expansion
- premium stable/rising
- active volume
- spot quiet/compressed
- controlled IV
- expected-move-relative premium condition

Current accumulation states:

- `EARLY_ACCUMULATION`
- `WATCH_ACCUMULATION`
- `NO_CLEAR_ACCUMULATION`

The system must never claim it can know the exact bottom/top. The goal is to identify **early evidence with confirmation and adaptive risk**, not predict exact turning points.

---

## 6. ADAPTIVE ENTRY / EXIT

### Entry

For `early_accumulation`, the execution plan uses stronger confirmation stages rather than blindly entering on the first accumulation signal.

Current confirmation concepts:

- `EARLY_ACCUMULATION_CONFIRMATION`
- `ACCUMULATION_THEN_BREAKOUT_CONFIRMATION`

### Exit

Current adaptive exit state considers:

- capital protection
- favorable move
- exhaustion / gamma reversal
- profit lock
- trailing stop activation
- continued trend/accumulation support

Current implementation is primarily **spot-movement based with gamma/volume/pressure context**. A future enhancement may add stronger option-premium/IV/Greeks/liquidity confirmation after sufficient data and tests are available.

---

## 7. SESSION / CAS POLICY

All times are IST.

```text
Before 09:20       PRE_OPEN       no decision
09:20–15:15        NORMAL_ADAPTIVE normal Brain allowed
15:15–15:30        CAS_REENTRY    normal Brain stopped; CAS only
15:30 onward       CLOSED         no decision
```

Exact boundaries are important:

- 09:19:59 -> blocked
- 09:20:00 -> allowed
- 15:14:59 -> normal adaptive
- 15:15:00 -> CAS-only
- 15:29:59 -> CAS-only
- 15:30:00 -> closed

CAS must be **already-produced live CAS data**. The session policy must not synthesize CAS to manufacture a trade.

---

## 8. DATA INTEGRITY / LOOK-AHEAD RULES

### Live decisions

Live decisions must use live provider data and must pass the live data-integrity gate.

### Historical/replay decisions

Recorded historical data may be used for replay/backtest/research.

### Look-ahead prohibition

A decision at timestamp `T` may use only information available at or before `T`.

Future market movement, future outcome, or after-market replay result must never be injected into the original live decision.

```text
TODAY 10:00
  decision is frozen

TODAY 15:30+
  research learns what happened

TOMORROW 09:20+
  validated learning can influence future decisions
```

---

## 9. LIVE LEARNING LOOP — 3 MONTH EXPERIMENT

During the planned 3-month learning period:

```text
09:20
  -> start live learning
  -> capture snapshots continuously
  -> compute analytics
  -> make Adaptive Brain decision
  -> record decision state
  -> track hypothetical/READ-ONLY trade lifecycle
  -> record MFE / MAE / outcome

15:15
  -> stop normal Brain
  -> CAS-only policy

15:30
  -> close live session
  -> freeze live-day records
  -> launch after-market research
```

The Brain can operate from Day 1, but learned overrides must be conservative while sample sizes are small.

Suggested learning progression (configurable, not a hard-coded claim):

```text
Small sample      -> baseline/anchor dominates
Growing sample    -> learned statistics have limited influence
Strong sample     -> learned policy can influence selection
Validated sample  -> policy candidate eligible for promotion
```

---

## 10. AFTER-MARKET LAB — FINALIZED REQUIREMENT

After 15:30, the system must replay the complete stored market day and test **all strategies** against the same data.

At minimum:

1. Directional
2. Early Accumulation
3. Gamma Blast
4. Gamma Transition
5. Range
6. Breakout/confirmation behavior
7. Adaptive
8. CAS re-entry where the session window applies
9. Relevant exit policies

For every strategy, collect:

- number of opportunities
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
- false breakout rate
- regime-specific performance
- time-of-day performance
- expiry behavior where applicable

### Critical separation

**LIVE_MEMORY** = what the Brain actually selected/experienced live.

**RESEARCH_MEMORY** = what every strategy would have done when replayed after close.

Counterfactual results must never be represented as actual live trades.

---

## 11. SCENARIO / EXPERIENCE LIBRARY

The After-Market Lab should convert important replay outcomes into reusable scenarios.

Example schema:

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
CAS state if applicable
outcome classification
```

Scenario classifications should include both positive and negative examples.

---

## 12. LEARNING / POLICY PROMOTION RULES

Learning must be **outcome-aware but future-safe**.

A research result becomes eligible to influence future decisions only after:

1. the relevant outcome is closed,
2. the data is validated,
3. the sample belongs to the appropriate regime/strategy bucket,
4. no look-ahead contamination is present,
5. policy comparison passes the configured minimum evidence threshold.

The eventual live policy should be versioned, validated and reversible.

Recommended promotion lifecycle:

```text
RAW EXPERIENCE
      -> VALIDATED EXPERIENCE
      -> LEARNED STATISTICS
      -> WALK-FORWARD/OOS VALIDATION
      -> POLICY CANDIDATE
      -> POLICY vN
      -> LIVE READ-ONLY
```

If a learned policy is unavailable, insufficiently trained, invalid, or fails validation, the system must safely fall back to the anchor strategy / standby rather than forcing learned behavior.

---

## 13. CURRENT SOFTWARE ARCHITECTURE

Key modules:

- `main.py` — live provider ingestion, analytics, API routes
- `institutional_engine.py` — Institutional Signal -> RiskEngine -> FinalDecision -> ExecutionPlan
- `research_brain.py` — regime detection, adaptive strategy selection, accumulation, adaptive exit, learning memory helpers
- `session_policy.py` — 09:20/15:15/15:30 session policy and CAS-only late-session behavior
- `decision_validation.py` — snapshot/decision-stage validation and fail-closed consistency checks
- `replay.py` — deterministic replay
- `backtest.py` — backtest/validation execution loop
- `strike_selector.py` — strike policy
- `historical.py` — canonical historical snapshot contract and 1-year readiness gate
- `recording_loader.py` — recorded Parquet/JSON ingestion
- `recording_api.py` — historical replay/validation API
- `web/backtest.html` — Backtest UI

Architecture rules:

- One canonical owner per domain concept.
- `StrategySignal` must not bypass Decision/Risk.
- `FinalDecision` is authoritative.
- Risk owns permission to trade.
- `ExecutionPlan` describes execution only and never submits orders.
- Actual trade lifecycle state is separate from signal/decision state.
- Performance consumes actual trade records.
- Replay reuses the same analytics -> decision -> risk pipeline.
- UI uses stable view models.
- Configuration should not be hard-coded into business logic.
- Time must be deterministic/injectable for tests.

---

## 14. CURRENT VALIDATION / BACKTEST SEMANTICS

Replay diagnostics evaluate decision observations independently of the backtest execution loop.

Therefore two gate counters are intentionally retained:

- **Risk Gate** = all decision observations evaluated by replay diagnostics.
- **Execution Gate** = opportunities evaluated by the backtest execution loop, which can skip new entries while a position is open.

Example known scenario:

```text
Decision observations: 22
Risk Gate:             3 approved / 19 blocked
Execution Gate:        1 approved / 18 blocked
Actual trades:         1
```

These are different scopes and must not be collapsed.

Blocked reason counts can overlap because they are reason flags, not necessarily mutually exclusive categories.

---

## 15. HISTORICAL READINESS

The software has a historical readiness contract:

- minimum learning trading days: **252**
- minimum learning calendar span: **365 days**
- trading-day count excludes weekends
- provenance must be valid recorded historical data
- readiness states include `READY_FOR_1Y_LEARNING` and `INSUFFICIENT_1Y_DATA`

This gate remains useful for broader historical research, but the finalized 3-month live-learning plan does not wait for it before collecting live experience.

Known recorder evidence available before this plan was only a small sample (about 23 market-hours snapshots across roughly 11 trading days), so it is not sufficient to claim one-year strategy performance.

---

## 16. CURRENT PROJECT STATUS AT HANDOFF

### Completed / implemented

- Canonical architecture and decision/risk/execution separation
- Institutional Signal / RiskEngine / FinalDecision / ExecutionPlan flow
- Adaptive strategy selector
- Market regime detection
- Early accumulation detector
- Accumulation -> breakout confirmation path
- Direction-aware strategy selection
- Adaptive exhaustion/trailing exit logic
- Day-by-day adaptive memory in backtest
- 09:20 normal Brain start
- 15:15 CAS-only transition
- 15:30 market close stop
- Live data-integrity protection
- Decision-stage validation
- Replay/backtest consistency improvements
- Adaptive API/UI support
- Multipart strategy/config handling fix
- One-year historical readiness endpoint/contract
- Weekend exclusion from trading-day readiness count
- Exact session-boundary test coverage
- READ-ONLY execution protection
- CI regression coverage

### Current major work remaining

1. **Persistent live market recorder / learning store**
   - durable storage of live snapshots, decisions, outcomes and counterfactual research results
   - must survive service restarts/deployments
   - must be separated from secrets and code

2. **After-Market Strategy Lab**
   - automatically run after close
   - replay the entire stored day
   - execute all strategy simulations
   - calculate comparative metrics
   - produce scenario records

3. **Scenario / Counterfactual experience store**
   - distinguish actual live decisions from hypothetical alternatives
   - retain successful and failed scenarios

4. **Persistent Adaptive Policy**
   - versioned learned statistics/policy
   - validation gate
   - rollback/fallback to anchor
   - explicit insufficient-training state

5. **Three-month learning orchestration**
   - daily live capture
   - after-close research job
   - next-session policy loading
   - monitoring of data completeness

6. **Production validation for the complete new loop**
   - live snapshot -> Adaptive Brain -> Risk -> FinalDecision
   - 09:20/15:15/15:30 behavior
   - CAS re-entry gate
   - recorder persistence
   - after-market replay
   - READ-ONLY guarantee

7. **Additional exit research**
   - evaluate option-premium / IV / Greeks / liquidity confirmation for adaptive exits using real accumulated data

8. **Cleanup**
   - remove unused imports and address non-blocking framework deprecation warnings where appropriate.

---

## 17. KNOWN IMPORTANT COMMITS

| Commit | Purpose |
|---|---|
| `7494bd38ebf41e4398625b4aa7955e0cb4b091ef` | Multipart/API regression baseline; CI 58 passed |
| `208488...` | Adaptive research fixture/counterfactual fixes |
| `0d586...` | Adaptive Brain UI selector |
| `ae08e46264493d8f8d687520a9d9d5ee43b5f324` | Finalize canonical decision-gate contract assertions |
| `9a921a915ba20beaad56a0c1a70c54fe90a23fd3` | Expose one-year adaptive learning readiness |
| `3e9dd3216328be3b4360b0654a0b22961d03db9c` | Make one-year readiness count trading weekdays only |

At this handoff, `3e9dd3216328be3b4360b0654a0b22961d03db9c` is the verified latest `main` commit.

---

## 18. CI / VALIDATION EVIDENCE

Latest verified CI associated with the readiness work:

- GitHub Actions run `34076388908`
- Job `101603230111`
- **77 passed, 6 warnings**
- compileall passed

Warnings were non-fatal framework/action deprecations.

A later production-evidence workflow was observed running against the readiness commit; its final result must be rechecked before being called successful.

Do not claim a production deployment/evidence result without rechecking current Render/GitHub state.

---

## 19. DATA / FILE RULES

- `data_Review.txt` is recorder export evidence and must **not** be committed to GitHub.
- Raw market recordings should be stored outside Git source control or in an explicitly designed durable data store.
- Secrets/API tokens must never be committed to this repository.
- Existing environment variable for the provider token is `INDSTOCKS_API_TOKEN`.

---

## 20. RENDER / PRODUCTION

Render workspace: `quantnifty-next`  
Service: `quantnifty-api`  
Region: Singapore  
Production: https://quantnifty-api.onrender.com  
Backtest UI: https://quantnifty-api.onrender.com/backtest

Render auto-deploys `main`. Always inspect the current deployment before declaring a newly pushed commit live.

---

## 21. NEXT IMPLEMENTATION ORDER

Do not redesign the project. Continue from `main`.

Recommended implementation order:

```text
1. Inspect current main + this handoff
2. Verify latest Render deployment + CI
3. Implement durable live recorder / learning store
4. Implement after-market orchestration
5. Replay all strategies on stored day
6. Persist counterfactual/scenario results
7. Add daily learning/policy update pipeline
8. Add versioned validated Adaptive Policy with safe fallback
9. Add production evidence for the complete loop
10. Run the 3-month READ-ONLY learning period
11. Review evidence and only then consider any execution enablement
```

### Non-negotiable

**No real-money order execution during the learning/validation phase.**

The system may generate signals, simulate trades, calculate hypothetical P&L, and learn from market data, but `orders_placed` must remain zero and live trading must remain disabled until separately authorized after validation.

---

## 22. NEW-CHAT CONTINUATION INSTRUCTION

When continuing this project in a new chat, the first instruction can be:

> **Read `PROJECT_HANDOFF.md` from QuantNifty-Next main, inspect the current repository state and latest commit, then continue implementation from the documented pending items. Do not restart or redesign the project. Verify before claiming completion.**

This file is a handoff, not a substitute for inspecting current source code. The new chat must still inspect the repository and current CI/Render state before modifying or reporting status.
