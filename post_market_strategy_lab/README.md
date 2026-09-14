# QuantNifty Post-Market Strategy Lab

Standalone research section. It does **not** modify the live decision engine, paper-trading lifecycle, adaptive memory, or execution settings.

## Purpose

After each live NSE session, the lab can consume the raw snapshots captured during that session and run a common strategy tournament. Every strategy is evaluated as a counterfactual: **what would this strategy have done using only the information present in each stored snapshot?**

The lab is research-only. It must never place orders or feed historical/post-market results into the live decision path.

## Strategy families

### Directional / option-buying
- VWAP Momentum Breakout
- VWAP + EMA 9/21
- EMA trend
- RSI + Bollinger + VWAP mean reversion
- Opening Range Breakout
- OI Flow
- OI + VWAP
- GEX + VWAP
- Gamma Flip + Price Action
- IV/RV + Trend
- Market Structure + OI
- VWAP + OI + GEX

### Option selection variants
For every compatible directional signal, compare:
- ATM
- 1-step ITM
- 1-step OTM
- delta 0.50
- delta 0.60
- delta 0.70

### Multi-leg strategies
These require a multi-leg simulator and must not be approximated as single-leg trades:
- Bull Put Spread
- Bear Call Spread
- Bull Call Spread
- Bear Put Spread
- ATM Straddle
- OTM Strangle
- Iron Condor
- Iron Fly

## Common research rules

1. Use only raw stored live-session snapshots for the selected trading day(s).
2. Never use future snapshots when generating an entry decision.
3. Use actual stored option contracts/prices where available.
4. Model bid/ask first; fall back to last price only when the dataset explicitly lacks quotes.
5. Apply brokerage, exchange charges, STT, GST, SEBI/stamp charges and configurable slippage.
6. Enforce NSE session boundaries and expiry handling.
7. Record every entry, exit, selected contract, reason, gross P&L, costs and net P&L.
8. Report P&L by strategy, regime, direction and time bucket.
9. Do not rank on win rate alone.
10. Require sufficient observations before declaring a strategy robust.
11. Separate in-sample, validation and out-of-sample results for multi-day datasets.
12. Preserve raw results so strategy changes are auditable.

## Required output

Each run should produce:

- strategy leaderboard
- gross P&L
- net P&L
- return
- win rate
- profit factor
- expectancy/trade
- Sharpe-like metric
- maximum drawdown and drawdown %
- average win/loss
- number of trades
- average holding time
- cost drag
- best/worst day
- regime breakdown
- OOS result where enough history exists
- cost/slippage sensitivity
- trade ledger

## Important interpretation

A one-day profitable result is **not** evidence of a durable edge. The lab is intended to accumulate independent daily experiments and later evaluate multi-day robustness. Post-market results remain counterfactual research results and are never represented as actual trades.
