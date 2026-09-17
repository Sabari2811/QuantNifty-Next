# Render runtime schedule

QuantNifty-Next is intended to run on weekdays only during the useful operating window:

- 09:00 IST: application runtime starts/resumes.
- 09:15-15:30 IST: NSE live-provider polling and live paper lifecycle.
- 15:30-16:00 IST: post-market research, strategy comparison, P&L and result generation.
- 16:00 IST: application compute should be suspended.
- Saturday/Sunday: application compute should remain suspended.

The application-level session guard is deliberately narrower for market data: provider polling remains disabled before 09:15 and at/after 15:30. The 09:00-16:00 runtime window exists so pre-market initialization and the 15:35 post-market lab can run safely.

## Important billing boundary

A Python sleep or application-level closed state does **not** stop a paid Render web service from accruing compute charges. The Render service itself must be suspended to stop paid compute. Render exposes `POST /v1/services/{serviceId}/suspend` and `POST /v1/services/{serviceId}/resume` for this purpose.

## Required production services

For QuantNifty-Next only:

1. `quantnifty-api` — paid `0.5c-512mb` (Starter equivalent), active only during the runtime window.
2. `quantnifty-production` — paid PostgreSQL for durable production learning/paper/research data. Keep this database available; do not suspend it as part of the daily compute schedule.
3. Do not enable the separate `QuantNifty` worker/services unless explicitly required by a later architecture change.

## Daily scheduler

The scheduler must call the Render API with a Render API key:

- 09:00 IST weekdays: `POST https://api.render.com/v1/services/<QUANTNIFTY_SERVICE_ID>/resume`
- 16:00 IST weekdays: `POST https://api.render.com/v1/services/<QUANTNIFTY_SERVICE_ID>/suspend`

The API key must be stored as a secret in the scheduler; never commit it to GitHub or put it in source code.

Render cron schedules are UTC. IST is UTC+05:30, so the weekday schedules are:

- Resume: `30 3 * * 1-5` (09:00 IST)
- Suspend: `30 10 * * 1-5` (16:00 IST)

The scheduler needs permission to call the Render API. The current Render connector can inspect and deploy the service but does not expose suspend/resume actions, so the final suspend/resume automation must be configured in Render's dashboard/API or another scheduler with the Render API credential.

## Cost expectation

Render bills paid compute by active runtime, prorated to the second. The exact monthly amount therefore depends on the service plan and how long it remains active. Suspending at 16:00 and resuming at 09:00 on weekdays avoids paying for overnight/weekend API compute while preserving the persistent PostgreSQL database.
