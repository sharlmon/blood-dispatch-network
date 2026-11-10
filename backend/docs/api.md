# Backend API — first implementation slice

All routes use `/api`. This implementation is for local development with synthetic data. Authentication, authorization, idempotency keys, production migrations, ranking, compatibility substitution, stock freshness enforcement, arrival estimates, and automatic next-source selection are not implemented. Do not expose it as a production dispatch service.

## Implemented endpoints

| Method | Path | Behavior |
|---|---|---|
| GET | /health | Process health and country |
| GET | /ready | Database connectivity and whether inventory exists |
| GET | /facilities | Paginated facility list |
| GET | /facilities/{id} | Facility details |
| GET | /facilities/{id}/inventory | Stock, reservations, safety stock, available units, update timestamp |
| POST | /requests | Create a pending request; returns 201 |
| GET | /requests | Paginated requests; optional facility_id and status filters |
| GET | /requests/{id} | Current request state and supplier attempt |
| POST | /requests/{id}/pick | Reserve units and start supplier confirmation deadline |
| POST | /requests/{id}/confirm | Confirm the full requested quantity |
| POST | /requests/{id}/reject | Release reservation and return request to pending |
| POST | /requests/{id}/dispatch | Consume reserved units and record dispatched status |
| POST | /requests/{id}/cancel | Release any reservation and cancel request |
| GET | /audit | Paginated events; optional request_id filter |

Lists accept `limit` (1–200, default 50) and `offset` (nonnegative, default 0). List responses contain `items`, `limit`, and `offset`; inventory contains `items`. Errors raised by endpoint validation return `{"error":{"message":"..."}}`: 400 invalid input, 404 missing resource, 409 workflow conflict. Unknown Flask routes still use the framework's default error response.

## Local walkthrough

Run from `backend/` after installing requirements:

```bash
.venv/bin/python -m flask --app wsgi seed-demo
.venv/bin/python -m flask --app wsgi run --port 5000
```

Seeding is explicit, synthetic, and refuses databases that already contain facilities. No CSV data is imported automatically. Default SQLite location is the repository's `data/blood.sqlite`; override with `DB_PATH`.

Create a request:

```http
POST /api/requests
Content-Type: application/json

{"facility_id":"DEMO-H1","blood_group":"A+","product":"red_cells","units":3}
```

Supported groups: A+, A-, B+, B-, AB+, AB-, O+, O-. Products: red_cells, whole_blood. Units must be an integer from 1 through 100. Unknown groups are rejected until the configured group-O policy is implemented and reviewed. The response is the persisted request, including its generated `id`; ranking and ETA fields are deliberately absent.

Use the returned request ID for subsequent calls:

```http
POST /api/requests/{id}/pick
Content-Type: application/json

{"supplier_id":"DEMO-C1"}
```

The returned `attempt` identifies the supplier selection. Confirmation, rejection, and dispatch must include the matching attempt and supplier ID:

```http
POST /api/requests/{id}/confirm
Content-Type: application/json

{"supplier_id":"DEMO-C1","attempt":1,"confirmed_units":3}
```

```http
POST /api/requests/{id}/dispatch
Content-Type: application/json

{"supplier_id":"DEMO-C1","attempt":1}
```

Reject with `{"supplier_id":"DEMO-C1","attempt":1,"reason":"Stock unavailable"}`. Cancel with `{"reason":"No longer needed"}`.

## State and stock rules

- pending → awaiting_confirmation → confirmed → dispatched.
- Rejection or expired confirmation returns to pending, releasing stock.
- Cancellation is allowed before dispatch and releases stock.
- Initial selection accepts external centres only, excludes SAT-* IDs, and reserves the exact requested blood group/product. Hospital lending and alternative compatible groups are deferred.
- SQLite write transactions serialize reservations. Available units are on_hand minus reserved minus safety_stock, floored at zero.
- Full-quantity confirmation is required; partial fulfillment is deferred.
- The confirmation deadline is enforced even if the expiry command has not run.
- Old attempts cannot confirm a newer selection. Duplicate mutation calls return conflicts rather than silently repeating stock changes; request creation retries are not yet deduplicated.
- Every successful workflow action and expiry is audited. Failed actions roll back their writes.
- Dispatched and cancelled requests are terminal in this slice. Delivery confirmation is not implemented.

Run the following periodically to release expired reservations:

```bash
.venv/bin/python -m flask --app wsgi expire-confirmations
```

There is no background scheduler embedded in Flask. Expiry does not automatically select another supplier because the ranking engine is not available. Explicit selection is required.

## Remaining backend work

1. Identity/role authorization and idempotency, consistent framework-level errors.
2. Dataset-specific CSV ingestion and freshness rules.
3. Ranking integration, source-options endpoint, compatibility and lending policies, baseline and arrival windows.
4. Automatic next-source attempts after rejection/timeout, with reviewed human-approval behavior.
5. Fallback status/control and safe operational configuration endpoints.
6. Pre-alert runs and results.
7. SMS webhook authentication, command parsing, and shared workflow integration.
8. Replay CLI and results endpoints.

Changes to group-O fallback, lending limits, or human approval require whole-team review under CONTRIBUTING.md before merging.
