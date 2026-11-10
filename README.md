# Blood Dispatch Network

> Network Finder with honest arrival windows — built for the **Terumo BCT Africa Hackathon 2026**.

It's 1 a.m. A patient needs blood urgently and the hospital fridge doesn't have the right type. Today the lab worker phones the main blood centre and hopes; if it has none, they phone another and wait with no idea how long it will take. In the data, about **1 in 4** of these patients got no blood at all. Meanwhile a hospital 30 minutes away often has spare bags of exactly that type, but hospitals never share with each other.

## What it does

1. The lab worker enters what the patient needs, on a computer or by **SMS from a basic phone**.
2. The tool checks every nearby blood centre and hospital and lists those with **spare, compatible units**. A hospital only shares what it can spare, so it never leaves itself short.
3. Each option gets an **honest arrival window**, e.g. "median 2½ h, estimated 80% interval 2–3½ h".
4. The lab worker picks one. The supplying site **confirms the units are on the shelf**, then dispatches.
5. If the wait is too long, the tool says so plainly so the clinician can act now (emergency group O, or transfer the patient).
6. **Evening pre-alert:** lists hospitals that have run out of the most common blood type so the centre can top them up before the 1 a.m. emergency.

## Safety principles

- A **person makes every decision**; the tool suggests, people approve.
- The tool never decides blood group. Unknown group → request group O only, per hospital protocol.
- A trained lab worker crossmatches and checks every unit before transfusion.
- Lending protects O-negative stock held for girls and women of childbearing age.
- If the tool fails, everyone **falls back to the existing phone process**.

## Why it matters (synthetic data, Nov 2025 – Oct 2026)

The earlier concept estimates (~2 hours sooner and ~290 additional patients)
have not been reproduced by the implementation in this repository. The DS2
pipeline now produces a chronological held-out evaluation, baseline comparisons,
and explicit assumptions in `results/*.json`.

See [DS2 implementation and reproducible evaluation](docs/ds2-implementation.md)
for commands, integration contracts, data cleaning, test periods and limitations.
Snapshot replay counts potential opportunities, not unique patients served;
hospital lending remains an unobserved assumption. The web app's **Evidence**
page shows these files.

## Architecture

**Stack:** Nuxt 4 (frontend) · Flask (backend API) · Python decision engine · SQLite · SMS gateway (not built yet) · CSV in, JSON out.

```
 Lab worker ──► Web screens (Nuxt) ──┐
 Basic phone ─► SMS gateway ─► SMS parser ─┤
                                           ▼
 CSVs ─► Ingest ─► SQLite ─►  Flask API ── Workflow ── Audit log
                     │            │          (request → pick → confirm → dispatch)
                     │            │          Fallback mode (phone process)
                     ▼            ▼
              Decision engine (deterministic, no LLM-generated numbers)
              ├─ Ranking: compatible spare units above safety stock
              ├─ Arrival ranges: p10 / p50 / p90
              ├─ Evening pre-alert: hospitals out of common groups
              └─ Replay: reruns past requests ─► results/*.json ─► Results tab

 Country settings file (lending rules, safety stock, arrival params, demo clock)
 configures engine and workflow: a new country = a new file, not a code change.
```

### Components

| Layer | Component | Owner | Role |
|---|---|---|---|
| Clients | Web screens | Frontend | Request entry, ranked options, tracking with the audit trail, and the **Pre-alerts** page (the evening list) |
| Clients | SMS parser | Full-stack 2 | Turns text messages into structured requests (not built yet) |
| Clients | Results tab | Frontend | The **Evidence** page: replay, arrival and alert results from `results/*.json` |
| Backend | HTTP API | Full-stack 1 | Flask API under `/api`: serves the engine to the screens, stores requests, serves `results/*.json` |
| Backend | Workflow | Full-stack 1 | Request, pick, shelf check, dispatch, arrival. After 10 minutes without a shelf confirmation, a person records it and moves to the next option |
| Backend | Audit log | Full-stack 1 | Records every request and step with who did it and when |
| Backend | Fallback mode | Full-stack 1 | A phone-process banner in the web app when the API or the engine is down |
| Engine | Ranking (`rank_sources()`) | Data scientist 1 | Compatible spare units above safety stock |
| Engine | Arrival ranges | Data scientist 2 | p10 / p50 / p90 arrival estimates |
| Engine | Evening pre-alert | Data scientist 2 | Hospitals out of common groups, from yesterday's closing stock |
| Engine | Replay | Data scientist 2 | Reruns past requests, writes results JSON |
| Data | Ingest | Full-stack 2 | Loads starter CSVs (git-ignored `DATA_DIR`) into SQLite |
| Data | Country settings | Full-stack 2 | Per-country YAML config |

Where each component lives in the code: [docs/architecture](docs/architecture/README.md#where-it-lives-now).

### Emergency request sequence

1. The lab worker submits a request on the web (SMS is not built yet). The API ranks it, stores it and logs it.
2. The API calls `rank_sources`, which returns ranked options with ranges and reasons, plus a baseline.
3. If the top option's p90 exceeds the clinician's time limit, the tool advises considering emergency group O or patient transfer.
4. The lab worker sees the options and the baseline side by side, then picks, changes or rejects.
5. The supplying site confirms the units are on the shelf, then dispatches. If there is no confirmation within 10 minutes, a person records the timeout and the request moves to the next option.
6. The arrival window goes back to the lab worker. Every step is logged.

### Ranking engine (`rank_sources()`)

- **Compatibility** (`compat.py`): fixed lookup table, never a model. Unknown group falls back to O- and O+ only, with a flag.
- **As-of date:** request date minus one day, so stock is yesterday's closing count. Edges of the data: the first day uses its own count; a request after the data ends uses the last count.
- **Candidates:** all facilities except the requester and `SAT-*` satellites; centres only if `sharing_allowed` is false.
- **Spare stock** (`stock.py`): centres offer all compatible red cells and whole blood; hospitals offer stock minus the higher of usual level and minimum keep; O- never drops below the O- reserve; near-expiry units are capped at the spare count.
- **Arrival time** (`eta.py`): fixed-seed Monte Carlo of wait + extra time + ratio x travel hours gives p10/p50/p90. Without a model file it uses a simpler estimate and sets `model_used` to false.
- **Sorting** (`rank.py`): p50 in quarter-hour buckets, then near-expiry first, backup power first, most spare units.
- **Full vs partial:** if no candidate covers the request, returns best partial options with a `no_full_source` advice.
- **Baseline:** today's rule (also the fallback): the supply centre if it has enough, otherwise the nearest other regional centre with enough stock, by road distance (spec section 8, decided 2026-11-10). Quote is map time plus two hours, no range.
- **Reasons** (`reasons.py`): string templates filled with computed numbers.
- **Served by the API** (`backend/app/services.py`, `workflow.py`): checks the input, saves the engine's JSON unchanged under `ranking`, and reserves stock only when a person picks a source. Endpoints: [backend/docs/api.md](backend/docs/api.md).

## Repo structure

```
.
├── frontend/   Nuxt 4: request, results, track, pre-alerts and evidence screens
├── backend/    Flask API and the decision engine
│   ├── app/        Flask app factory, routes, engine adapter, results reader, Clerk auth
│   ├── workflow/   request store, workflow rules, audit log (the API's SQLite)
│   ├── engine/     ranking, arrival, replay, prealert, CSV -> SQLite load
│   ├── scripts/    build_db.py, fit_eta.py, make_examples.py, sensitivity.py
│   ├── config/     country settings, demo clock
│   ├── api/ db/    empty placeholders
│   ├── sms/        SMS parser (not built yet)
│   └── tests/
├── docs/       architecture, engine spec, DS2 guide, data protection, brand, video
├── results/    DS2 results JSON for the expert review (committed)
├── data/       dataset and engine data (git-ignored)
└── scripts/    evaluate_ds2.py, deploy-pages.sh
```

## Quick start

You need Python 3.11+, Node 22+ and the hackathon starter kit. Run from the repo root.

```bash
# 1. Data: unzip the starter kit's CSVs into data/ (git-ignored). The kit's own README.md
#    overwrites ours: keep the kit's copy under another name, then restore ours.
mv data/README.md data/README.starter-kit.md && git restore data/README.md

# 2. Python
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# 3. Engine data (once), from backend/
cd backend
export DATA_DIR=data            # relative paths resolve from the repo root
python scripts/build_db.py      # CSVs -> data/blood.db, with data checks
python scripts/fit_eta.py       # arrival model -> data/eta_model.json and eta_metrics.json

# 4. API on port 5001, from backend/. AUTH_DISABLED=1 is for local demos only.
#    ingest-data loads the starter CSVs and yesterday's stock into the API's database.
DATA_DIR=data AUTH_DISABLED=1 DEMO_CLOCK=2026-10-31T00:58:00 flask --app wsgi ingest-data
DATA_DIR=data AUTH_DISABLED=1 DEMO_CLOCK=2026-10-31T00:58:00 flask --app wsgi run --port 5001

# 5. Frontend, in a second terminal
cd frontend && npm install
DEMO_AUTH=1 npm run dev         # http://localhost:3000
```

- **Instead of the variables in step 4**, copy `.env.example` to `backend/.env`. It sets
  `DATA_DIR` and `DEMO_CLOCK`; uncomment `AUTH_DISABLED=1`, or set `CLERK_PUBLISHABLE_KEY`.
  Then run `flask --app wsgi run --port 5001`.
- **`DEMO_CLOCK`** freezes the request time inside the synthetic data, which ends on
  31 Oct 2026. Without it, requests use the real time and the last stock count, and the
  screens say how old that count is. Leave it unset in a real deployment.
- **Sign-in.** `DEMO_AUTH=1` gives local demo accounts that live only in your browser. It
  needs the API's `AUTH_DISABLED=1`, because no session token is sent. For real sign-in,
  set Clerk keys on both sides instead (see [frontend/README.md](frontend/README.md)).
- **Check the API:** `curl localhost:5001/api/ready` answers 200 once the engine data and
  yesterday's stock are loaded (503 until then). Swagger is at http://localhost:5001/api/docs.
- **Roles.** Pre-alerts and the results API are for network operators (the Clerk role
  `org:network_admin`); with `AUTH_DISABLED=1` the demo caller is an operator. The supplying site's
  steps (confirm, dispatch) are taken by the supplier, so a requesting hospital cannot record them
  without that role; see [backend/docs/api.md](backend/docs/api.md).

What you then see at http://localhost:3000:

1. **New request** (after you create a demo account): choose the requesting hospital from the
   dataset, then the patient group, units and longest wait. "Nearby sources" previews the
   ranking as you type; nothing is stored.
2. **Find sources** stores the request (`BDN-XXXXXXXX`) and opens **Results**: ranked sources
   on a schematic map, each with a most likely time, an 8-in-10 range and the engine's reasons,
   next to today's way (one quote, no range).
3. Pick a source, and **Track** follows the shelf check, dispatch and arrival, with the audit
   log. A demo button records the supplying site's steps.
4. **Pre-alerts** shows the evening list and **Evidence** the DS2 results, both from `results/`.

The static GitHub Pages build (`scripts/deploy-pages.sh`) has no API. It runs on fictional
demo data shaped like the engine's output, and its Evidence and Pre-alerts pages read the
committed `results/` files.

Tests: `cd backend && python -m pytest -q`. Real-data tests skip unless `DATA_DIR` is set.
Frontend: `cd frontend && npm test` (Node's built-in runner; checks the API adapter and the
workflow rules against the backend).

See [backend/README.md](backend/README.md) (endpoints, workflow, settings) and
[frontend/README.md](frontend/README.md) (screens, links, demo mode).

## Roadmap

1. Prevent shortages before they happen (pre-alerts).
2. Live national blood picture for the health ministry.
3. New country = new settings file, no rewrite.

## Team & ownership

| Role | Owns |
|---|---|
| Data scientist 1 | Ranking engine (Tue 18:00). Stretch: estimate today's centre stock |
| Data scientist 2 | Arrival ranges, replay ladder, pre-alert test, results JSON (ready 15:00) |
| Full-stack 1 | API, workflow, audit log, fallback, deployment |
| Full-stack 2 | SMS parser, settings file, demo clock, architecture diagram, standards table |
| Frontend | Screens, results tab, video script and recording |

See [CONTRIBUTING.md](CONTRIBUTING.md) for workflow.

## AI tools

Codex assisted with the DS2 arrival model, data cleaning, replay evaluation,
pre-alert tests, documentation and results artifacts. The numerical results come
from deterministic code operating on the synthetic starter dataset.

## License

MIT — see [LICENSE](LICENSE). Data is synthetic; nothing here describes real facilities.
