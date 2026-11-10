# Backend verification and deployment

The backend has local operational tools and service templates. They do not create
Clerk accounts, provision SMS services, install system services or deploy a server.

## Verify the starter dataset without touching operational stock

Install requirements and point the validator at the supplied synthetic starter CSVs:

```bash
cd backend
.venv/bin/python -m flask --app wsgi verify-workflow \
  --data-dir /absolute/path/to/starter-csvs \
  --facility-id HSP-004 --group O+ --units 1 \
  --report /tmp/backend-verification.json
```

This builds temporary engine and workflow databases, derives a historical clock
from the final stock day, and checks all of:

- request → deterministic ranking → pick → confirm → dispatch → receive;
- an exact retry of dispatch leaves stock unchanged;
- supplier rejection releases stock and selects an eligible backup;
- confirmation timeout releases stock and selects an eligible backup;
- the old supplier attempt cannot confirm a newer selection.

It refuses an existing report file. The scenario must have at least two full RBC
suppliers; choose a different requester/group/quantity if it does not. Its local
identity bypass is restricted to the temporary verification app and is explicitly
labelled in the report. It does not verify live Clerk accounts or SMS delivery.
Raw patient data and operational databases are not modified or copied into reports.
A generated small fixture passing these checks does not replace starter-data testing.

Run the complete dataset test suite separately, using the same CSV directory:

```bash
DATA_DIR=/absolute/path/to/starter-csvs .venv/bin/python -m pytest -ra
```

Review every skip. Dataset tests still skip when DATA_DIR is absent. The prepared backend CI template (`deploy/backend-ci.yml`) tests Python 3.12 and
3.14. It must be installed as `.github/workflows/backend-ci.yml` after granting
GitHub workflow permission; it is not active yet. Ignored starter data is not
uploaded to CI automatically.

## Identity and SMS setup

Configure the existing Clerk issuer/publishable key and authorized frontend origin.
Set `ORG_FACILITY_MAP` using actual organization IDs and dataset facility IDs. The
custom `org:network_admin` role is a network operator role; ordinary organization
administrators do not inherit it.

`flask --app wsgi check-config` reports prerequisites and mapping counts without
printing secrets, tokens or mappings. It exits nonzero for missing production
configuration or unavailable engine data. This is a configuration/data probe, not
an external Clerk login verification.

For a live-account check, sign in separately as a requester and supplier, use their
short-lived Clerk tokens in Swagger Authorize, and exercise the complete workflow
against the synthetic dataset. Confirm the requester cannot perform supplier actions
and an unrelated organization cannot read or mutate the request. Do not paste
session tokens into Git, logs, reports or chat. Tests additionally exercise genuine
RS256 signatures with local test keys through the complete workflow; they do not
contact or claim verification of the live Clerk tenant.

SMS supports the signed provider-neutral envelope and a dedicated Africa's Talking
adapter with queued outbound notifications, replies and delivery reports. See
[sms.md](sms.md) for configuration, callback protection and the worker. Production
requires a webhook secret of at least 32 characters when senders are configured.

## Production process and configuration

Use `deploy/backend.env.example` as the shape of a private server environment file.
Replace all placeholders. Production startup refuses AUTH_DISABLED, missing Clerk
configuration/mappings, relative/in-memory workflow storage and debug mode.

The supplied service templates assume:

- checkout at `/opt/blood-dispatch-network`, with a Python venv in `backend/.venv`;
- an unprivileged `blood` user/group;
- private environment/settings files under `/etc/blood-dispatch`;
- writable local storage under `/var/lib/blood-dispatch`;
- HTTPS termination in the host's reverse proxy/load balancer.

Use a local persistent filesystem for SQLite, on the same host as API and maintenance
processes. Multiple Gunicorn workers are supported; multiple hosts sharing the SQLite
file over a network filesystem are not a supported deployment here.

After provisioning the paths/user/environment on the chosen server:

```bash
cd /opt/blood-dispatch-network/backend
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m flask --app wsgi ingest-data
.venv/bin/python -m flask --app wsgi check-config
.venv/bin/gunicorn --config gunicorn.conf.py wsgi:app
```

The historical hackathon dataset needs a historical `demo_clock` in the private
settings file. It must not be represented as current real-world inventory. A frozen
demo clock also freezes workflow expiry; advance it deliberately for timeout demos.
Ingestion refuses repeated/older snapshots and active reservations. Resolve pending
supplier reservations first, import a newer snapshot, then restart API workers so
their existing engine caches reload. Do not run concurrent CSV importers.

The supplied Gunicorn config uses two threaded workers, request recycling and bounded
worker timeouts. The Flask application emits request IDs, method, route template,
status and duration; it does not log tokens, payloads, phone numbers or query strings.
The response includes `X-Request-ID`. Production logs are JSON and go to stderr.
Route templates avoid logging raw identifiers embedded in unrecognized paths.

Source references for deployment configuration:
[Gunicorn configuration](https://gunicorn.org/configure/) and
[GitHub Python CI](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).

## Scheduled maintenance

Run a standalone maintenance worker:

```bash
.venv/bin/python -m flask --app wsgi maintenance --interval 30
```

Or invoke `maintenance --once` each minute from an existing scheduler. Do not add
both approaches deliberately; persistent job claims protect against duplicate
workers, but a single configured scheduler is easier to operate.

The worker expires overdue confirmations once per real-clock minute, runs evening
pre-alerts once per operational day after `prealert.run_hour` (default 18:00 in the
configured timezone), and compacts retry responses once per real day. Completed
pre-alert checkpoints survive restarts. A failed job rolls back its action and
checkpoint, records only the error class, and can retry after a one-minute cooldown.
Claims abandoned by a stopped process expire after 15 minutes. Missing data produces
a failed job rather than a successful empty assessment. Start this worker only after
dataset/configuration validation. It sends no external messages.

`deploy/blood-api.service` and `deploy/blood-maintenance.service` are ready-to-edit
systemd templates. Install/enable them only on the selected host after checking paths,
permissions, secrets and data. They have not been installed by editing this repository.

## Backups, restoration and retention

```bash
.venv/bin/python -m flask --app wsgi backup-db --directory /var/lib/blood-dispatch/backups
.venv/bin/python -m flask --app wsgi backup-db --output /tmp/workflow-snapshot.sqlite
.venv/bin/python -m flask --app wsgi restore-db /tmp/workflow-snapshot.sqlite \
  --output /var/lib/blood-dispatch/restored-workflow.sqlite
```

Backups use SQLite's online backup API, include committed WAL state, and pass
integrity and foreign-key checks before publication. Files are private (0600).
Existing destinations are never overwritten. Restore creates a NEW file: stop API
and maintenance processes, validate the restore, change DB_PATH to that file, then
restart and recheck readiness. Keep a copy of the previous database until recovery
is confirmed. Engine data/models can be rebuilt from the preserved source dataset;
protect those artifacts separately. Copy backups to storage independent of the host
and establish the organization's backup retention policy before production use.

The optional `blood-backup.service`/`blood-backup.timer` templates schedule uniquely
named verified backups daily at 02:00 Africa/Nairobi, with up to five minutes of
jitter. Existing backups are never automatically deleted.

Retry-cache maintenance retains key/fingerprint tombstones permanently while removing
old response payloads after `IDEMPOTENCY_RETENTION_DAYS` (default 30):

```bash
.venv/bin/python -m flask --app wsgi prune-idempotency --older-than-days 30
```

A replay of a compacted key returns 409 and cannot duplicate the original request or
stock mutation. Inspect current request state before proceeding; do not automatically
submit a new key in response to that error. Retention uses real UTC wall time,
independently of the demo clock. Old databases are migrated additively on startup;
existing retry keys receive a conservative migration timestamp, preserving their
responses for a full retention period. Stop API and maintenance processes before
the first deployment of this migration; older workers use the previous insert
shape and must not run concurrently with the migrated schema. Request and audit records are not deleted.

## Remaining external acceptance

Starter-data verification in this workspace is recorded in verification.md.
Live Clerk organization IDs, authorized SMS facility/phone mappings, receiving
shortcode and public callback URLs, and target hosting environment are still
required to complete live acceptance. Compatibility,
lending and human-approval behavior still need the team review required by
CONTRIBUTING.md before merging PR #30. Partial/whole-blood fulfillment and receipt
discrepancies remain on the existing phone process.

For Africa's Talking configuration, public callbacks and the optional
`blood-sms.service` worker, follow [sms.md](sms.md). Enable sending only after
registering the facility phone mappings; API keys alone do not enable messages.
