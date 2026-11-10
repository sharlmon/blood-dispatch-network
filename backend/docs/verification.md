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
