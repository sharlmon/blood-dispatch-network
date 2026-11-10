# backend/ (Flask)

The Flask API serves the decision engine (`engine/`) to the web screens, stores emergency
requests with their audit log, and serves the DS2 results files. Build the engine data first
([engine/README.md](engine/README.md)), then:

```bash
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # or export the variables below; then set AUTH_DISABLED=1 or a Clerk key
flask --app wsgi run --debug --port 5001
python -m pytest -q       # real-data tests skip unless DATA_DIR is set
```

Local demo without Clerk: `DATA_DIR=data AUTH_DISABLED=1 flask --app wsgi run --port 5001`.
The caller is then `user_demo` in organisation `org_demo` with role `org:admin`.

| Path | Owner | Purpose |
|---|---|---|
| `app/` | Full-stack 1 | App factory (`__init__.py`), routes (`routes.py`), engine adapter (`engine_service.py`), results reader (`results.py`), Clerk auth (`clerk_auth.py`) |
| `workflow/` | Full-stack 1 | Request store, workflow rules and audit log in SQLite (`store.py`) |
| `api/` | Full-stack 1 | Empty: the API lives in `app/` |
| `db/` | Full-stack 2 | Empty: CSV → SQLite ingest is `engine/load.py`, run by `scripts/build_db.py` |
| `engine/` | Data scientist 1 | Ranking engine: `rank.py`, `stock.py`, `compat.py`, `eta.py`, `reasons.py`, `load.py`, `config.py`. DS2's `cleaning.py`, `dataset.py` and `artifacts.py` sit alongside. `engine/ranking/` is an empty placeholder |
| `engine/arrival/` | Data scientist 2 | Arrival-window model used by the replay and the DS2 evaluation |
| `engine/replay/` | Data scientist 2 | Replay ladder against last year's data; `ds1_provider.py` plugs in DS1's rules |
| `engine/prealert/` | Data scientist 2 | Evening pre-alert test |
| `scripts/` | Data scientist 1 | `build_db.py`, `fit_eta.py`, `make_examples.py`, `sensitivity.py` |
| `sms/` | Full-stack 2 | SMS parser (not built yet) |
| `config/` | Full-stack 2 | `kenya.yaml` (engine), `settings.default.yaml` (API and DS2, demo clock) |
| `tests/` | all | Backend tests |

## Endpoints

All under `/api`. "Hospital" means signed in with a hospital (Clerk organisation) selected,
the `@require_hospital` decorator.

| Method | Path | Auth | What it does |
|---|---|---|---|
| GET | `/health` | public | API and engine status. Answers at once, even while the engine loads |
| GET | `/results` | public | `{files, scenarios}`: the DS2 results files and scenario folders that exist |
| GET | `/results/<name>?scenario=<folder>` | public | One results file's full envelope, unchanged. Names: `arrival_validation`, `data_quality`, `prealert_evaluation`, `replay_summary`, `summary` |
| GET | `/me` | signed in | The verified identity: `user_id`, `session_id`, `org_id`, `org_role`, `org_slug` |
| GET | `/facilities` | hospital | `{facilities}`: every facility in the engine data, sorted by name |
| POST | `/rank` | hospital | Ranks a RankInput and returns a RankResult. A preview: nothing is stored or audited |
| POST | `/requests` | hospital | Ranks a RankInput, then stores the request and its first audit entry. `201 {request, result, audit}` |
| GET | `/requests?limit=N` | hospital | `{requests}`: your organisation's requests, newest first. Default 20; above 100 counts as 100 |
| GET | `/requests/<id>` | hospital | `{request, result, audit}`: the record, the ranking that was shown, the audit trail oldest first |
| POST | `/requests/<id>/events` | hospital | `{action, facility_id?}`: one workflow step. Returns `{request, audit}` |
| GET | `/prealerts` | hospital | The evening list from `results/prealerts.json`, each row with `facility_name` |

`GET /health` returns `{status, country, engine: {state, model_used, stock_first, stock_last, message}}`.
`GET /prealerts` returns `{generated_at, stock_as_of, alerts, missing_snapshot, assumptions,
synthetic_data, source}`. It still answers when the engine is down (names are then `null`)
and answers 404 when the file is missing. Regenerate it with `scripts/evaluate_ds2.py`.

Quick check with the real data and `AUTH_DISABLED=1`: the golden case below returns a
`ranking` identical to `engine/examples/full_source.json`.

```bash
curl -s -X POST localhost:5001/api/rank -H 'Content-Type: application/json' \
  -d '{"facility_id": "HSP-004", "patient_group": "O+", "units_needed": 1, "requested_at": "2026-10-31T00:58:20"}'
```

### Errors

Every error is `{"error": {"code", "message"}}`, with a message a person can act on.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_request` | The body breaks the RankInput rules or the engine's input rules; a request dated before the first stock count; an unknown action; a pick of a site that was not offered; a bad `limit` |
| 401 | `missing_token`, `invalid_token` | No session token, or an invalid or expired one |
| 403 | `session_pending`, `hospital_required`, `forbidden` | Account not set up, no hospital chosen, or the wrong role |
| 404 | `not_found` | Unknown request id (another organisation's request gets the same answer), unknown results file or scenario, missing `prealerts.json`, unknown `/api` path |
| 405 | `method_not_allowed` | Wrong method for the path |
| 409 | `invalid_transition` | The action is not possible from the request's status, or a site step names a site that is no longer selected |
| 500 | `internal_error` | Unexpected server error |
| 503 | `engine_unavailable` | The engine data cannot be loaded (same message as `/health`'s `engine.message`), or it is still loading after 20 s |
| 503 | `auth_not_configured`, `auth_unavailable` | No Clerk settings and no `AUTH_DISABLED`, or Clerk's keys cannot be fetched |

## RankInput and RankResult

`POST /rank` and `POST /requests` take the same body.

| Field | Rule |
|---|---|
| `facility_id` | Required. The requesting facility, e.g. `"HSP-004"`. An unknown id is a 400 from the engine |
| `patient_group` | Required. `O-`, `O+`, `A-`, `A+`, `B-`, `B+`, `AB-`, `AB+` or `unknown`, any case. Unicode minus signs and dashes (`A−`) count as `-`. `unknown` means group O only |
| `units_needed` | Required. A whole number from 1 to 100. JSON booleans, decimals and strings are refused |
| `component` | Default `RBC`, any case. Only `RBC` is ranked (anything else is a 400); red cell and whole blood stock both count |
| `requested_at` | ISO 8601. No offset means East Africa Time; an offset is converted to it. Years 2000-2100. A day before the first stock count is a 400; after the data ends, the last count is used. Default: `DEMO_CLOCK`, then the settings file's `demo_clock`, then now |
| `limit_h` | Hours, above 0 and at most 72. Default `clinician_limit_h` from the engine settings (6). The clinician's limit for this request: a top option whose p90 is over it gets the `consider_emergency_O_or_transfer` advice |
| `mode` | `model` (default) or `baseline` (today's rule only) |
| `top_n` | 1 to 10, default 5 |

Optional fields sent as `null` count as absent. Unknown fields (a patient name, an ID, a
clinical note) are ignored: never passed to the engine, stored or echoed (tested).

A RankResult is `{ranking, clinician_limit_h, requester, sites}`:

- `ranking`: the engine's JSON (spec section 9), unchanged. Its reasons and `stock_note` are the
  engine's own words.
- `clinician_limit_h`: the limit used for this request.
- `requester`: `{facility_id, name, facility_type, county, lat, lon}`.
- `sites`: one entry per option plus the baseline site, with the same fields and `road_km` and
  `travel_hours_map` from the site to the requester (map hours rounded to 2 decimals, like the
  engine's options).

## Workflow

A request starts `open`. Each step is one `POST /requests/<id>/events` with an `action`, and a
person takes every step; the tool never moves a request on its own.

| Action | Allowed from | Status after |
|---|---|---|
| `pick` | `open`, `escalated`, `awaiting_shelf` | `awaiting_shelf`. Needs `facility_id`: one of the options shown or the baseline site. Picking again while awaiting the shelf check switches site |
| `shelf_confirmed` | `awaiting_shelf` | `confirmed` |
| `dispatched` | `confirmed` | `dispatched` |
| `arrived` | `dispatched` | `arrived` (final) |
| `not_on_shelf`, `confirm_timeout` | `awaiting_shelf` | `open`, with the selection cleared so the next option can be picked |
| `emergency_group_o`, `transfer_patient` | `open`, `escalated`, `awaiting_shelf`, `confirmed`, `dispatched` | `escalated` from `open`; otherwise unchanged. Always audited |
| `cancel` | `open`, `escalated`, `awaiting_shelf`, `confirmed` | `cancelled` (final) |

Any other action from any other status is a 409; an unknown action is a 400. **Site steps** (`shelf_confirmed`, `dispatched`, `arrived`,
`not_on_shelf`, `confirm_timeout`) may name their site with `facility_id`. It must be the
request's current selection, or the API answers 409 and records nothing; a `facility_id` that is
not a non-empty string is a 400. Without `facility_id` the step applies to the current
selection. The track page sends it.

Request ids are `BDN-` plus 8 random uppercase hex characters. A request is visible only to the
organisation that created it; other organisations get a 404.

## Audit log

The `audit` table, in the same SQLite file as the requests (`DB_PATH`), gets one row for
`request_created` and one per step. Each row records the action, the time in East Africa Time
(`+03:00`), the actor from the verified session (`user_id`, `org_id`, `org_role`) and a
`detail` object:

- `request_created`: group, units, component, limit, request time, stock date, mode, advice,
  `model_used`, the option site ids and the baseline site id.
- Every step: `from_status` and `to_status`.
- `pick`: the site id and name, the previous selection, `option_rank` (null when the site was
  only offered as the baseline) and `is_baseline`.
- `not_on_shelf` and `confirm_timeout`: the previous site and `waited_minutes` since the pick.
- Other steps: the selected site.

There is no free-text field. Read a request's trail with `GET /requests/<id>`; there is no
global audit endpoint, and no endpoint changes or deletes entries.

## Engine loading

- At startup a background thread loads the engine settings, the engine database and the arrival
  model, then ranks one request (`ENGINE_WARMUP`). On the starter data this takes about 5 s;
  a ranking then takes about 20 ms.
- `/health` shows the state (`idle`, `loading`, `ready` or `error`) and, when there is one, a
  `message`. It never waits for the engine or starts a load.
- Without the warm-up, the first call that needs the engine loads the data.
- A call made while the data loads waits up to 20 s, then gets 503 `engine_unavailable`.
- After a failed load, calls get 503 with the reason, and the load is tried again at most once
  every 30 s, so fixing the data needs no restart.
- Without `$DATA_DIR/eta_model.json` the engine is `ready` with `model_used: false`, and ranges
  use rough defaults.
- Public messages name files, not the server's folders. The full text is logged at WARNING
  (`Engine data problem: ...`).

## Settings

| Variable | Default | What it does |
|---|---|---|
| `DATA_DIR` | none | Engine data folder: starter CSVs, `blood.db`, `eta_model.json`. Relative paths resolve from the repo root (`DATA_DIR=data`) |
| `ENGINE_DB_PATH` | `$DATA_DIR/blood.db` | The engine's SQLite file, built by `scripts/build_db.py`. Relative paths resolve from the repo root |
| `ENGINE_COUNTRY` | `kenya` | Engine settings file `config/<name>.yaml` |
| `ENGINE_WARMUP` | on | Load the engine in the background at startup; `0`, `false`, `no` or `off` turns it off |
| `DEMO_CLOCK` | unset | The request time when a request gives none. ISO 8601, no offset means East Africa Time. Overrides `demo_clock` in the settings file; an invalid value is ignored with a warning. `.env.example` sets `2026-10-31T00:58:00` for demos on the synthetic data; leave it unset in a real deployment |
| `DB_PATH` | `../data/blood.sqlite` | The API's own SQLite file: requests and the audit log. Relative paths resolve from `backend/`. Created on first use |
| `RESULTS_DIR` | `results` | DS2 results served by `/results` and `/prealerts`. Relative paths resolve from the repo root |
| `SETTINGS_FILE` | `config/settings.default.yaml` | The API reads `country` and `demo_clock` from it. Relative paths resolve from `backend/` |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated origins allowed to call the API |
| `CLERK_PUBLISHABLE_KEY` or `CLERK_ISSUER` | unset | Turns on session verification (below) |
| `CLERK_JWKS_URL` | `<issuer>/.well-known/jwks.json` | Optional override |
| `CLERK_AUTHORIZED_PARTIES` | `CORS_ORIGINS` | Origins accepted in the token's `azp` |
| `AUTH_DISABLED` | unset | `1` makes every caller the demo user. Local demos only, never in production |

`backend/.env` is read at startup; real environment variables win.

## Known limits

- **No reservation.** Two open requests can be offered, and pick, the same units. The store
  does not track stock; a person confirms every transfer.
- **The confirmation timeout is recorded by a person.** The track page counts down 10 minutes,
  then someone presses "Ask the next source" (`confirm_timeout`, with `waited_minutes`). The
  server runs no timer and does not read `arrival.confirmation_timeout_minutes`.
- **No link between a Clerk organisation and a facility.** Any hospital organisation can rank or
  file a request for any `facility_id`. Requests are scoped by organisation only.
- **No supplying-site view.** Only the requesting organisation sees a request, so the site's steps
  are recorded from the requesting hospital's track page (its demo button stands in for the site).
- **Pre-alerts are generated offline** by `scripts/evaluate_ds2.py`; the API serves the last list.
- **No SMS endpoint yet** (`POST /sms` is a TODO in `routes.py`).
- **Gunicorn is not configured.** It is in `requirements.txt`. Without `--preload` each worker
  loads its own copy of the data. In development the Flask reloader loads it twice.

## Authentication (Clerk session verification)

`app/clerk_auth.py` verifies the signed-in user's Clerk session token on the server. The frontend sends it as `Authorization: Bearer <jwt>` (`useApi()` does this). Flask checks the RS256 signature against Clerk's public keys (cached), `exp`/`nbf`, the issuer, the authorized origin (`azp`), and rejects `pending` sessions (user has not chosen a hospital yet). A hospital is a Clerk Organization.

```bash
# backend/.env (git-ignored). The public key is enough: the issuer is derived from it.
CLERK_PUBLISHABLE_KEY=pk_test_...
```

Protect a route:

```python
from flask import g
from .clerk_auth import require_auth, require_hospital, require_role

@api.post("/requests")
@require_hospital              # signed in AND acting for a hospital
def create_request():
    caller = g.auth            # user_id, org_id, org_role, org_slug -> put these in the audit log
```

| Decorator | Requires |
|---|---|
| `@require_auth` | signed-in user |
| `@require_hospital` | signed in and a hospital selected (`org_id`) |
| `@require_role("org:admin")` | the above plus one of the roles |

Errors use the envelope above: `401 missing_token | invalid_token`, `403 session_pending | hospital_required | forbidden`, `503 auth_not_configured | auth_unavailable`. **If Clerk is not configured, protected routes fail closed (503)**; `/health` and `/results` still answer. `AUTH_DISABLED=1` is an explicit local-demo switch and must never be set in production. `GET /api/me` echoes the verified identity. Tests: `pytest tests/test_clerk_auth.py` (no network, uses a generated key pair).
