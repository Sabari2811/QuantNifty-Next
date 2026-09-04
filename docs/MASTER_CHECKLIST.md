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
- [x] Expected move — IV percentage and days-to-expiry handled correctly
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
- [x] Gamma walls
- [x] Market structure
- [x] Dealer flow / rationale
- [x] Data-integrity state
- [x] No fabricated fallback values

## Deployment / reliability
- [x] Render Python service configuration aligned with repository
- [x] Render health endpoint contract
- [x] WebSocket client-disconnect handling
- [x] CI compile validation
- [x] CI replay/analytics regression tests
- [x] Successful CI run observed for the implementation fixes
- [x] Production Render deployment previously observed live

## Final evidence gates
- [ ] Authenticated live-market response observed in cloud runtime
- [ ] Full browser E2E with live provider response
- [ ] Production historical replay run with real provider candles

These final three gates remain evidence-gated. They cannot be marked complete from source inspection alone. QuantNifty Next remains production-read-only until authenticated live-provider evidence is observed.
