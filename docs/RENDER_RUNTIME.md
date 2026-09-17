# Render runtime schedule

QuantNifty-Next is intended to run on weekdays only during the useful operating window:

- 09:00 IST: application runtime starts/resumes.
- 09:15-15:40 IST: NSE NIFTY equity-derivatives live-provider polling and live paper lifecycle.
- 15:15-15:35 IST: NSE Closing Auction Session (CAS) is observed as a cash-market influence; NIFTY options are not CAS instruments.
- 15:30 IST: CAS-aware new entries stop; existing CAS-aware NIFTY paper positions may be managed until the derivatives close guard.
- 15:39 IST: all NIFTY paper positions are forced closed, one minute before the 15:40 derivatives close.
- 15:40-16:00 IST: post-market research, strategy comparison, P&L and result generation.
- 16:00 IST: application compute is suspended.
- Saturday/Sunday: application compute remains suspended.

The application-level session guard is deliberately narrower for market data: provider polling remains disabled before 09:15 and at/after 15:40. The 09:00-16:00 runtime window exists for pre-market initialization and the post-market lab.

## NSE timing authority

NSE currently documents CAS as a separate 20-minute session from 15:15 to 15:35 for eligible cash-segment stocks, with reference-price calculation/transition at 15:15-15:20, order entry at 15:20-15:30 and matching/trade confirmation at 15:30-15:35. NSE separately documents equity-derivatives regular trading from 09:15 to 15:40. QuantNifty therefore treats CAS as an influence/evidence window, not as a trading session for NIFTY options.

## Important billing boundary

A Python sleep or application-level closed state does **not** stop a paid Render web service from accruing compute charges. The Render service itself must be suspended to stop paid compute. Render exposes `POST /v1/services/{serviceId}/suspend` and `POST /v1/services/{serviceId}/resume` for this purpose.

## Required production services

For QuantNifty-Next only:

1. `quantnifty-api` — paid web service, active only during the runtime window.
2. `quantnifty-production` — paid PostgreSQL for durable production learning/paper/research data. Keep this database available; do not suspend it as part of the daily compute schedule.
3. Do not enable the separate `QuantNifty` worker/services unless explicitly required by a later architecture change.

## Daily scheduler

The repository now contains GitHub Actions scheduler workflows for the actual Render service lifecycle. They require one repository secret:

- `RENDER_API_KEY` — a Render API key with permission to suspend/resume the service.

The service ID is non-secret and is configured as `srv-dad5e767bikc739oighg`.

The scheduler calls:

- 09:00 IST weekdays: `POST https://api.render.com/v1/services/<QUANTNIFTY_SERVICE_ID>/resume`
- 16:00 IST weekdays: `POST https://api.render.com/v1/services/<QUANTNIFTY_SERVICE_ID>/suspend`

The API key must be stored only as a GitHub Actions secret; never commit it to GitHub or put it in source code.

Render cron schedules are UTC. IST is UTC+05:30:

- Resume: `30 3 * * 1-5` (09:00 IST)
- Suspend: `30 10 * * 1-5` (16:00 IST)

GitHub Actions scheduled workflows can start a few minutes late. The application remains fail-closed outside its defined market/runtime windows, so scheduler jitter cannot enable trading outside policy.

## Cost expectation

Render bills paid compute by active runtime, prorated to the second. The exact monthly amount depends on the service plan and actual runtime. Suspending at 16:00 and resuming at 09:00 on weekdays avoids overnight/weekend API compute while preserving the persistent PostgreSQL database.
