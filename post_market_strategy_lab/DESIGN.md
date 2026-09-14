# Research design / non-negotiable correctness gates

The lab intentionally freezes the selected option contract at entry. It must never re-select the nearest strike on every future bar, because that creates a rolling-strike P&L artifact.

Entry uses the first snapshot after the signal. Exit uses the same security_id/trading_symbol whenever it is present. If the exact contract cannot be found, the trade is marked unresolved rather than silently switching contracts.

The lab is split into:

1. **Signal layer** — strategy-specific signal from the current raw snapshot and prior snapshot only.
2. **Contract selector** — ATM/ITM/OTM/delta selection at entry only.
3. **Lifecycle** — fixed contract until STOP/TARGET/TIME/expiry or data failure.
4. **Execution** — buy at ask where available, sell at bid where available, otherwise documented last-price fallback.
5. **Costs** — configurable slippage and fixed per-side cost.
6. **Metrics** — net P&L, PF, expectancy, drawdown, return, Sharpe-like daily statistic and cost drag.
7. **Research isolation** — no live decisions, paper trades, adaptive memory or broker execution are read or mutated by the lab.

## Multi-leg boundary

Credit spreads, debit spreads, straddles, strangles, Iron Condors and Iron Flies are not treated as single-leg strategies. A dedicated multi-leg simulator must freeze every leg at entry and mark each leg independently on exit. Until that engine exists, these strategies are reported as pending rather than generating fake P&L.

## Robustness boundary

One live day is a scenario test, not proof of a strategy. Multi-day stored sessions should be aggregated chronologically and then evaluated with walk-forward/OOS splits. Parameter selection must happen on training data only.
