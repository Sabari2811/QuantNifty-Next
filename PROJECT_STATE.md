# QuantNifty Next — Project State

## Source of truth
- Branch: `main`
- The GitHub `main` branch is authoritative; this document is a governance/state summary and intentionally does not pin a stale commit SHA.
- Trading remains disabled/read-only.

## Current architecture
- Live provider ingestion and analytics: `main.py`
- Institutional signal, RiskEngine, FinalDecision, ExecutionPlan: `institutional_engine.py`
- Deterministic candle replay: `replay.py`
- Backtest and validation metrics: `backtest.py`
- Strike policy: `strike_selector.py`
- Canonical historical snapshot contract: `historical.py`
- Recorded Parquet + JSON ingestion: `recording_loader.py`
- Backtest UI: `web/backtest.html`

## Backtest status
Implemented and unit-tested:
- decision-at-t / fill-at-t+1 replay boundary
- FinalDecision path through RiskEngine and ExecutionPlan
- bid/ask-aware entry/exit fallback
- slippage and fixed transaction costs
- P&L, win/loss counts and distribution
- profit factor and expectancy
- maximum drawdown and drawdown percentage
- Sharpe-like daily metric
- in-sample / validation / out-of-sample split
- regime classification
- expiry-day / expiry-open / final-15-minute classification when timestamp and expiry data are present
- risk-gate effectiveness and signal-confidence summary
- canonical snapshot validation and provenance isolation
- recorded Parquet option-chain + Greeks ingestion

## Historical data evidence
`data_Review.txt` was reviewed outside the repository because it is not present on `main`.
The reviewed recorder export contains:
- 75 snapshot directories
- 67 option-chain parquet files
- 67 greeks parquet files
- 64 analytics JSON files
- 64 decision JSON files
- runtime timestamps spanning 27-Jul-2026 through 07-Aug-2026
- 23 snapshots during NSE market hours in the reviewed export
- 45 snapshots referencing 04-Aug-2026 expiry and 22 referencing 11-Aug-2026 expiry
- expiry-day snapshots on 04-Aug-2026 are present, including pre-expiry and post-rollover observations

The recorder data is structurally sufficient to attempt canonical reconstruction. It is not committed to the repository, so production empirical results are not claimed until the actual bundle is supplied to the ingestion path and successfully replayed.

## Empirical-result rule
No historical P&L, win rate, profit factor, expectancy, drawdown, Sharpe-like result, Gamma Blast result, or CAS result is considered empirical until the recorded option-chain data is successfully decoded, canonicalized, and replayed through the same live intelligence -> FinalDecision -> RiskEngine -> ExecutionPlan path.

Index-only historical candles are not sufficient to claim option-strategy backtest results.

## Remaining highest-priority work
1. Wire the recorded-snapshot loader into the API/UI without introducing a second data source of truth.
2. Reconstruct canonical snapshots from the actual recorder export and verify all timestamps, expiry, option identity and Greeks.
3. Replay the actual recorded snapshots through the authoritative decision/risk path.
4. Validate directional and Gamma Blast strike policy, including qualified-only OTM.
5. Validate expiry/CAS behavior only where recorded timestamps and expiry support it.
6. Produce empirical metrics and expose their provenance in the backtest UI/API.
7. Add production E2E coverage for the historical validation surface.
