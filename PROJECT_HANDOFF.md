# QuantNifty-Next — Persistent Project Handoff

**Updated:** 2026-09-13  
**Branch:** `main`  
**Repository:** https://github.com/Sabari2811/QuantNifty-Next  
**Production:** https://quantnifty-api.onrender.com  
**Backtest:** https://quantnifty-api.onrender.com/backtest  
**Execution:** READ-ONLY; no real orders; `trading=DISABLED`.

## Product and safety contract
QuantNifty-Next is a Live Adaptive Brain + After-Market Research Lab. Live decisions use only data available at decision time. Adaptive runtime is restricted to the live IST session; no overnight paper positions are allowed. Same-day Adaptive memory consumes only current-IST-day CLOSED outcomes in explicit LIVE mode. Historical learning/bootstrap/performance gates are removed. `data_Review.txt`, old recordings and external historical archives are replay/reference evidence only and never seed live Adaptive memory or policy. Real trading is permanently disabled.

Do not modify `QuantNifty`, `data/instruments/fno.csv`, or commit secrets.

## Live paper risk
At entry the paper manager freezes entry spot, entry premium, selected instrument, trigger, stop/target points, R:R and exit policy. Option premium SL/target are delta-driven from the NIFTY-point risk budget using live option delta. New entries require valid delta. Existing legacy OPEN trades without delta evidence are not fabricated or rewritten. No real orders are submitted and no overnight paper positions are carried.

## Live entry scenarios
Entry-capable pathways: `EARLY_ACCUMULATION`, `DIRECTIONAL`, `NEGATIVE_GAMMA_EXPANSION`, `GAMMA_TRANSITION`, `CAS_REENTRY`. Liquidity-risk, positive-gamma range, compression and standby states are explicit NO_ENTRY states.

## GPT-6 Astra decision intelligence
GPT-6 Astra is merged into `main` as a LIVE-only advisory decision-intelligence layer using `apps/api/src/quantnifty/astra_intelligence.py`, OpenAI Responses API, structured JSON and `gpt-6-astra`. It receives only decision-time market evidence and returns WAIT/ENTER/HOLD/EXIT, direction, confidence, thesis, invalidation and risk flags. Deterministic institutional/risk controls remain authoritative; Astra cannot create a trade when the deterministic gate rejects it and is not invoked for replay/backtest/research. `store=false` is used. Production has non-secret Astra configuration enabled, but `OPENAI_API_KEY` is intentionally absent; missing key or Astra failure fails open to the deterministic brain. Regression coverage exists for missing secret, structured output, deterministic gating, replay isolation and advisory validation.

## Trade Audit
Read-only paper trade audit is available at `/trade-audit` with API `/api/v1/paper/trade-audit`. It joins durable outcomes to exact entry snapshots/decision timestamps without hindsight and marks incomplete legacy evidence instead of fabricating it.

## V3 thesis-hold stored-day research
The authoritative research lifecycle is:

`ENTRY CONFIRMED -> BUY ACTUAL STORED OPTION -> OPEN POSITION -> HOLD/MONITOR -> EXIT -> ONLY THEN ALLOW NEXT ENTRY`

The first approved signal becomes the first research trade; same-direction signals while open do not re-enter. Entry/exit use actual stored option premiums. Stop/target are NIFTY spot-point distances using a 20-snapshot close-to-close spot ATR proxy, with stop `max(50,min(150,ATR_proxy*4*IV_multiplier))`, IV multiplier 0.90/1.00/1.20 by ATM IV regime, and target 2R. Other exits include Adaptive exhaustion/trail, thesis/risk invalidation, expiry and same-day session close. Research is read-only and places zero orders.

`/api/v1/research/results?day=YYYY-MM-DD` reads durable `STORED_DAY` research and regenerates stale legacy fixed-TIME/counterfactual reports through the current V3 engine. Research rows now expose `position_lifecycle`, `risk_model`, and `tuning_profile` so production evidence can verify the model rather than merely trusting a P&L number.

## Historical options adapter
`apps/api/src/quantnifty/external_options_loader.py` accepts generic 1-minute NIFTY option CSVs and maps them into the existing canonical snapshot contract. Required fields are timestamp, strike, CE/PE, close/LTP, volume, OI, positive NIFTY spot and expiry. Optional OHLC/bid/ask are retained; missing Greeks are never invented. The path is:

`External CSV -> canonical snapshots -> research_strategy_runner -> position_hold_backtest -> V3 research P&L`

This is research/replay only and cannot enter live Adaptive memory. Dataset licensing, timestamp completeness, contract identity, OI semantics and quote quality must be validated before empirical results are accepted.

## Production validation evidence
On 2026-09-11 Render evidence established LIVE_PROVIDER option-chain snapshots, advancing durable snapshots, distinct decision-event gating, a live paper OPEN -> IDLE lifecycle, PostgreSQL learning durability and `trading=DISABLED`. This proved the live read-only loop is operating, not that it is profitable.

The production evidence workflow now also checks the stored-day V3 research endpoint for 2026-09-11 and asserts: `source=STORED_DAY`, `research_only=true`, `orders_placed=0`, `mode=READ_ONLY_AFTER_MARKET`, `position_lifecycle=THESIS_HOLD_UNTIL_INVALIDATION`, `risk_model=SPOT_ATR_PROXY_X4_WITH_ATM_IV_ADJUSTMENT`, and `tuning_profile=INTRADAY_OPTION_RESEARCH_V3_THESIS_HOLD` for tested strategies. It separately requires `/api/v1/market` to remain `LIVE_PROVIDER` and `/api/v1/replay` to remain `READ_ONLY_REPLAY`, preserving live/replay isolation.

A real third-party historical option archive has not yet been accepted as empirical backtest evidence. Public candidates identified for qualification include the Zenodo NIFTY one-minute 2017-2020 option archive and newer Hugging Face NIFTY/BANKNIFTY/SENSEX 1-minute option archives; these remain candidates until decoded and quality/licensing checks pass.

## Validation state
- Thesis-hold implementation: `823351703dd4e9360ce5171271e41f4dd20041b1`, `313f25ba0aa78032fcf6dcb036290d380d818d9e`, same-day safeguard `c234df4f92def0e212a9b94058c265e47dab28ee`.
- Point-based volatility risk: `fb6a9e72ccfd4918817967c706fa787865bf563c`.
- Historical options adapter and regression tests are on `main`.
- Astra feature PR was validated by green CI and merged into `main` as `a0a58e18a7c614911db2f0bd07732b77e6daee0f`.
- Latest production deploy before this merge was `dep-dai83u942hec73bkrq30` on commit `cffde48...`; the merged commit has triggered fresh production-evidence/liveness workflows and must not be called production-live until those workflows and the new Render deployment finish.
- Full empirical historical V3 P&L remains pending a qualified external option dataset.

## Non-negotiable rules
Never commit secrets or `data_Review.txt`; never use future outcomes in live decisions; never use historical recordings for live Adaptive learning; never represent research as actual trades; never submit real orders; no overnight paper positions; do not touch `data/instruments/fno.csv` or unrelated audit/backup artifacts. Use normal repository changes and existing validation workflows only.
