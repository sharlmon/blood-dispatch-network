# Backend API contract

Interactive Swagger UI: **http://localhost:5000/api/docs**. OpenAPI JSON:
**http://localhost:5000/api/openapi.json**. Both use the current server when hosted
elsewhere. Swagger assets are bundled locally. Use **Authorize** for a Clerk token;
mutations also need a unique **Idempotency-Key**. SMS adapters use separate gateway credentials.

Base path: `/api`. All requests and responses use JSON. No patient names, ages,
clinical notes or identifiers are accepted in request creation.

## Authentication and authorization

Existing Clerk session verification from `dev` is retained. Send
`Authorization: Bearer <session-token>`. The server verifies signature, issuer,
expiry, authorized origin and selected organization. Unconfigured authentication
fails closed with 503; invalid or missing tokens return 401.

Organizations map to facilities through the server-controlled `ORG_FACILITY_MAP`
JSON environment variable, e.g. `{"org_hospital":"HSP-004","org_centre":"RBTC-ELD"}`.
An ordinary user can create, pick, cancel or receive only for their mapped facility.
Only the current supplier can confirm, reject or dispatch. Request reads and request
audit are restricted to the requester/current supplier. Unmapped organizations are
denied. Facility directory reads are available to signed-in organization members;
raw inventory reads are restricted to that facility or a network operator.

The custom Clerk role `org:network_admin` grants network operator access, including
fallback controls, pre-alerts, results, and operational audit. Organization-level
`org:admin` alone does **not** grant network-wide access. Configure this custom role
in Clerk before using operator APIs. `AUTH_DISABLED=1` is an explicit **local demo
only** bypass. It grants the demo caller operator access, but does not bypass SMS
sender-to-facility restrictions.

## Retries and errors

Every HTTP POST/PUT mutation except the separately signed SMS webhook requires an
`Idempotency-Key` header containing 1–128 ASCII characters. Repeating the same key,
path, method and exact body returns the saved response. Reusing it with different
input returns 409. Authorization context is part of the key scope. Response storage,
stock changes, and audit writes commit in one SQLite transaction. Failed requests
roll back and do not consume the key. Cached response payloads are compacted after the configured retention period by the maintenance worker. Retry-key tombstones remain, so an expired cached response returns 409 without repeating the mutation. See deployment.md.

Errors use `{"error":{"code":"...","message":"..."}}`, including framework
404/405 errors. Validation errors return 400, authorization failures 403, missing
resources 404, state/stock conflicts 409, and unavailable dependencies 503. Maximum
HTTP body size is 64 KiB (413 when exceeded).

Paginated lists accept `limit` (1–200, default 50) and `offset` (nonnegative, default
0), and return `items`, `limit`, `offset`. Results and inventory return `items`.

## Endpoint inventory

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | /health | Public | Process health and configured country |
| GET | /ready | Public | Database access, readable engine tables and fresh inventory; 503 until ready |
| GET | /me | Signed in | Existing verified Clerk identity |
| GET | /config | Signed in | Safe country, group/component, timeout and policy settings |
| GET | /status | Signed in | Fallback state, inventory age and engine-data presence |
| PUT | /fallback | Operator | Enable/disable manual fallback with a reason |
| GET | /facilities | Organization member | Paginated directory; optional q and kind=centre/hospital filters |
| GET | /facilities/{id} | Organization member | Facility details, including imported engine metadata |
| GET | /facilities/{id}/inventory | Own facility/operator | Exact component/group counts, reservations, safety stock, snapshot timestamp |
| POST | /requests | Requester/operator | Create request and persist engine ranking, baseline and advice |
| GET | /requests | Request participant/operator | Paginated requests; facility_id, status, created_after/before filters |
| GET | /requests/{id} | Request participant/operator | State, ranking, selected option and exact allocations |
| GET | /requests/{id}/options | Request participant/operator | Saved engine ranking response |
| POST | /requests/{id}/options/refresh | Requester/operator | Refresh a pending request's ranking at the operational clock |
| POST | /requests/{id}/pick | Requester/operator | Select ranked supplier and reserve actual RBC inventory |
| POST | /requests/{id}/confirm | Current supplier/operator | Record full-quantity physical shelf confirmation |
| POST | /requests/{id}/reject | Current supplier/operator | Release stock and attempt the next eligible source |
| POST | /requests/{id}/dispatch | Current supplier/operator | Consume reserved stock and record dispatch |
| POST | /requests/{id}/cancel | Requester/operator | Cancel before dispatch and release reservations |
| POST | /requests/{id}/receive | Requester/operator | Record receipt of the full dispatched quantity |
| GET | /audit | Request participant/operator | Request events, with optional request_id and action filters |
| GET | /operations/audit | Operator | Fallback changes and inventory import history |
| POST | /prealerts/runs | Operator | Generate and persist an evening stock assessment |
| GET | /prealerts/runs | Operator | Paginated run history, latest first |
| GET | /prealerts/runs/{id} | Operator | Assessment results, assumptions, and missing snapshots |
| GET | /results | Operator | List allowlisted derived replay/evaluation artifacts |
| GET | /results/{id} | Operator | Read an artifact; nested experiment IDs supported |
| POST | /sms | Signed gateway/registered sender | Submit SMS commands through the shared workflow |

`created_after` and `created_before` are ISO timestamps with timezone. Non-operators
must specify `request_id` when reading `/audit`. No endpoint directly changes stock,
clinical compatibility rules or protected country settings.

## Request and workflow bodies

Create a request with the engine's established field names:

```json
{
  "facility_id": "HSP-004",
  "patient_group": "O+",
  "units_needed": 2,
  "component": "RBC",
  "clinician_limit_h": 6
}
```

Groups: A+, A-, B+, B-, AB+, AB-, O+, O-, unknown. Units: integer 1–100.
Only RBC requests are currently supported by the engine. `requested_at` defaults
to the operational clock; if supplied it must include a timezone and be within
five minutes of that clock. Set `demo_clock` in a local settings file for historical
data demonstrations. `clinician_limit_h` is optional, finite, greater than zero,
and at most 72. Legacy aliases `blood_group`, `units` and `product: "red_cells"`
are accepted; conflicting aliases are rejected.

The 201 response contains the persisted request (`id`, status, timestamps,
supplier/attempt/deadline), a canonical `request`, the existing engine's `ranking`
response, `selected_option`, and `allocations`. Ranking includes compatible source
options, p10/p50/p90 arrival ranges, reasons, baseline, and advice. These remain
suggestions, never a clinical release decision. `model_used: false` identifies the
engine's existing rough arrival fallback when the fitted model is absent.

Action examples (each requires its own idempotency key):

| Action | JSON body |
|---|---|
| pick | `{"supplier_id":"RBTC-ELD"}` |
| confirm | `{"supplier_id":"RBTC-ELD","attempt":1,"confirmed_units":2}` |
| reject | `{"supplier_id":"RBTC-ELD","attempt":1,"reason":"Unavailable on shelf"}` |
| dispatch | `{"supplier_id":"RBTC-ELD","attempt":1}` |
| cancel | `{"reason":"Using phone process"}` |
| receive | `{"received_units":2}` |

States: pending → awaiting_confirmation → confirmed → dispatched → received.
Cancellation is allowed before dispatch. Rejection/expiry releases reservations and
tries the next unattempted ranked source. When none can be reserved, the request
returns to pending and records `sources_exhausted`; use the phone process. Every
supplier still must confirm its shelf and explicitly dispatch. Old attempt IDs
cannot confirm newer selections. An attempted supplier cannot be selected again.

Selection requires a ranking and imported stock from the exact previous calendar
day in the configured timezone. Engine ranking may show older snapshots for
exploration; workflow selection refuses them. Inventory is reserved atomically
above safety stock, per actual blood group/component. Fixed engine compatibility
rules support compatible-group allocation, including group O only for unknown
patients. Hospital lending uses the engine's spare caps and imported safety reserves.
The engine's RBC+WB counts never manufacture RBC units: this workflow allocates
actual RBC rows only. Whole-blood and partial fulfillment, and receipt discrepancies,
require the phone process rather than silently substituting quantities/components.

Arrival windows are retained from the selected engine option; they are estimates
from request time, not a live transport tracker. The dispatch event records server
time in the audit trail. Receipt does not automatically restock the receiving site;
the next trusted inventory snapshot supplies its stock count.

Refresh updates a pending request's operational timestamp and saved options; it
does not reset its attempted-source history. Manual fallback blocks new requests,
selection, confirmation and dispatch. Cancellation, rejection, receipt and audit
remain available. `/status` also reports fallback when engine data or fresh stock
is absent. Readiness checks engine tables and the previous-day stock snapshot. Model artifacts
can still fall back to the existing rough estimator; engine failures return 503
from the request endpoint.

## Pre-alerts and results

`POST /prealerts/runs` accepts `{}` for the operational clock, or
`{"as_of":"2026-10-31T18:00:00+03:00"}` for an explicit assessment cutoff.
It calls the existing `generate_prealerts` service against validated dataset stock;
missing snapshots stay unknown. It does not place replenishment orders.

`PUT /fallback` accepts `{"enabled":true,"reason":"Maintenance"}`; a nonempty
reason is required when both enabling and clearing fallback. Changes are audited.

Results allow only summary, replay_summary, arrival_validation,
prealert_evaluation, data_quality and prealerts JSON files under the configured
results directory. Model samples and arbitrary filesystem paths are not served.
For example `/results/summary` or `/results/hospital-reserve-5/replay_summary`.
Existing replay generation remains an offline CLI (`scripts/evaluate_ds2.py`);
no unbounded replay execution endpoint is exposed.

## SMS gateway envelope

A provider adapter must POST this JSON envelope:

```json
{"message_id":"gateway-unique-id","from":"+254700000001","text":"REQUEST O+ 2"}
```

Set `SMS_WEBHOOK_SECRET` and register senders in `SMS_SENDERS` (server-side JSON):

```json
{"+254700000001":{"user_id":"sms-lab-worker","org_id":"org_hospital","facility_id":"HSP-004"}}
```

Headers: `X-SMS-Timestamp` is current Unix time in seconds (within five minutes of
real wall time, independently of demo_clock). `X-SMS-Signature` is the lowercase
hex HMAC-SHA256 of `timestamp + "." + exact_raw_body` using the shared secret.
Invalid signatures return 401; unknown senders return 403. A gateway message ID is
persistently deduplicated within its authenticated sender/facility identity.
Raw phone numbers and SMS text are not written to workflow audit or idempotency rows.

Commands:

```text
REQUEST <blood-group|unknown> <units>
STATUS <request-id>
PICK <request-id> <supplier-id>
CONFIRM <request-id> <attempt> <units>
REJECT <request-id> <attempt> <reason>
DISPATCH <request-id> <attempt>
```

Response: `message_id`, `request`, and `reply`. The gateway adapter is responsible
for sending the returned reply. Africa's Talking uses separate callback endpoints
and a persistent outbound queue, described in [sms.md](sms.md); its native
callbacks must not be pointed at this HMAC endpoint.

## Local operations

Run from `backend/`, with dependencies installed and the starter CSVs available:

```bash
export DATA_DIR=/absolute/path/to/synthetic-csvs
export DB_PATH=/absolute/path/to/workflow.sqlite
export ENGINE_DB_PATH=/absolute/path/to/engine.sqlite
# Configure Clerk and organization mappings, or explicitly set AUTH_DISABLED=1 locally.
.venv/bin/python -m flask --app wsgi ingest-data
.venv/bin/python -m flask --app wsgi run --port 5000
.venv/bin/python -m pytest -q
```

Use `SETTINGS_FILE` for a country/demo-clock YAML and `ENGINE_SETTINGS_FILE` for the
existing engine's country YAML (default kenya.yaml). Lending must be enabled in
both configurations. The engine database and workflow database must be different
files. Ingestion validates/builds the engine database and imports exact previous-day
stock into the workflow database; historical starter data requires a historical
demo clock. It refuses active reservations and repeated/older stock snapshots, so
rerunning it cannot restore consumed units. The engine DB and workflow DB are
separate stores: engine build can succeed before workflow synchronization fails;
read the command output and fix the reported condition before serving requests.

The existing `seed-demo` command creates only a minimal inventory fixture. It does
not create a ranking dataset and is not enough to run the integrated workflow.

Run `flask --app wsgi expire-confirmations` every minute from the deployment's
scheduler to release expired reservations and try the next eligible source. Flask
does not launch a scheduler automatically. Schedule pre-alert runs by invoking the
operator HTTP endpoint with a unique idempotency key, or the `run-prealerts` CLI.

The original first-slice requests remain readable after this additive schema update.
Legacy requests without engine metadata cannot select a supplier; cancel/recreate
pending requests. Legacy reservations can still be cancelled or expired safely.

## Validation and review

Tests cover real-engine request integration on synthetic fixtures, concurrent
reservations and duplicate submissions, scope/role authorization, stale supplier
attempts, retries, timeout/rejection advancement, compatible-group reservations,
SMS signatures/deduplication, operational fallback, and ingestion through dispatch.
Full starter-dataset tests skip when DATA_DIR is not available.

CONTRIBUTING.md requires whole-team review for group-O fallback, lending limits and
human-approval behavior before merging. Clerk organization mappings, gateway secrets,
a real synthetic dataset, and deployment scheduling are environment configuration;
this repository does not create them automatically.

Production setup, scheduled maintenance, backup/restore and dataset acceptance tools
are documented in [deployment.md](deployment.md).

Africa's Talking adapters are documented in [sms.md](sms.md) and Swagger:
`POST /api/sms/africastalking/inbound` and
`POST /api/sms/africastalking/delivery`. Both use a separate callback token and
accept provider form encoding. Outbound sending uses a persistent worker queue.
