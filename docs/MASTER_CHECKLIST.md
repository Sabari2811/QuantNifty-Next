# QuantNifty Next — Master Completion Checklist

## Data
- [x] INDstocks access token is runtime-only
- [x] NIFTY underlying security ID contract
- [x] Expiry discovery
- [x] Option-chain normalization
- [x] Provider failure / retry handling
- [x] Fail-closed live-data integrity

## Analytics
- [x] PCR / OI
- [x] OI change
- [x] GEX / DEX
- [x] Vanna proxy
- [x] IV skew / ATM IV
- [x] Gamma flip / gamma walls
- [x] Max pain
- [x] Expected move — IV percentage and days-to-expiry handled correctly
- [x] Expected move lower / spot / upper range exposed in UI
- [x] Support / resistance
- [x] Dealer-flow classification
- [x] Liquidity score
- [x] Direction score / rationale

## Replay / history
- [x] Historical OHLCV adapter
- [x] Deterministic candle normalization
- [x] Deterministic replay stream
- [x] Replay summary
- [x] Read-only replay API
- [x] Historical interval validation
- [x] Five-instrument request limit enforcement
- [x] Historical/replay capability exposed through API; UI remains signal-dashboard focused

## Trading safety
- [x] Explicit READ_ONLY mode
- [x] Order placement disabled
- [x] Order modification disabled
- [x] Order cancellation disabled
- [x] No UI execution controls

## UI
- [x] Live provider state
- [x] Live freshness timestamp
- [x] Analytics cards
- [x] Vanna proxy
- [x] Expected move value and lower/upper range
- [x] Focused Key Market Levels display
- [x] Current NIFTY market level
- [x] Gamma flip level
- [x] Call wall level
- [x] Put wall level
- [x] Support level
- [x] Resistance level
- [x] Gamma walls / market structure / dealer flow context
- [x] Directional bullish / bearish score and confidence
- [x] Positioning & volatility detail panel
- [x] Reference levels & provider feed panel
- [x] Data-integrity state
- [x] No fabricated fallback values
- [x] Full normalized option-chain exposed in UI
- [x] Live option-chain All / Calls / Puts filters
- [x] ATM strike identification and highlighting
- [x] Complete option-chain columns: Side, Strike, Security ID, LTP, Previous Close, OI, OI Δ, Volume, Bid, Bid Qty, Ask, Ask Qty, IV %, Delta, Gamma, Theta, Vega
- [x] Option-chain rows remain sourced from the same normalized provider payload used by analytics

## Deployment / reliability
- [x] Render Python service configuration aligned with repository
- [x] Render health endpoint contract
- [x] WebSocket client-disconnect handling
- [x] CI compile validation
- [x] CI replay/analytics regression tests
- [x] Production deployment of previously completed UI/API changes observed live

## Final evidence gates
- [ ] Authenticated live-market response observed after the latest UI/API deployment
- [ ] Full browser E2E with live provider response after the latest UI/API deployment
- [ ] Production historical replay run with real provider candles

These final three gates remain evidence-gated. They cannot be marked complete from source inspection alone. QuantNifty Next remains production-read-only until authenticated live-provider evidence is observed after the latest deployment.
