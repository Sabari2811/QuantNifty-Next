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
Live Provider
    -> Canonical Snapshot / Analytics
    -> Institutional Signal
    -> Adaptive Brain
    -> Risk
    -> FinalDecision
    -> ExecutionPlan (READ-ONLY)
    -> Live Paper Trade Manager
    -> Learning Store
             |
             v
       After-Market Lab
             |
       +-----+------------------+
       |                        |
       v                        v
 Full Research Universe    Scenario Engine
       |                        |
       +-----------+------------+
                   v
             Policy Validator
                   |
                   v
       Future-Safe Policy Store
                   |
             next service start
                   |
                   v
             Adaptive Brain
```

Historical/research inputs such as `data_Review.txt` may be used for replay/bootstrap research but are never committed to GitHub and never injected into live decisions as future information.

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
```

The live refresh is periodic and records each valid live snapshot and Adaptive FinalDecision. When Risk approves a candidate, the paper manager opens one hypothetical trade without sending any broker order. Subsequent snapshots update MFE/MAE; invalidation or 15:30 session close closes the paper trade and records an option-premium P&L proxy when the selected option leg is available.

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

The strategy registry remains explicit and testable:

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

The live API intentionally exposes only `directional`, `gamma_blast`, and `adaptive`. After-market research additionally evaluates `early_accumulation`, `transition`, `range`, and `breakout_watch` by routing them through the canonical Adaptive Brain/FinalDecision/Risk path using an explicit research-only override. This does not weaken live safeguards.

## 6. Early Accumulation Architecture

The objective is to identify potential accumulation before a confirmed breakout while preserving confirmation and risk controls.

Evidence can include near-ATM option OI expansion, premium stability/rise, active volume, quiet/compressed spot, controlled IV, expected-move-relative premium, market structure and gamma/DEX context.

States:

```text
NO_CLEAR_ACCUMULATION
WATCH_ACCUMULATION
EARLY_ACCUMULATION
```

The system must not claim exact bottom/top prediction.

## 7. Adaptive Exit Architecture

Exit decisions can use capital-protection threshold, favorable move, exhaustion, gamma reversal, volume/pressure deterioration, profit-lock trigger, trailing stop and continued trend/accumulation support.

Current implementation is primarily spot-based with gamma/volume/pressure context. Option premium, IV, Greeks and liquidity confirmation remain a research enhancement after sufficient observations exist.

## 8. Market Recorder and Outcome Lifecycle

The recorder stores immutable evidence for the decision timestamp. The learning store separates:

- `snapshots`: live market evidence
- `decisions`: live FinalDecision evidence
- `outcomes`: actual read-only paper lifecycle outcomes
- `research`: after-market/counterfactual research and validated policy artifacts

Open paper trades are persisted as `lifecycle=OPEN` so service restart can recover the active hypothetical trade. Closed outcomes include MFE/MAE, exit reason, option-premium P&L when available, and explicit read-only/no-execution metadata.

## 9. Durable Learning Store

PostgreSQL is supported using `QUANTNIFTY_DATABASE_URL` or `DATABASE_URL`. The database table is created idempotently and events use an idempotent event ID. Filesystem JSONL remains a fallback when PostgreSQL is unavailable.

Production readiness requires the Render API service to have its database connection environment variable securely configured and persistence verified across restart/deploy. No credential or connection string is stored in Git.

## 10. After-Market Research

At/after 15:35 IST, the scheduler loads the same day's stored snapshots and runs:

```text
directional
gamma_blast
adaptive
early_accumulation
transition
range
breakout_watch
```

Every result is marked research-only/counterfactual. The same day's future observations are allowed in this post-close analysis because it is explicitly after-market research. Results are persisted as research events.

The Scenario Engine extracts deterministic labels including accumulation breakout, gamma blast, gamma transition, positive-gamma range, compression/breakout watch, liquidity risk, failed direction and exhaustion/profit-lock.

## 11. Adaptive Policy Runtime

After-market results are passed through the versioned `adaptive-policy-v1` validator. Promotion requires the configured minimum sample and minimum improvement over the Adaptive anchor. Every persisted policy must carry `future_safe=true` and `counterfactual_source=true`.

At service startup, `policy_runtime.load_future_policy()` loads only a policy created before the current IST date and with valid schema/status/metadata. Current-day policies are rejected. The loaded policy is passed into the live Adaptive Brain for the new session only; it is never used to rewrite past decisions.

Fallback remains the Adaptive anchor whenever promotion requirements are not met.

## 12. Historical Readiness

The broader one-year learning gate remains 252 trading days + 365 calendar days + valid recorded historical provenance. Existing `data_Review.txt` is valid research/bootstrap evidence but does not satisfy the one-year gate by itself.

## 13. Safety / Governance

- FinalDecision is authoritative.
- Risk owns permission to trade.
- ExecutionPlan never submits an order.
- Live paper outcomes are not real trades.
- Counterfactual research is never mixed into empirical live outcomes.
- Future outcomes never enter a live decision.
- Live API strategy safeguards remain stricter than research-only routing.
- All live learning remains READ-ONLY.

## 14. Operational Verification Before Learning Start

Before the first production learning session after this implementation, verify:

1. CI passes on the latest `main` commit.
2. Render deploy serves that same commit.
3. PostgreSQL environment is configured without exposing secrets.
4. `/api/v1/status` reports durable learning configuration.
5. Live snapshot/decision/outcome events persist.
6. 15:30 closes any active paper trade.
7. After-market scheduler runs once per weekday and persists research/scenarios/policy.
8. Next service start loads only the prior-day future-safe policy.
9. `orders_placed=0` and `trading_enabled=false` remain true.

No production-learning claim is considered verified until these checks pass.
