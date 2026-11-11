# Damu Dispatch: finds the nearest site that can safely spare blood for an emergency, with an honest arrival time

Terumo BCT Africa Hackathon 2026 · Challenge area: **Emergency request and dispatch**

Project: Blood Dispatch Network. Lets a hospital lab worker facing a night-time emergency
find the nearest site that can safely spare compatible blood, with an honest arrival time,
on the web or by SMS.

## The problem

**The user:** the lab worker at a county or private hospital who runs out of a blood group
during an emergency, often at night. Some of these sites have 2G only and unreliable power.

**What they do today:** check the fridge, then phone the regional blood centre, because that
is the only route. The centre packs and drives. The quote is "map time plus about 2 hours",
with no range.

**Where it goes wrong:** nobody can see that a hospital 30 minutes away holds spare units of
that group, and the quote has no range, so the clinician cannot plan.

From the starter dataset (Kenya, 1 Nov 2025 to 31 Oct 2026, 47 facilities):

| What | Number |
|---|---|
| Emergency requests in the year | 8,768 |
| Emergency requests made between 20:00 and 06:00 | 41% |
| Emergency deliveries that arrived later than today's quote (map time + 2 h) | 67% of 5,170 |
| Emergency deliveries that took over 6 hours | 34% |
| Median time from request to arrival, against map driving time | 4.7 h vs 2.1 h |
| Emergency red-cell requests where a hospital within 2 h could spare enough (yesterday's count) | 55% |
| Emergency requests unfilled / partly filled | 625 / 101 |
| Units that expired on shelves in the same year | 7,173 (15%) |

## What we built

**What works now**
- The full request workflow with two user roles and the audit log:
  1. The lab worker enters a request (blood group, units, longest safe wait).
  2. The engine ranks the sources, each with an arrival range and plain reasons, next to
     today's rule.
  3. The lab worker picks, changes or rejects.
  4. The supplying site confirms the units are on the shelf, then dispatches.
  5. Tracking shows each step until arrival.
- If there is no shelf confirmation within 10 minutes, the request times out and moves to
  the next source.
- Every step is recorded in an append-only audit log: who, when and what.
- **SMS from a basic phone** through Africa's Talking (sandbox). Commands: `REQUEST`,
  `STATUS`, `PICK`, `CONFIRM`, `REJECT` and `DISPATCH`. A repeated message is recognised by
  its ID and never entered twice.
- **Evening pre-alerts:** a list of hospitals that have run out of common groups, so the
  centre can top them up before the night.
- **Evidence page:** the replay and arrival-model results from `results/`.
- Sign-in with roles (hospital, supplying site, network operator) through Clerk. Each
  hospital sees only its own requests.
- **Fallback:** if the API or the engine is down, the web app shows a banner for the phone
  process.

SMS is implemented: a basic phone receives three ranked sites with arrival ranges
and today's baseline; staff reply `1`/`2`/`3`, `STATUS`, or `CANCEL`. Suppliers reply
`YES`, `NO`, then `SENT`. The transactional outbox, retries, delivery reports and
signed gateway remain in place. For the video, use the [sandbox simulator and tunnel walkthrough](backend/docs/sms.md#video-demo-sandbox-simulator-and-tunnel)
with two pre-registered demo phones; a live shortcode is not required.

**What is mocked or not finished**
- Stock is yesterday's closing count from the dataset, not a live feed.
- The dataset has no hospital-to-hospital lending, so hospital dispatch times are assumed
  from regional centre data. Our result still holds with hospitals up to 3 h slower.
- The public live demo runs on fictional sample data in the engine's output shape. The real
  engine runs when you start the API locally (see How to run it).
- SMS runs in the Africa's Talking sandbox, not on a live shortcode.

**Stack:** Nuxt 4 (frontend) · Flask (backend API) · Python decision engine · SQLite · SMS gateway · CSV in, JSON out.

Demo video (3 minutes or less): `[[link]]`

Live demo: https://sharlmon.github.io/blood-dispatch-network/ · Test log-in: create any
demo account on the sign-in page. It is stored only in your browser, and no password is
checked.

Hosted API docs (Swagger): https://blood-dispatch-api.onrender.com/api/docs. The API is on
Render's free plan, so the first request after a quiet spell can take about a minute. Its
engine data is not loaded yet, so ranking runs only locally for now.

## How to run it

You need Python 3.11+, Node 22+ and the hackathon starter kit CSVs. Run these commands from
the repo root.

```bash
# 1. Data: unzip the starter kit's CSVs into data/ (git-ignored). The kit's README.md
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
DATA_DIR=data AUTH_DISABLED=1 DEMO_CLOCK=2026-10-31T00:58:00 flask --app wsgi ingest-data
DATA_DIR=data AUTH_DISABLED=1 DEMO_CLOCK=2026-10-31T00:58:00 flask --app wsgi run --port 5001

# 5. Frontend, in a second terminal
cd frontend && npm install
DEMO_AUTH=1 npm run dev         # http://localhost:3000
```

Check the API: `curl localhost:5001/api/ready` returns 200 once the engine data and
yesterday's stock are loaded, and 503 until then. Swagger is at
http://localhost:5001/api/docs.

**What to click**
1. Create a demo account, then open **New request**.
2. Choose the requesting hospital, then the patient's blood group, the units and the longest
   safe wait.
3. **Find sources** stores the request and opens **Results**. Each ranked source shows its
   most likely time, its 8-in-10 range and the engine's reasons, next to today's way.
4. Pick a source. **Track** follows the shelf check, dispatch and arrival, with the audit
   log. A demo button records the supplying site's steps.
5. **Pre-alerts** shows the evening list, and **Evidence** shows the results.

**Settings and tests**
- `DEMO_CLOCK` freezes the request time inside the synthetic data, which ends on 31 Oct 2026.
- Instead of setting variables in step 4, you can copy `.env.example` to `backend/.env`.
- Tests: `cd backend && python -m pytest -q`, and `cd frontend && npm test`.

More detail: [backend/README.md](backend/README.md), [backend/docs/api.md](backend/docs/api.md)
and [frontend/README.md](frontend/README.md).

## Architecture

Full diagrams (whole system, emergency request, evening pre-alert, ranking engine):
[docs/architecture/README.md](docs/architecture/README.md).

```
 Lab worker ──► Web app (Nuxt) ─────────────────┐
 Basic phone ─► SMS (Africa's Talking) ─────────┤
                                                ▼
 CSVs ─► Ingest (checked) ─► SQLite ─► Flask API ── Workflow ── Audit log
                               │          │        (request → pick → confirm → dispatch)
                               │          │        Fallback banner (phone process)
                               ▼          ▼
              Decision engine (deterministic, no language model)
              ├─ Ranking: compatible spare units above safety stock
              ├─ Arrival ranges: p10 / p50 / p90
              ├─ Evening pre-alert: hospitals out of common groups
              └─ Replay: reruns past requests ─► results/*.json ─► Evidence page

 Country settings file (lending rules, safety stock, time limits, demo clock)
```

**Stack:** Nuxt 4, Flask (Python), Python decision engine (pandas, numpy), SQLite, Clerk
sign-in, Africa's Talking SMS. Hosted on GitHub Pages (web) and Render (API).

**Where it sits in a wider blood-bank information system:** this is the Emergency request
and dispatch module.
- It reads each site's daily stock and unit expiry, and writes requests, transfers and audit
  events back.
- It links to Stock-out early warning through the evening pre-alerts.
- It links to Redistribution: when two sites tie, the one with units near expiry goes first.

**Standards:** none implemented yet. The data model is designed to map to HL7 FHIR
(SupplyRequest, SupplyDelivery, BiologicallyDerivedProduct) and ISBT 128 unit IDs.

**Security:**
- Roles separate hospital, supplying site and network operator.
- Each hospital sees only its own requests.
- The audit log is append-only.
- No patient name or ID is collected.
- SMS webhooks are signed, and raw phone numbers are kept out of the audit log.
- Kenya Data Protection Act mapping: [docs/DATA_PROTECTION.md](docs/DATA_PROTECTION.md).

## AI and data

- **What the AI or data feature does:** ranks the nearby sites that can safely supply the
  request, and gives each one an arrival range.
  - **Rules decide who can safely give:** a fixed compatibility table, never a model.
    Hospitals lend only above their own safety stock, and an O-negative reserve is protected.
  - **The arrival model gives each option a range:** it is learned from 3,541 past
    emergency deliveries and gives p10, p50 and p90.
  - Spec: [docs/RANKING_ENGINE_SPEC.md](docs/RANKING_ENGINE_SPEC.md). Code: `backend/engine/`.
- **Baseline we compared against:** today's rule, which picks the regional centre and quotes
  map time + 2 h, with no range.
- **Result:** we measured the typical arrival-time error (mean absolute error) on 1,734
  held-out emergency deliveries from Jul–Oct 2026. The model trained only on earlier data.

  | | Typical error |
  |---|---|
  | Today's quote (map time + 2 h) | 1.17 h |
  | **Our model** | **0.95 h** |
  | Remote hospitals, map time 5 h+: today's quote | 2.75 h |
  | Remote hospitals, map time 5 h+: our model | 1.76 h |
  | Independent check, 438 deliveries, Sep–Oct 2026: today's quote | 1.33 h |
  | Independent check, 438 deliveries, Sep–Oct 2026: second model | 0.89 h |

  80% of real arrivals fell inside our 8-in-10 range, and coverage stays between 77% and 82%
  in every distance band and for 2G sites.

  The independent check is a separate evaluation by our second data scientist. It has its
  own cleaning, its own model and a later test period, and 81% of arrivals fell inside its
  range. It is not the model the ranking uses, but it reaches the same conclusion: both
  models beat today's quote. Its details are in
  [docs/ds2-implementation.md](docs/ds2-implementation.md) and `results/`, and the
  **Evidence** page shows it.
- **How a user sees the reason for a recommendation:** plain-language reasons built from
  templates filled with computed numbers. For example: *"22 spare compatible units above its
  own safety stock (yesterday's count). Most likely 2.6 h; 8 in 10 arrive within 1.4–3.8 h.
  14 units expire within 10 days."* No language model writes any number or reason.
- **Who approves it (Accept / Change / Reject):** the lab worker picks a source, picks a
  different one, or rejects them all. The supplying site confirms its shelf. A qualified
  person crossmatches and releases every unit. Every step goes in the audit log.
- **What happens if the AI is wrong or offline:**
  - The screen falls back to today's rule (nearest regional centre) and the phone process.
  - If even the best option's p90 is over the clinician's time limit, the tool says so, so
    they can act now (emergency group O, or transfer the patient).
  - If the arrival model file is missing, a simpler estimate is used and marked as such.

## Data

- **Starter dataset tables used:** `facilities`, `routes`, `daily_stock`, `units`,
  `requests` and `transfers`. They are loaded from CSV and checked on the way in (see
  `backend/engine/cleaning.py`).
- No other data. Everything is synthetic, and there is no real donor, patient or facility
  data.
- The public demo uses fictional sample data generated in `frontend/app/utils/mock.ts`.

## African conditions

- **Connectivity:** a basic phone can request and confirm by SMS. Repeated messages are
  recognised by ID, so nothing is entered twice. If the tool is down, the phone process
  still works.
- **Power:** when arrival times tie, sites with backup power rank first. Stock counts show
  their age, so a count that is out of date is visible.
- **Paper and spreadsheets:** stock counts and unit lists load from CSV and are checked on
  load.
- **Another site or country:** a new settings file, with no code change. It covers lending
  rules, safety stock, the O-negative reserve and time limits. See
  `backend/config/kenya.yaml` and `backend/config/settings.default.yaml`.
- **Languages:** English only for now.

## AI tools we used

| Tool | What for |
|---|---|
| Claude Code (Anthropic) | Ranking engine code and tests, engine spec, documentation, pitch deck text |
| Codex (OpenAI) | Data-science arrival model, data cleaning, replay evaluation, pre-alert tests, results files, documentation |

The numerical results come from deterministic code running on the synthetic starter
dataset. Every team member can explain the part they built.

## Team

| Name | Role | Country | Presenting Friday (in person / online) |
|------|------|---------|-----------------------------------------|
| Sheila Mumbi Macharia | Data scientist: ranking engine (compatibility, safe lending, arrival ranges, reasons) | Kenya | In person |
| Graham Akello | Data scientist: data cleaning, arrival replay, pre-alert evaluation, evidence results | Kenya | In person |
| Rovenel Abanga | Full-stack: API, request workflow, audit log, engine integration | Kenya | In person |
| Thomas Muia | Full-stack: SMS with Africa's Talking, settings, deployment and operations | Kenya | In person |
| Sharlmon Junior | Frontend: web screens, map, accessibility, demo video | Kenya | In person |

See [CONTRIBUTING.md](CONTRIBUTING.md) for how we worked.

## Known limits and next steps

**Known limits**
- Stock is yesterday's count, so a source may no longer have the units. That is why the
  supplying site confirms the shelf before dispatch.
- Hospital lending times are assumed, because the dataset has no hospital-to-hospital
  transfers.
- The hosted API on Render is not loaded with data yet, so the live site runs on sample data.
- No FHIR or ISBT 128 interface is built yet. These are mappings only.

**Next steps**
- **3 months, MVP:** a live stock feed from one regional centre, confirmed shelf counts, an
  SMS shortcode and data protection registration.
- **6 months, controlled pilot:** one regional centre and 8–10 hospitals around it. We would
  measure time from request to arrival, the share of requests filled, and units expired.
- **What we need:** a pilot with one regional blood transfusion centre and the hospitals
  around it, with access to their anonymised daily stock data.

## License

MIT, see [LICENSE](LICENSE). The data is synthetic, and nothing here describes real
facilities.
