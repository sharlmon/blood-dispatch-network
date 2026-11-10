# backend/ (Flask)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # or export vars
flask --app wsgi run --debug --port 5000
pytest
```

`app/` is the Flask app factory and routes (`/api/health` works now). Other folders below are imported by it.

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
