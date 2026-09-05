# QuantNifty Next — Project State

## Source of truth
- Branch: `main`
- The GitHub `main` branch is authoritative; this document does not pin a stale commit SHA.
- Trading remains disabled/read-only.

## Current architecture
- Live provider ingestion and analytics: `main.py`
- Institutional signal, RiskEngine, FinalDecision, ExecutionPlan: `institutional_engine.py`
- Deterministic candle replay: `replay.py`
- Backtest and validation metrics: `backtest.py`
- Strike policy: `strike_selector.py`
- Canonical historical snapshot contract: `historical.py`
- Recorded Parquet + JSON ingestion: `recording_loader.py`
- Recorded historical API: `recording_api.py`
- Backtest UI: `web/backtest.html`

## Backtest status
Implemented and unit-tested:
- decision-at-t / fill-at-t+1 replay boundary
- authoritative FinalDecision → RiskEngine → ExecutionPlan path
- bid/ask-aware entry/exit fallback
- configurable slippage and fixed transaction costs
- P&L, win/loss counts and distribution
- profit factor and expectancy
- maximum drawdown and drawdown percentage
- Sharpe-like daily metric
- deterministic in-sample / validation / out-of-sample split
- regime classification
- expiry-day / expiry-open / final-15-minute classification when timestamp and expiry data are present
- risk-gate effectiveness and signal-confidence summary
- canonical snapshot validation and provenance isolation
- recorded Parquet option-chain + Greeks ingestion
- UTF-8/CP1252-transcoded recorder export recovery
- read-only recorded-history API endpoints and Backtest UI integration

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
- expiry-day snapshots on 04-Aug-2026 are present

The recorder export is structurally sufficient to attempt canonical reconstruction. It is not committed to `main` and is not mounted in the Render service. Therefore no empirical P&L or strategy result is claimed from inspection alone.

## Empirical-result rule
No historical P&L, win rate, profit factor, expectancy, drawdown, Sharpe-like result, Gamma Blast result, or CAS result is considered empirical until recorded option-chain data is successfully decoded, canonicalized, and replayed through the same live intelligence → FinalDecision → RiskEngine → ExecutionPlan path.

Index-only historical candles are not sufficient to claim option-strategy backtest results.

## Current remaining work
1. Upload the reviewed recorder export through the Backtest UI validation endpoint.
2. Run recorded-history validation against the real bundles and verify Parquet decoding and canonical reconstruction.
3. Produce empirical directional and Gamma Blast results only from successfully decoded recorded snapshots.
4. Verify ATM/ITM directional policy, qualified-only OTM for Gamma Blast, and CAS expiry-day behavior against supported recorded timestamps.
5. Capture and retain empirical validation evidence in CI or another authoritative project record.

## Validation evidence
- Latest CI validation covers the historical replay mode, report importer, backtest session boundaries and existing backtest safeguards.
- Production evidence workflow passed live-provider, historical candle replay and browser E2E checks for the application deployment available at the time of validation.
- Render service `quantnifty-api` is configured for automatic deployment from `main` in Singapore.
- No real trading or order execution is enabled.
