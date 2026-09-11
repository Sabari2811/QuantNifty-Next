# Historical NIFTY Options Integration

## Scope
This adapter feeds external historical NIFTY option CSV data into the existing canonical snapshot contract used by V3 thesis-hold research. It does **not** create a second backtest engine.

## Required source fields
The loader requires timestamp, strike, option type (CE/PE or equivalent), close/LTP, volume, and open interest. It also requires a positive NIFTY spot and option expiry for every snapshot.

Optional bid/ask and OHLC fields are retained when present. Greeks are never fabricated; they remain absent unless the source supplies them through a future adapter extension.

## Canonical path
`external_options_loader.load_option_csv()` -> `historical.canonicalize_snapshots()` -> `research_strategy_runner.run_research_strategy()` -> `position_hold_backtest.run_position_hold_backtest()`.

The V3 engine therefore remains authoritative for decision, risk, option-premium P&L, thesis hold, expiry/session exits, and read-only execution semantics.

## Data qualification
1. Validate source licensing/usage rights before importing a third-party archive.
2. Verify the source is genuinely intraday and not end-of-day snapshots.
3. Verify timestamps are complete enough for the intended strategy cadence.
4. Verify strike, expiry and CE/PE identity are stable for each contract.
5. Verify OI and volume are contract-level values and document whether OI is end-of-minute or cumulative.
6. Verify option premium fields are executable enough for the intended model. V3 uses ask/last for entry and bid/last for exit when available.
7. Only after these checks should the dataset be used to produce empirical backtest results.

## Provenance and learning isolation
External historical imports are `RECORDED_HISTORICAL` research/replay data. They cannot seed live Adaptive memory. Live learning remains restricted to `LIVE_PROVIDER`, with same-day post-market learning from `STORED_DAY`.
