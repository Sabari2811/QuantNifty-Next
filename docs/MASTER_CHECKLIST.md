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
- [x] IV skew / ATM IV
- [x] Gamma flip / gamma walls
- [x] Max pain
- [x] Expected move
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
- [x] Gamma walls
- [x] Market structure
- [x] Dealer flow / rationale
- [x] Data-integrity state
- [x] No fabricated fallback values

## Validation
- [x] Python compile validation in CI
- [x] Replay unit tests in CI
- [ ] Authenticated live-market response observed in cloud runtime
- [ ] Full browser E2E with live provider response
- [ ] Production historical replay run with real provider candles

The remaining unchecked items require an authenticated provider response to be observable from the deployed runtime; they are deliberately not marked green from static/source inspection alone.
