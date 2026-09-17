# Render runtime schedule

QuantNifty-Next is intended to run on weekdays only during the useful operating window:

- 09:00 IST: application runtime starts/resumes.
- 09:15-15:30 IST: NSE NIFTY live-provider polling and live paper lifecycle.
- 15:15-15:27 IST: cash-session strategy may generate a new NIFTY-options paper entry when its deterministic confirmation passes.
- Before 15:15 IST: normal paper positions are closed before the cash-session influence window.
- 15:29 IST: any remaining cash-session NIFTY paper position is force-closed.
- 15:30-16:00 IST: independent post-market research, strategy comparison, P&L and result generation from the day's raw snapshots.
- 16:00 IST: application compute is suspended.
- Saturday/Sunday: application compute remains suspended.

The application-level session guard is deliberately narrower for market data: provider polling remains disabled before 09:15 and at/after 15:30. The 09:00-16:00 runtime window exists for pre-market initialization and the independent post-market lab.

## NSE timing authority

NSE Closing Auction Session (CAS) is a separate cash-segment session for eligible cash-segment stocks. QuantNifty observes the cash session only as an underlying-market influence/evidence window; NIFTY options are not CAS instruments. QuantNifty's own paper-entry policy is intentionally narrower: `CAS_REENTRY` entries are permitted only from 15:15 through 15:27 IST, and the resulting paper position is force-closed by 15:29 IST.

NIFTY equity-derivatives live-provider access is independently closed at 15:30 IST by project policy. Post-market research begins at that boundary and does not consume live paper decisions, live outcomes or future auction results.

## Important billing boundary

A Python sleep or application-level closed state does **not** stop a paid Render web service from accruing compute charges. The Render service itself must be suspended to stop paid compute. Render exposes `POST /v1/services/{serviceId}/suspend` and `POST /v1/services/{serviceId}/resume` for this purpose.

## Required production services

For QuantNifty-Next only:

1. `quantnifty-api` — paid web-service compute, active only during the 09:00-16:00 weekday runtime window.
2. `quantnifty-production` — paid PostgreSQL for durable production learning/paper/research data. Keep this database available; do not suspend it as part of the daily compute schedule.
3. Do not enable the separate `QuantNifty` worker/services unless explicitly required by a later architecture change.

## Daily scheduler

The repository contains GitHub Actions scheduler workflows for the actual Render service lifecycle. They require one repository secret:

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
