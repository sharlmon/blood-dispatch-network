# Data protection

How the Blood Dispatch Network handles personal and health data, mapped to Kenya's Data
Protection Act 2019 (KDPA). The hackathon build runs on **synthetic data only**. This note
covers what the design already does and what an operator must do before real use.
It is not legal advice; section numbers should be checked with the ODPC guidance.

## What data the system touches

| Data | Where it comes from | Used by | Personal? | Kept where |
|---|---|---|---|---|
| Facility stock, routes, units, transfers | Blood service records | Ranking engine, pre-alert, replay | No | `blood.db` (SQLite) |
| Emergency request: facility, blood group, units, component, time limit, request time, status, selected site, the ranking shown | Hospital lab worker (web or SMS) | Ranking engine, workflow | Health data, **no patient identifier** | The API's own SQLite (`DB_PATH`, default `data/blood.sqlite`), `requests` table |
| Audit trail: action, time, staff user id, organisation id and role, step details (sites, statuses, minutes waited) | Every request and workflow step | Accountability | Yes (staff ids) | Same file, `audit` table |
| Past requests: id, facility, time, blood group, component, units, urgency | Requests CSV | Ranking engine (arrival fit, CLI) | Health data, **no patient identifier** | `blood.db` |
| Patient sex, age band, clinical indication | Requests CSV | **Not stored by the engine** (dropped at load; tested) | Health data | Not in `blood.db`; DS2's cleaned copy (`data/cleaned/`, git-ignored) keeps all columns |
| Donor records (sex, birth date, county, last 4 phone digits) | Donors CSV | DS2 data-quality checks only; identities never merged | Yes | `data/` and `data/cleaned/` (git-ignored); not used by ranking or the API |
| Staff identity and role | Clerk login | API auth, request ownership, audit log | Yes | Clerk (US). The API's SQLite keeps only Clerk ids and the role, no names or emails |
| Local demo account: name, email, hospital, role | Typed in by the user (`DEMO_AUTH=1` or the static demo only) | Header and greeting | Yes | That browser's localStorage only; never sent to the API |
| Phone number of SMS sender | SMS gateway | SMS parser, reply | Yes | Private sender configuration, gateway, SMS outbox |

The request store keeps exactly: the request id and creation time, facility id and name, blood
group, units, component, the clinician's time limit, request time, status, the selected site,
the ranking shown (the API's full answer), and the staff user and organisation ids. The audit
adds the staff role. Fields the API does not know, such as a patient name, ID or clinical note,
are dropped and never stored or echoed, and there is no free-text field
(`backend/tests/test_api_workflow.py::test_extra_fields_are_never_stored` scans the SQLite file).

Committed outputs (`results/`, `backend/engine/examples/`) hold no personal fields.

## Already built in

| KDPA area | What the design does |
|---|---|
| Data minimisation (s.25) | The engine keeps only seven request columns; no patient name or ID is ever asked for. `tests/test_load.py::test_db_keeps_no_patient_details`. The API's request store keeps only the fields above and drops anything else (`tests/test_api_workflow.py::test_extra_fields_are_never_stored`) |
| Automated decisions (s.35) | The engine only suggests. A person picks the source, the supplying site confirms, a qualified person crossmatches and releases every unit |
| Explainability | Reasons are fixed templates filled with computed numbers; every arrival time has a range; no LLM produces any number |
| Accuracy and fairness | Compatibility is a fixed table. Arrival ranges checked per distance band and for 2G sites: 77-82% of arrivals inside the range in every group (`scripts/fit_eta.py`) |
| Access control | Clerk sessions verified server-side (`backend/app/clerk_auth.py`). Every request endpoint needs a hospital (a Clerk organisation), and a request is visible only to the organisation that made it. `AUTH_DISABLED=1` is a local-demo switch only |
| Accountability | The audit log is built: the `audit` table in the API's SQLite (`DB_PATH`) records every request and step (request, pick, shelf confirmed, dispatched, arrived, not on shelf, confirmation timeout, emergency group O, patient transfer, cancel) with the staff user id, organisation id and role, the time in East Africa Time, and the step details. No free text. The API only adds entries; no endpoint changes or deletes them |
| Resilience | If the tool fails, everyone falls back to the phone process; the web app shows a phone-process banner when the API or the engine is down |

## Implemented SMS handling

SMS is built: registered staff can request ranked options, choose a site and confirm
or dispatch using short replies. Messages include facility names, blood group,
unit count and arrival estimates, without patient identifiers. The supplier needs
the group and quantity to check stock. Staff must still crossmatch and release units.

Sender authorization is facility scoped. The signed gateway verifies HMAC timestamps;
Africa's Talking callbacks use a separate secret bearer token over HTTPS. Committed
outbox records support delivery reports and controlled retries. Raw phone numbers
and incoming texts are not logged in the workflow audit; SMS actors are keyed hashes.
The private sender configuration and outbox contain phone numbers, and outbox bodies
contain request details. Restrict their access and backups and set a retention policy
before sustained use. Never log callback query strings or expose tunnel inspectors.

The [video walkthrough](../backend/docs/sms.md#video-demo-sandbox-simulator-and-tunnel)
uses synthetic stock and two sandbox simulator phones, rather than real handset
traffic. Its sender registrations are demo identities, not staff identity records.

## Lawful basis

- **Controller:** the blood service and the hospitals that use the tool. The software
  team would be a processor.
- **Health data (s.46):** handled by or under the responsibility of a healthcare provider.
- **Purpose:** emergency blood supply. The basis is a public task or a patient's vital
  interests, not consent; there is no consent log for patients.
- **Staff data:** needed to run the service and keep the audit trail.

## Before real use (operator's checklist)

1. **Register with the ODPC.** Health-sector controllers and processors register regardless of size.
2. **DPIA (s.31).** Health data at scale triggers one. This note and the data map above are its starting point.
3. **Processor agreements** with the hosting provider, the SMS gateway and Clerk.
4. **Hosting and transfers.** Host the database in Kenya. Clerk stores staff logins in the
   US: cover it with a transfer agreement (s.48-50) or replace it with a locally hosted
   login. Health may count as "strategic interest" data needing a local copy (2021 regulations).
5. **Security.** Encrypt data at rest and in transit, keep role-based access, and review the audit log.
   Today the API's SQLite file is not encrypted and nothing is ever deleted from it: set a
   retention period. Any hospital organisation can file a request for any facility: tie each
   organisation to its facility.
6. **Breach plan.** A processor tells the controller within 48 h; the controller tells the
   ODPC within 72 h (s.43). Name who calls whom.
7. **Notices and rights.** A short privacy notice for staff users, and a way to handle
   access or correction requests. Patients are not identifiable in the tool.
8. **Keep checking fairness.** Re-run `fit_eta.py` on live data and watch the per-group table.
