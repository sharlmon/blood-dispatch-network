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
hospital lending remains an unobserved assumption.

## Architecture

**Stack:** Nuxt 4 (frontend) · Flask (backend API) · Python decision engine · SQLite · SMS gateway · CSV in, JSON out.

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
| Clients | Web screens | Frontend | Request entry, options list, confirmation, pre-alert list |
| Clients | SMS parser | Full-stack 2 | Turns text messages into structured requests |
| Clients | Results tab | Frontend | Shows replay outputs from `results/*.json` |
| Backend | HTTP API | Full-stack 1 | Serves web clients, triggers the evening run |
| Backend | Workflow | Full-stack 1 | Request, pick, confirm, dispatch; no confirmation in time moves to the next option |
| Backend | Audit log | Full-stack 1 | Records every request, decision, confirmation, dispatch and timeout |
| Backend | Fallback mode | Full-stack 1 | Switches to the phone process if the tool is down |
| Engine | Ranking (`rank_sources()`) | Data scientist 1 | Compatible spare units above safety stock |
| Engine | Arrival ranges | Data scientist 2 | p10 / p50 / p90 arrival estimates |
| Engine | Evening pre-alert | Data scientist 2 | Hospitals out of common groups, from yesterday's closing stock |
| Engine | Replay | Data scientist 2 | Reruns past requests, writes results JSON |
| Data | Ingest | Full-stack 2 | Loads starter CSVs (git-ignored `DATA_DIR`) into SQLite |
| Data | Country settings | Full-stack 2 | Per-country YAML config |

### Emergency request sequence

1. The lab worker submits a request by web or SMS; the API logs it.
2. The API calls `rank_sources`, which returns ranked options with ranges and reasons, plus a baseline.
3. If the top option's p90 exceeds the clinician's time limit, the tool advises considering emergency group O or patient transfer.
4. The lab worker sees the options and the baseline side by side, then picks, changes or rejects.
5. The supplying site confirms the units are on the shelf, then dispatches. No confirmation in time moves the request to the next option.
6. The arrival window goes back to the lab worker. Every step is logged.

### Ranking engine (`rank_sources()`)

- **Compatibility** (`compat.py`): fixed lookup table, never a model. Unknown group falls back to O- and O+ only, with a flag.
- **As-of date:** request date minus one day, so stock is yesterday's closing count.
- **Candidates:** all facilities except the requester and `SAT-*` satellites; centres only if `sharing_allowed` is false.
- **Spare stock** (`stock.py`): centres offer all compatible red cells and whole blood; hospitals offer stock minus the higher of usual level and minimum keep; O- never drops below the O- reserve; near-expiry units are capped at the spare count.
- **Arrival time** (`eta.py`): fixed-seed Monte Carlo of wait + extra time + ratio x travel hours gives p10/p50/p90. Without a model file it uses a simpler estimate and sets `model_used` to false.
- **Sorting** (`rank.py`): p50 in quarter-hour buckets, then near-expiry first, backup power first, most spare units.
- **Full vs partial:** if no candidate covers the request, returns best partial options with a `no_full_source` advice.
- **Baseline:** today's rule (also the fallback): supply centre if it has enough, otherwise the two nearest regional centres by road distance; quote is map time plus two hours, no range.
- **Reasons** (`reasons.py`): string templates filled with computed numbers.

## Repo structure

```
.
├── frontend/   Nuxt 4: pages, components, results tab
├── backend/    Flask
│   ├── app/        Flask app factory and routes
│   ├── db/         CSV ingest, SQLite schema
│   ├── api/        API modules
│   ├── workflow/   request flow, audit log, fallback
│   ├── engine/     ranking, arrival, replay, prealert
│   ├── sms/        SMS parser
│   ├── config/     country settings, demo clock
│   └── tests/
├── docs/       architecture diagram, standards table, video script
├── results/    replay results JSON for the expert review
├── data/       dataset (git-ignored)
└── scripts/    tooling
```

## Quick start

```bash
# backend
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && flask --app wsgi run --debug --port 5001
# frontend (Node 22+)
cd frontend && npm install && npm run dev
```

See [backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md) for per-folder ownership.

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
