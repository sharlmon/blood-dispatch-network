# Data protection

How the Blood Dispatch Network handles personal and health data, mapped to Kenya's Data
Protection Act 2019 (KDPA). The hackathon build runs on **synthetic data only**. This note
covers what the design already does and what an operator must do before real use.
It is not legal advice; section numbers should be checked with the ODPC guidance.

## What data the system touches

| Data | Where it comes from | Used by | Personal? | Kept where |
|---|---|---|---|---|
| Facility stock, routes, units, transfers | Blood service records | Ranking engine, pre-alert, replay | No | `blood.db` (SQLite) |
| Emergency request: facility, blood group, units, time, urgency | Hospital lab worker (web or SMS) | Ranking engine | Health data, **no patient identifier** | `blood.db`, audit log |
| Patient sex, age band, clinical indication | Requests CSV | **Not stored by the engine** (dropped at load; tested) | Health data | Not in `blood.db` |
| Donor records (sex, birth date, county, last 4 phone digits) | Donors CSV | DS2 data-quality checks only; identities never merged | Yes | Not used by ranking or the API |
| Staff identity and role | Clerk login | API auth, audit log | Yes | Clerk (US), audit log |
| Phone number of SMS sender | SMS gateway | SMS parser, reply | Yes | Gateway, audit log |

Committed outputs (`results/`, `backend/engine/examples/`) hold no personal fields.

## Already built in

| KDPA area | What the design does |
|---|---|
| Data minimisation (s.25) | The engine keeps only seven request columns; no patient name or ID is ever asked for. `tests/test_load.py::test_db_keeps_no_patient_details` |
| Automated decisions (s.35) | The engine only suggests. A person picks the source, the supplying site confirms, a qualified person crossmatches and releases every unit |
| Explainability | Reasons are fixed templates filled with computed numbers; every arrival time has a range; no LLM produces any number |
| Accuracy and fairness | Compatibility is a fixed table. Arrival ranges checked per distance band and for 2G sites: 77-82% of arrivals inside the range in every group (`scripts/fit_eta.py`) |
| Access control | Clerk sessions verified server-side; organisation role on every request |
| Accountability | Audit log records request, decision, confirmation, dispatch and timeout |
| Resilience | If the tool fails, everyone falls back to the phone process |

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
6. **Breach plan.** A processor tells the controller within 48 h; the controller tells the
   ODPC within 72 h (s.43). Name who calls whom.
7. **Notices and rights.** A short privacy notice for staff users, and a way to handle
   access or correction requests. Patients are not identifiable in the tool.
8. **Keep checking fairness.** Re-run `fit_eta.py` on live data and watch the per-group table.
