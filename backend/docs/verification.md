# Backend verification — 10 November 2026

The supplied Terumo BCT Africa Hackathon starter archive was tested locally. Its
README explicitly identifies every record as synthetic. Original extracted CSVs
remain in ignored local data storage; no raw dataset or private environment
configuration is committed.

- **343 backend tests passed, zero skipped** against the cleaned copy of the supplied starter CSVs.
- The isolated workflow validator passed on original and cleaned copies: dispatch
  and receipt, idempotent dispatch retry, rejection and timeout recovery, reservation
  release, and stale-attempt rejection.
- The conservative cleaner produced eleven tables without removing exact duplicate
  rows in this archive. Review flags are retained; unknown values are not inferred
  and clinical facts are not rewritten.
- Local ingestion loaded 47 facilities, 2,162 routes, 185,785 daily-stock rows,
  49,426 units, 35,181 transfers and 17,430 historical requests into the engine.
  The workflow database contains 382 component/group inventory rows for 31 October.
- The local historical demo clock is 1 November 2026, 01:00 Africa/Nairobi. This
  represents a synthetic historical snapshot, not current inventory.
- Arrival fitting used 3,541 waits and 3,436 transport ratios before 1 July 2026.
  On 1,734 held-out transfers, model p50 MAE was about 0.95 hours and about 80% fell
  inside p10–p90. These are exploratory synthetic-data metrics, not clinical claims.
- Operational tests cover backup/restore, additive migration, retry-key tombstones,
  concurrent scheduler deduplication, failed-job retry and abandoned-lease recovery.
- Genuine RS256 test tokens pass through the full workflow; forged tokens and
  requester attempts at supplier actions are rejected. Signing keys are local test
  fixtures; no live Clerk tenant is claimed to have been verified.

Gunicorn configuration validation passed. The backup calendar expression was checked
as 02:00 Africa/Nairobi. Production system services have not been installed. Live
Clerk issuer/mappings, SMS provider/account integration and the target host remain
external setup requirements.

The backend CI template is included under deploy/backend-ci.yml. GitHub rejected
active workflow publication because the OAuth token lacks workflow scope; CI
activation remains pending that authorization.


## SMS sandbox acceptance — 11 November 2026

The free Africa's Talking sandbox was exercised through a public HTTPS ngrok tunnel
with separate requester and supplier simulator sessions. The requester was scoped
to HSP-004 and the supplier to HSP-001. Private keys, callback tokens, and actual
staff phone numbers remain in ignored local configuration.

- `REQUEST O+ 1` returned the real golden-case ranking: National Referral 2.6h
  (1.4–3.8h), Eastlands County 2.8h (1.6–4.0h), and Naivasha 4.6h (3.3–5.9h),
  alongside the Eldoret baseline of about 8.9h and the unconfirmed-stock note.
- `1` selected National Referral; supplier `YES` confirmed stock and the requester
  received the arrival range. Supplier `SENT` completed dispatch and both simulator
  sessions showed the dispatch update.
- The isolated demo workflow database records one request in `dispatched` state,
  with `created`, `pick`, `confirm`, and `dispatch` audit events.
- All 376 backend tests passed, including real-data golden ranking, short commands,
  legacy commands, authorization, duplicate handling, rejection and timeout advance,
  outbox atomicity, transport failures, retries, and delivery-report ordering.
- Actual simulator receipt was observed. The outbox records provider acceptance;
  no `Success` delivery reports were present at the acceptance check. Provider
  acceptance and delivery-report confirmation remain distinct states.

Use [the sandbox walkthrough](sms.md#video-demo-sandbox-simulator-and-tunnel) and
`backend/sms-demo.env.example` to reproduce this with a separate demo database.
The profile freezes 31 October 2026 at 00:58:20 EAT with 30 October synthetic stock.
This verifies sandbox SMS only; live shortcode service and live Clerk integration
remain separate setup work.


## Isolated server acceptance — 11 November 2026

The API, sandbox SMS worker, and maintenance worker were deployed in the separate
`blood-dispatch` Docker Compose project with persistent project-owned SQLite storage.
Public HTTPS readiness reports both engine data and inventory loaded. The public
facility API permits the GitHub Pages origin, and the public ranking preview returns
the real golden-case 2.6h, 2.8h, 4.6h options and 8.9h baseline. A synthetic request
was created, retried idempotently, and cancelled without reserving or consuming stock.
All 28 frontend adapter tests passed and the connected static frontend built successfully.
The final build explicitly disables Clerk and the browser-local demo login as requested.
Existing unrelated containers retained their IDs and remained running.

The server uses the requested sign-in bypass and synthetic historical stock, rather
than the authenticated production profile. Africa's Talking dashboard callbacks must
be pointed at the server URLs to remove their remaining dependency on the local tunnel.
