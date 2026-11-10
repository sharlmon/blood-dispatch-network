# backend/ (Flask)

Swagger UI: **http://localhost:5000/api/docs** (use your chosen server port).
OpenAPI: **http://localhost:5000/api/openapi.json**.

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # or export vars
flask --app wsgi run --debug --port 5001
pytest
```

`app/` provides the Flask API, persistent workflow, Clerk authorization, engine adapters, SMS intake and operational commands. See [the API contract](docs/api.md) for all routes, configuration, and examples.

| Path | Owner | Purpose |
|---|---|---|
| `db/` | Full-stack 2 | CSV → SQLite ingest and schema |
| `api/` | Full-stack 1 | HTTP API, deployment entrypoint |
| `workflow/` | Full-stack 1 | Request → pick → confirm → dispatch logic, audit log, fallback mode |
| `engine/ranking/` | Data scientist 1 | Ranking engine (+ stretch: today's centre stock estimate) |
| `engine/arrival/` | Data scientist 2 | Arrival-window ranges |
| `engine/replay/` | Data scientist 2 | Replay ladder against last year's data |
| `engine/prealert/` | Data scientist 2 | Evening pre-alert test |
| `sms/` | Full-stack 2 | SMS parser |
| `config/` | Full-stack 2 | Settings file (country-portable), demo clock |
| `tests/` | all | Backend tests |

## Request workflow foundation

See [the API contract and local walkthrough](docs/api.md) for implemented routes,
request bodies, state transitions, and remaining work. Seed an empty local database
with `flask --app wsgi seed-demo`; run `flask --app wsgi expire-confirmations`
periodically to release expired supplier reservations. These commands are explicit;
starting the server does not seed inventory or start a scheduler.
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

Errors are JSON `{"error": {"code", "message"}}`: `401 missing_token | invalid_token`, `403 session_pending | hospital_required | forbidden`, `503 auth_not_configured | auth_unavailable`. **If Clerk is not configured, protected routes fail closed (503).** `AUTH_DISABLED=1` is an explicit local-demo switch and must never be set in production. `GET /api/me` echoes the verified identity. Tests: `pytest tests/test_clerk_auth.py` (no network, uses a generated key pair).
