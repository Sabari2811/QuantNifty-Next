# QuantNifty-Next — Application Architecture & Implementation Plan

This document defines the finalized application-level architecture and execution plan. `PROJECT_HANDOFF.md` is the persistent project tracker; this document is the detailed application architecture reference. Both must be kept aligned whenever architecture changes.

## 1. Product Goal

QuantNifty is a READ-ONLY NIFTY signal and research platform built around an Adaptive Brain.

The application has two complementary operating modes:

- **Live Learning Mode:** consume live INDstocks/INDMoney market data, generate decisions using only information available at that moment, and record read-only paper outcomes.
- **After-Market Research Mode:** after market close, replay the stored day and test every research strategy against the same market observations to generate counterfactual experience and scenarios.

The initial learning program is planned for approximately three months. Real-money order execution remains disabled during learning and validation.

## 2. High-Level Application Map

```text
                         +----------------------+
                         | INDSTOCKS / INDMONEY  |
                         +----------+-----------+
                                    |
                     +--------------+--------------+
                     |                             |
                     v                             v
              LIVE MARKET DATA          PRE-EXISTING HISTORICAL DATA
                     |                    (REFERENCE / REPLAY ONLY)
                     |                             |
                     v                             |
              +----------------+                   |
              | LIVE RECORDER  |                   |
              +-------+--------+                   |
                      |                            |
                      v                            |
              +----------------+                   |
              | STORED DAY     |<------------------+
              | LIVE EVIDENCE   |       historical data never trains live memory
              +-------+--------+
                      |
                      v
                         +----------------------+
                         | CANONICAL SNAPSHOT   |
                         | + DATA VALIDATION    |
                         +----------+-----------+
                                    |
                  +-----------------+------------------+
                  |                                    |
                  v                                    v
       +------------------------+           +------------------------+
       | LIVE ADAPTIVE BRAIN    |           | AFTER-MARKET LAB        |
       | 09:20 - 15:15          |           | Stored same-day replay  |
       +-----------+------------+           +-----------+------------+
                   |                                    |
                   v                           +---------+----------+
       +------------------------+              |                    |
       | ANALYTICS / REGIME     |              v                    v
       | GEX DEX OI IV Volume   |       ALL STRATEGIES       SCENARIO ENGINE
       +-----------+------------+              |                    |
                   |                           +---------+----------+
                   v                                     |
       +------------------------+                         v
       | STRATEGY SELECTOR      |              +------------------+
       | Adaptive policy        |              | RESEARCH MEMORY  |
       +-----------+------------+              +--------+---------+
                   |                                    |
                   v                                    v
       +------------------------+              +------------------+
       | RISK ENGINE            |              | POLICY VALIDATOR |
       | permission to trade    |              +--------+---------+
       +-----------+------------+                       |
                   |                                    v
                   v                           +------------------+
       +------------------------+              | FUTURE LIVE BRAIN|
       | FINAL DECISION         |              +------------------+
       | authoritative output   |
       +-----------+------------+
                   |
                   v
       +------------------------+
       | EXECUTION PLAN         |
       | READ-ONLY / no orders  |
       +-----------+------------+
                   |
                   v
       +------------------------+
       | LIVE PAPER OUTCOME     |
       | MFE / MAE / P&L        |
       +-----------+------------+
                   |
                   v
            DURABLE STORE
```

**Finalized learning-source rule:** pre-existing historical/research inputs such as `data_Review.txt` are reference/replay evidence only. They are never a live-learning bootstrap and never seed, train, promote, or influence the live Adaptive Brain or its policy memory. Only `LIVE_PROVIDER` observations and completed same-day `STORED_DAY` observations are learning sources.

## 3. Live Decision Architecture

```text
Live Provider
    -> Canonical Snapshot
    -> Snapshot Validation
    -> Analytics
    -> Regime Detection
    -> Adaptive Strategy Selection
    -> Institutional Signal
    -> Risk Engine
    -> Session/CAS Policy
    -> FinalDecision
    -> ExecutionPlan
    -> Live Paper Outcome Lifecycle
    -> Durable Learning Store
    -> READ-ONLY API/UI
```

### Responsibilities

**Provider layer**
- Obtain live market information from INDstocks/INDMoney.
- Never embed credentials in source code.

**Canonical snapshot layer**
- Normalize provider output into the application's stable snapshot contract.
- Attach provenance and timestamp.

**Analytics layer**
- Compute GEX, DEX, gamma walls, gamma flip/transition, OI flow, IV skew, expected move, PCR, market structure, liquidity and other approved features.

**Adaptive Brain**
- Detect regime.
- Detect early accumulation.
- Choose the most suitable validated strategy for the current state.
- Use learned evidence conservatively.
- Accept an explicit research-only strategy override during after-market replay; live mode does not expose arbitrary overrides.

**Risk Engine**
- Own the permission to trade.
- Fail closed on invalid data or failed risk gates.

**FinalDecision**
- Authoritative decision object.
- Must be the only downstream decision authority.

**ExecutionPlan**
- Describes what a permitted execution would look like.
- Never submits an order.

**Recorder / Learning Store**
- Persist the exact evidence needed to reproduce and evaluate the decision later.
- Store snapshots, decisions, paper outcomes and research separately.

## 4. Session Architecture

All times are IST.

```text
PRE_OPEN
before 09:20
    -> no Adaptive decision

NORMAL_ADAPTIVE
09:20:00 through 15:14:59
    -> Adaptive Brain active

CAS_REENTRY
15:15:00 through 15:29:59
    -> normal Brain stopped
    -> only already-produced valid live CAS may authorize re-entry

CLOSED
15:30:00 onward
    -> no decision
    -> active paper trade closes as SESSION_CLOSE
```

CAS is an input to the session policy, not something synthesized solely to create a trade.

## 5. Strategy Architecture

The strategy registry remains explicit and testable.

```text
ADAPTIVE
  |
  +-- Directional
  +-- Early Accumulation
  +-- Gamma Blast
  +-- Gamma Transition
  +-- Range
  +-- Breakout / Confirmation
  +-- CAS Re-entry
  +-- Standby
```

Strategy selection is based on:

1. Current market regime.
2. Current live evidence.
3. Current risk/liquidity conditions.
4. Validated learned performance.
5. Minimum sample requirements.
6. Safe fallback policy.

The Brain must not blindly select whichever strategy has the highest historical P&L. In this finalized plan, historical means pre-existing recordings only and is excluded from learning; strategy evidence is derived from live outcomes and same-day post-market research.

Live API strategy exposure remains `directional`, `gamma_blast`, `adaptive`. After-market research covers `directional`, `gamma_blast`, `adaptive`, `early_accumulation`, `transition`, `range`, and `breakout_watch` through the canonical Adaptive Brain/FinalDecision/Risk pipeline.

## 6. Early Accumulation Architecture

The objective is to identify potential accumulation before a confirmed breakout while preserving confirmation and risk controls.

Evidence can include:

- near-ATM option OI expansion
- premium stability/rise
- active volume
- quiet/compressed spot
- controlled IV
- expected-move-relative premium
- market structure
- gamma/DEX context

States:

```text
NO_CLEAR_ACCUMULATION
WATCH_ACCUMULATION
EARLY_ACCUMULATION
```

The system must not claim exact bottom/top prediction.

## 7. Adaptive Exit Architecture

Exit decisions can use:

- capital-protection threshold
- favorable move
- exhaustion
- gamma reversal
- volume/pressure deterioration
- profit-lock trigger
- trailing stop
- continued trend/accumulation support

Current implementation is primarily spot-based with gamma/volume/pressure context. Option premium, IV, Greeks and liquidity confirmation should be researched and added only after enough real observations and tests exist.

## 8. Market Recorder

The recorder is a first-class application component.

Each stored observation should preserve, where available:

```text
record_id
session_date
timestamp
provider
provenance
spot
complete option_chain payload
analytics
Greeks available from provider
Delta / Gamma / Theta / Vega where supplied
Vanna when supplied or validly derived by the analytics layer
OI / previous OI / volume
bid / ask / quantities
IV
regime
CAS state
signal
risk decision
final decision
execution plan
learning-policy version
```

Records must be immutable for the completed decision timestamp. Fields are not invented when the provider does not supply them.

The storage must be durable across service restarts and Render deployments. Raw recordings should not be committed to GitHub.

## 9. Live Learning Store

The learning store separates:

### LIVE_MEMORY
What the Brain actually selected and what happened afterward.

### RESEARCH_MEMORY
What alternative strategies would have done when replayed after market close.

### SCENARIO_MEMORY
Reusable descriptions of market patterns, including both successful and failed outcomes.

A live decision must never be retroactively modified because a later replay produced a better strategy.

PostgreSQL is supported through `QUANTNIFTY_DATABASE_URL` or `DATABASE_URL`, with JSONL filesystem fallback. Production must wire the Render service to the database without committing credentials.

Daily live evidence is appended incrementally. Snapshots, decisions, closed paper outcomes and after-market research are retained as separate durable event types so P&L and strategy learning cannot be confused with counterfactual results.

## 10. After-Market Strategy Lab

Trigger after the market closes at 15:35 IST.

```text
Freeze day
   -> verify completeness
   -> load stored snapshots
   -> deterministic replay
   -> run Directional
   -> run Early Accumulation
   -> run Gamma Blast
   -> run Gamma Transition
   -> run Range
   -> run Breakout/Confirmation
   -> run Adaptive
   -> evaluate CAS window
   -> evaluate exit policies
   -> calculate metrics
   -> generate scenarios
   -> update research memory
   -> validate policy candidate
   -> persist complete daily training record
```

All strategies must see the same stored information at each replay timestamp. Explicit research strategies are routed through the canonical Adaptive Brain/FinalDecision/Risk stack and marked research-only.

The daily research event is persisted only after scenarios and the policy result are attached. The scheduler marks a day complete only after a `COMPLETED` result is durably saved; `NO_DATA` and failures remain retryable, and persisted completion is recognized after restart.

## 11. Counterfactual Testing

For every replay day, compare strategies without confusing simulated results with live outcomes.

Metrics should include:

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
- false-breakout rate
- time-of-day performance
- regime performance
- expiry performance

## 12. Scenario Engine

The Scenario Engine converts meaningful sequences into reusable experience.

Examples:

```text
Compression
 -> Early Accumulation
 -> Breakout
 -> Momentum
 -> Exhaustion
```

```text
Compression
 -> Early Accumulation
 -> Breakout
 -> Failed Breakout
 -> Reversal
```

```text
Gamma Transition
 -> Volatility Expansion
 -> Directional Move
 -> Exhaustion
```

Scenario records preserve both positive and negative examples so that the Brain learns when **not** to act. Scenario results are persisted in the durable `research` event stream after the daily replay.

## 13. Learning Policy

The Brain should learn from closed outcomes only.

```text
Live Market evidence
    -> Decision frozen
    -> Outcome resolved
    -> Same-day research replay
    -> Validate evidence
    -> Update statistics
    -> Evaluate policy change
    -> Walk-forward/OOS checks where applicable
    -> Promote validated policy for a future session
```

**No historical bootstrap:** there is no 252-trading-day gate, 365-calendar-day gate, or historical performance prerequisite. Strategy promotion still requires its own minimum evidence and validation rules; these are not historical-data startup gates.

Learned behavior must be conservative at low sample sizes.

Recommended safety states:

```text
INSUFFICIENT_TRAINING
LEARNING
VALIDATING
POLICY_CANDIDATE
VALIDATED
FALLBACK
```

The versioned `adaptive-policy-v1` contract requires minimum samples and improvement over the Adaptive anchor before promotion. Persisted policy artifacts must declare `future_safe=true` and `counterfactual_source=true`.

## 14. Three-Month Learning Plan

### Stage 1 — Startup / Day 1

- Start recorder.
- Validate live provider data.
- Run Adaptive Brain in READ-ONLY mode.
- Record all decisions and market evidence.
- Do not let learned memory override the baseline aggressively.

### Stage 2 — Daily Learning

Every trading day:

- capture live snapshots
- record decisions
- resolve simulated paper outcomes
- calculate MFE/MAE and P&L proxy
- close the day
- run the After-Market Lab
- test all strategies
- generate scenarios
- validate/persist policy
- persist the complete daily training/research record

### Stage 3 — Growing Evidence

As observations accumulate:

- compare strategies by regime
- identify false-breakout conditions
- identify early-accumulation conditions
- identify exhaustion signatures
- compare entry timing
- compare exit behavior
- monitor drawdown and stability

### Stage 4 — Policy Validation

Before learned behavior can materially override the anchor:

- require minimum sample size
- check data quality
- check look-ahead contamination
- compare against baseline
- perform walk-forward/OOS validation where enough sequential data exists
- reject unstable policies

### Stage 5 — Three-Month Review

At the end of the learning period produce:

- strategy leaderboard
- regime leaderboard
- Adaptive vs anchor comparison
- live vs counterfactual comparison
- MFE/MAE analysis
- false-breakout analysis
- CAS analysis
- drawdown analysis
- policy version recommendation

No live execution activation should happen merely because the three-month period ended; promotion requires evidence and explicit authorization.

## 15. Data Integrity Rules

Non-negotiable:

- No future information in a historical/replay decision.
- No after-market results injected into the original live decision.
- No synthetic CAS created to manufacture trades.
- Live decisions require live provider provenance.
- Same-day post-market replay uses only that day's stored live evidence.
- Pre-existing historical recordings are replay/reference only and are excluded from learning/policy memory.
- Raw secrets never enter recordings or Git.
- Completed records are immutable.
- Actual live trades and simulated/counterfactual trades remain separate.

## 16. Current Code Ownership Map

```text
main.py
  -> provider ingestion + API + live refresh + paper outcome integration

institutional_engine.py
  -> signal -> risk -> final decision -> execution plan

research_brain.py
  -> regime + accumulation + adaptive selection + adaptive exit + memory helpers + research override + future-safe policy input

session_policy.py
  -> market session and CAS policy

decision_validation.py
  -> snapshot and decision validation

replay.py
  -> deterministic replay

backtest.py
  -> simulation/backtest execution loop

historical.py
  -> snapshot contract + provenance diagnostics only; no learning gate

recording_loader.py
  -> recording ingestion

recording_api.py
  -> historical replay/validation API

paper_trade_tracker.py
  -> read-only paper trade lifecycle and MFE/MAE

live_paper_manager.py
  -> live open/update/close/recovery integration

research_strategy_runner.py
  -> full after-market strategy coverage through canonical Adaptive pipeline

after_market_lab.py
  -> daily research, scenario persistence and complete training record

after_market_scheduler.py
  -> weekday after-market orchestration with durable completion/retry semantics

scenario_engine.py
  -> deterministic counterfactual scenario extraction

adaptive_policy.py
  -> versioned policy validation/promotion gate

adaptive_learning.py
  -> live-only policy helper; rejects pre-existing historical learning sources

policy_runtime.py
  -> policy persistence, versioning and prior-day loading

learning_store.py
  -> PostgreSQL/JSONL learning event persistence

web/backtest.html
  -> research/backtest UI
```

New components should have one clear canonical owner and should reuse existing decision/risk/replay infrastructure rather than creating parallel implementations.

## 17. Implementation Roadmap

```text
[CURRENT FOUNDATION]
      |
      v
1. Durable Live Recorder
      |
      v
2. Learning/Event Store
      |
      v
3. After-Market Orchestrator
      |
      v
4. All-Strategy Replay Runner
      |
      v
5. Counterfactual + Scenario Engine
      |
      v
6. Daily Research Aggregation
      |
      v
7. Adaptive Policy Builder
      |
      v
8. Policy Validation / Versioning / Rollback
      |
      v
9. Production Evidence + Monitoring
      |
      v
10. Three-Month READ-ONLY Learning
      |
      v
11. Final Evidence Review
      |
      v
12. Explicit decision on any future execution enablement
```

Current implementation has completed items 1–8 in code; production evidence and durable Render wiring remain verification gates, not reasons to enable trading.

## 18. Definition of Done for the Learning System

The learning system is not considered complete until:

- live snapshots are durably stored
- live decisions are durably stored
- simulated outcomes are durably stored
- after-market replay runs automatically
- every strategy is tested on the same day data
- actual and counterfactual experiences are separated
- scenarios are generated and searchable
- policy versions are persisted
- policy validation is enforced
- fallback works
- look-ahead tests pass
- session boundary tests pass
- READ-ONLY protection passes
- CI passes
- production evidence confirms the complete pipeline

## 19. Change Management

Every implementation change must update `PROJECT_HANDOFF.md`.

The tracker update must include, where applicable:

- date
- implementation item
- files changed
- tests added/changed
- commit SHA
- CI result
- deployment result
- production validation result
- remaining work
- next implementation item

Never mark an item complete solely because code was written. Mark it complete only after the relevant verification succeeds.

## 20. Finalized Learning Plan Addendum — 2026-09-07

This section is authoritative for the finalized learning behavior and supersedes any older wording above that refers to historical bootstrap learning.

### Learning sources
- `LIVE_PROVIDER`: current live observations are the only input to live decisions and live learning.
- `STORED_DAY`: immutable same-day live recordings are the only input to that day's after-market training/research.
- `RECORDED_HISTORICAL` / `data_Review.txt`: reference/replay evidence only; never a training, seeding, promotion, or policy-memory source.

### Daily persistence
- During the session, persist snapshots, decisions and closed read-only paper outcomes incrementally.
- Preserve all provider fields that are actually available, including OI, previous OI, volume, IV, bid/ask and supplied Greeks; Vanna is retained when supplied or validly derived, never fabricated.
- After 15:35 IST, automatically run the full research universe against that stored day.
- Persist scenarios and policy results.
- Persist the complete daily after-market training record after enrichment.
- A scheduler run is complete only after the result is durably saved. Missing data/errors are retryable and restart recovery checks durable completion.

### Historical gate removal
- No 252-trading-day requirement.
- No 365-calendar-day requirement.
- No historical performance requirement to start learning.
- Strategy-level minimum sample and validation rules remain safety controls and are not historical bootstrap gates.

### Operational safety
- READ-ONLY remains mandatory.
- Live decisions are never retroactively changed by post-market research.
- Counterfactual results remain labeled and separated from actual paper outcomes.
