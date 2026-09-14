# QuantNifty Post-Market Strategy Lab

A standalone research section. It does **not** modify the live decision engine, paper lifecycle, adaptive memory, execution settings, or order path.

## What is implemented

### Single-leg tournament
12 signal strategies × 6 contract variants = **72 counterfactual tests**:

- VWAP Momentum Breakout
- VWAP + EMA 9/21
- EMA Trend
- RSI + Bollinger + VWAP mean reversion
- Opening Range Breakout
- OI Flow
- OI + VWAP
- GEX + VWAP
- Gamma Flip + Price Action
- IV/RV + Trend
- Market Structure + OI
- VWAP + OI + GEX

Variants: ATM, 1-step ITM, 1-step OTM, delta 0.50, 0.60 and 0.70.

### Multi-leg simulator
Implemented separately rather than approximating multi-leg positions as single options:

- Bull Put Spread
- Bear Call Spread
- Bull Call Spread
- Bear Put Spread
- ATM Straddle
- OTM Strangle
- Iron Condor
- Iron Fly

Every leg is frozen at entry using the stored contract identity. Future bars never re-select a nearest strike.

## Execution/cost correctness

- Raw snapshots from `quantnifty.learning_store.load_snapshots` are the only market-data input.
- Signal decisions use only the current and previous snapshot.
- Entry executes on the next stored snapshot, avoiding same-bar look-ahead.
- Option contracts are fixed at entry by security ID / symbol / strike / expiry.
- Bid/ask is preferred; last price is only a fallback when a quote is absent.
- NSE session is restricted to 09:15–15:30 IST.
- Configurable slippage is applied to every leg.
- Default 2026 NSE option cost model includes ₹20/order brokerage, 0.03553% NSE option transaction charge, SEBI turnover fee, 0.003% buyer stamp duty, 0.15% sell-side STT, and 18% GST on brokerage + transaction + SEBI charges. Rates are configuration values so they can be changed without touching the live engine.
- No real orders are possible from this package.

## Robustness

Each research run can include:

- P&L / return / win rate / profit factor / expectancy
- average win/loss
- max drawdown and drawdown percentage
- daily best/worst result
- Sharpe-like daily metric
- 0/5/10/20 bps slippage stress
- 5,000-path Monte Carlo drawdown / ending-equity distribution
- risk-of-ruin estimate
- minimum-observation robustness gate
- multi-day in-sample vs out-of-sample split

A profitable one-day result is **not** considered a durable edge.

## Commands

Single session:

```powershell
python -m post_market_strategy_lab.run_day 2026-09-15 --output reports\2026-09-15.json
```

Multiple sessions, oldest first:

```powershell
python -m post_market_strategy_lab.run_period 2026-09-01,2026-09-02,2026-09-03 --output reports\period.json
```

## Research isolation

The lab remains counterfactual and research-only. Its results are not automatically fed into live signals, paper positions, adaptive memory, or execution. Historical recordings are evidence for replay/research only.

## Important limitation

This branch can calculate only what the stored raw snapshots contain. If a snapshot lacks a quote, delta, expiry, OI field, or other required value, the lab does not invent it; the affected test may be skipped or use an explicitly documented fallback. Expiry settlement/exercise is not simulated unless the required expiry-state snapshots are present.
