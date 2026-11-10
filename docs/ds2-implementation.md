# Data Scientist 2: implementation and expert-review guide

This contribution covers arrival ranges, an offline replay ladder, an evening
stock-alert evaluation, and reproducible JSON evidence. It follows the emergency
workflow in the project README. It does not dispatch blood or replace laboratory,
compatibility, quarantine, reserve, confirmation, or human-approval decisions.

## Run on Windows

Use Python 3.10 or later. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe scripts/evaluate_ds2.py
New-Item -ItemType Directory -Path .test-tmp -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest backend/tests --basetemp .test-tmp/tests -q
```

On this machine the installed Python 3.12 executable is
`C:\Users\beaut\AppData\Local\Programs\Python\Python312\python.exe`;
the unqualified `python` initially selected an older 3.8 environment.

The default source is `data/datasets terumo/`; override it with `--data-dir` or
`DATA_DIR`. Input data and cleaned copies are git-ignored. Original CSV files
are preserved. The evaluation first cleans all starter CSVs into `data/cleaned/`,
validates the core schema and foreign keys, then writes derived files to `results/`.
Use `--cleaned-dir` and `--output-dir` to isolate experiments. `--skip-cleaning`
explicitly bypasses cleaning for an already prepared source; schema validation
still runs and artifacts disclose that cleaning was skipped.

The raw starter dataset has 11 CSVs. Core evaluation reads facilities, routes,
requests, transfers and daily stock. Donor records and final-state unit location
are not arrival features or historical stock. The data dictionary's SQLite file
is absent from this download; CSV evaluation does not require it.

## Cleaning contract

The cleaning report records corrections, missing values, exclusions and file
checksums. Whitespace, known blood-group formatting, timestamp formatting and
facility display names are normalized using stable IDs. The three documented
temperature-sensor sentinel values are marked missing. Exact duplicate rows can
be removed; conflicting primary keys must be investigated. Potential donor
identity matches are flagged, never automatically merged.

Missing blood groups, missing transfer receipts and absent stock snapshots are
not guessed or filled with zero. Per-unit transfer rows remain per-unit records.
Unknown clinical facts and suspicious observations retain quality flags for
review. Missing receipt batches are excluded from timing-model training and
reported in exclusion counts. Cleaning does not grant clinical eligibility.

## Arrival model

The estimate runs from request submission to the receiving facility's arrival,
not crossmatched blood ready at the bedside. Transfers are per unit, so fitting
groups them by request and supplying source. A batch is usable only if every
recorded unit has valid timestamps, all receipts precede the fit cutoff, and a
positive route time exists. Completion is the latest receipt in that source's
recorded batch; it does not prove the whole original request was fulfilled.

For the last-arriving unit, retain its paired preparation wait and transit ratio:

```text
preparation = dispatched_at - requested_at
road multiplier = (received_at - dispatched_at) / typical_travel_hours
new-route duration = preparation + road multiplier * new_route_hours
```

The model evaluates every retained historical pair, then takes empirical
p10/p50/p90 quantiles. This is the deterministic full empirical distribution
rather than a finite Monte Carlo sample: no sampling noise or sample-count
tuning. The seed remains recorded for reproducibility. The distribution pools
routes because individual routes can be sparse. Quantity, route and hospital
workflow effects are not separately fitted. Hospital lending is explicitly
labelled extrapolation because there are no hospital-origin examples.

Default split (all timestamps EAT):

| Purpose | Period |
|---|---|
| Train | Before 1 July 2026 |
| Validation | 1 July to 1 September 2026 |
| Held-out test | 1 September to 1 November 2026 |

The same frozen model is used for validation and test. Receipt labels at or after
each cutoff are censored. No performance claim is made for missing/unconfirmed
batches. Report error, interval coverage and width together. p10–p90 is an
estimated **80%** interval; avoid the phrase “almost certainly.”

If the model is absent or has too few batches, use the configured fallback point
estimate, set `model_used=false`, and return null p10/p90 bounds. Do not render
null as zero. Invalid/missing routes remain unavailable instead of being treated
as zero-distance journeys.

Integration, with `backend/` on the Python import path:

```python
from engine.arrival import ArrivalModel, estimate_arrival

model = ArrivalModel.load("results/arrival_model.json")
window = estimate_arrival(
    route["typical_travel_hours"],
    model=model,
    settings=country_settings,  # Complete mapping, not just arrival subsection.
    source_kind="centre",      # Or hospital; adds an extrapolation warning.
)
```

The full signature and fallback contract are in `backend/engine/arrival/README.md`.

## Replay ladder and DS1 integration

The default replay is **independent-request snapshot feasibility**, not a full
inventory simulation. It evaluates emergency RBC requests with known group and
insufficient exact-match stock in the requester's previous-day snapshot. It does
not use the future `units_from_local_stock` outcome to decide eligibility.

1. Baseline: supply centre, then two nearest regional centres by road distance.
2. All regional centres.
3. Centres plus explicitly eligible hospital lenders.

The replay keeps this two-neighbour baseline. The live engine's baseline (spec
section 8, decided 2026-11-10) goes on to the nearest regional centre with
enough stock, so the app's "today's way" can name a centre this baseline skips.

The reference provider uses exact component and group only. It excludes satellites
and the requesting site. No whole-blood pooling or compatibility substitution is
implemented here. Unknown groups are excluded with a human-review reason. This
comparator is conservative and will not reproduce a broader compatible-group
analysis such as the original exploratory “290” claim.

Hospital lending is off in the reference comparator without explicit experimental
reserves. A research scenario can be run separately:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_ds2.py --hospital-reserve-units 5 --output-dir results/hospital-reserve-5
```

This reserve value is an assumption for sensitivity testing, not an approved
clinical threshold. Reference O-negative lending stays excluded. Changing live
lending or group rules still belongs to the reviewed production engine.

Use `candidate_provider` in `run_replay()` to evaluate DS1's real eligibility and
stock rules. The adapter contract is:

```python
def provider(request, as_of, *, include_hospitals):
    # Call DS1 with its agreed request/context contract. Return ALL eligible
    # sources, not just the top-N already ranked options.
    return [
        Candidate(
            facility_id=option["facility_id"],
            available_units=option["spare_units"],
            travel_hours=option["travel_hours"],
            road_km=option["road_km"],
            source_kind=option["source_kind"],
        )
        for option in approved_options
    ]
```

`approved_options` above stands for DS1's output; field mapping is intentionally
isolated in the adapter. `DS1CandidateProvider` implements this contract with
DS1's rules (see "DS1 provider run" below).
The replay filters this complete candidate set into the three policies. It uses
the same arrival estimator for fair policy comparisons and separately reports
the baseline's map-plus-two quote. A full source must cover the entire requested
quantity; partial stock is counted separately. Time savings are paired on the
same requests, rather than subtracting means from different fulfilled cohorts.

Stocks are reused between independent requests. Thus counts are **opportunities**,
not additional unique patients served. No stock depletion, confirmation failure,
transport capacity, expiry/quarantine reconstruction or split-source fulfilment
is simulated. The starter's stock reconstruction uses transfer dispatch dates,
which also makes snapshots approximate. A stateful inventory simulation is still
needed before claiming aggregate additional deliveries; the DS1 provider run
below changes which sources count, not this.

### DS1 provider run

`DS1CandidateProvider` (`backend/engine/replay/ds1_provider.py`) calls DS1's
`engine.stock.candidates` unchanged. It returns every site with spare compatible
units and a route to the requester, not DS1's top few, and never the requester or
a satellite. Run it with:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_ds2.py --candidate-provider ds1 --engine-country kenya
```

`--engine-country` (default `kenya`) picks DS1's settings file
`backend/config/<country>.yaml`. Output goes to `results/ds1-provider/` unless
`--output-dir` is given, so the committed `results/` are never overwritten. The run
builds DS1's SQLite from the same CSV folder the replay reads (the cleaned folder,
or `--data-dir` with `--skip-cleaning`) in a temporary folder; `data/blood.db` and
`ENGINE_DB_PATH` are not touched. `replay_summary.json` records
`candidate_provider: "DS1CandidateProvider"`, and `settings.ds1_engine` records
DS1's `country`, `sharing_allowed`, `min_keep` and `o_neg_reserve` (covered by
`settings_sha256`). Nothing from a DS1 run is committed yet. Once `results/ds1-provider/`
exists where the API runs (generated or committed), `GET /api/results` lists it as a
scenario and the Evidence page labels it "DS1 rules"; the static demo build offers only
the two hospital-reserve scenarios.

How it differs from the reference provider:

- Compatible groups come from the fixed table: an O+ patient counts O+ and O- units.
- RBC and WB are pooled as red cell supply.
- Hospitals keep max(usual level, `min_keep`) per group and never lend O- below
  `o_neg_reserve`; regional centres lend everything.
- DS1's `sharing_allowed` decides hospital lending. The script folds DS2's
  `lending.enabled` into it, which must be a YAML boolean (a quoted `"false"` is
  refused).

The run stops with exit 1 rather than ignore a setting it cannot honour: hospital
reserves (`--hospital-reserve-units` or `replay.hospital_reserve_units`),
`replay.components` other than `[RBC]`, and a DS1 settings file with a nonzero
`hospital_extra_dispatch_h` (use `backend/scripts/sensitivity.py` for that
question). It also exits 1, with the reason, if DS1's data checks reject the
CSVs. From Python, the provider raises `ValueError` for a non-RBC request and
reads no DS2 settings, so fold `lending.enabled` into `sharing_allowed`
yourself, as the script does.

Caveats (the artifacts list them too):

- Requests are still selected by the requester's prior-day exact-match
  snapshot, so both providers are compared on the same requests.
- Every source is timed by this replay's arrival estimator against
  `replay.deadline_hours`, with no extra hospital dispatch delay; the baseline
  quote stays map + 2 h. DS1's ETA model and its `clinician_limit_h` and
  `baseline_quote_extra_h` are not used.
- `usual_level` is a median over the whole year, so the replay sees some later
  information.
- Counts are still opportunities, not unique patients served, and hospital
  lending is still an unobserved assumption.

## Evening alert test

At the configured evening hour, generate component-specific zero-stock review
alerts using the exact previous day's closing stock. Default O+ RBC and WB
are evaluated separately, not pooled. Missing series remain unknown; the starter
generator omits some series that were always zero, which limits coverage.

Evaluate complete next-24-hour windows against exact group/component emergency
or urgent requests receiving fewer units than requested. Precision uses alerts
as its denominator; recall uses eligible unmet requests. Both denominators,
missing-stock exclusions and censored last windows are included in JSON. This
measures association with later unmet demand, not whether replenishment would
prevent a shortage. A zero RBC alert does not say all red-cell options are absent.

The simple zero-stock rule has low precision on the held-out data. Show its
alert burden and recall together; it needs expert review before operational use.

## JSON files for the frontend

| File | `result` payload |
|---|---|
| `data_quality.json` | Cleaning report and provenance |
| `arrival_model.json` | Serializable model; `ArrivalModel.load` accepts the envelope |
| `arrival_validation.json` | `validation` and `test` metrics/exclusions |
| `replay_summary.json` | `policies`, cohort, paired comparison and assumptions |
| `prealert_evaluation.json` | Alert metrics, denominators and censoring |
| `prealerts.json` | Facility-level review alerts and missing snapshots |
| `summary.json` | Compact metrics for the results tab |

The API serves every file except `arrival_model.json`: `prealerts.json` through
`GET /api/prealerts`, the others through `GET /api/results/<name>`.

Every envelope includes schema version, generated time, synthetic-data flag,
input file hashes, settings and their hash, split and seed. JSON serialization
rejects NaN/Infinity; missing values are null. Each file is replaced atomically.
Files contain aggregate results and model parameters, not raw patient/donor rows.

## Measured starter-data results

The checked run trains on 1,762 completed source-request batches and tests on 438
later completed batches. Test mean absolute arrival error is **0.890 hours**, versus
**1.333 hours** for map time plus two hours. The estimated 80% interval covers
**80.82%** of test arrivals, with a mean width of **3.03 hours**. These figures
apply only to observed completed batches, not unconfirmed deliveries.

Replay uses the same 370 eligible September–October requests in each scenario:

| Scenario | Full-source opportunities with p50 within 6h | With p90 within 6h |
|---|---:|---:|
| Existing centre-search baseline | 141 | 132 |
| All centres | 141 | 135 |
| Hospitals with assumed reserve 5 | 292 | 283 |
| Hospitals with assumed reserve 10 | 269 | 260 |

The default has no assumed hospital reserve, so its hospital stage equals the
all-centres stage. Additional scenario artifacts live in
`results/hospital-reserve-5/` and `results/hospital-reserve-10/`. These are
independent-request opportunities with the limitations above, not actual or
inventory-constrained additional deliveries.

The evening O+ rule, RBC/WB independently, produces 1,557 evaluated alerts in 60
complete windows. Of these, 47 precede matching unmet demand: **3.02% precision**.
It detects 56 of 57 eligible unmet requests: **98.25% recall**. Missing snapshots
exclude another 29 unmet requests. This is evidence of a noisy review rule, not
proof of useful preventive replenishment.

Cleaning canonicalizes 1,314 request display names and blanks 55 documented
temperature glitches actually present in the download. It flags 904 donor records
for possible identity duplication, 102 short donation intervals, 506 missing donor
groups, 442 unknown request groups and 1,046 missing transfer receipts. No donor
identities are merged and no unknown group or receipt is invented.

## Expert discussion and remaining team work

- Are request-to-receipt and bedside readiness being distinguished correctly?
- What extra confirmation/preparation delay should hospital lending assume?
- What reserve rules can the production provider safely expose?
- How should stale snapshots and unavailable confirmations affect the workflow?
- Can a more selective alert rule reduce false alarms while retaining recall?

Wired into the app now: `GET /api/results` lists the result files and scenario
folders, `GET /api/results/<name>?scenario=<folder>` returns one file's envelope
unchanged, and `GET /api/prealerts` serves `results/prealerts.json` with facility
names added. The web app's Evidence page (`/evidence`) and Pre-alerts page
(`/prealerts`) read them; the static demo build reads the same committed files.
Not wired yet: the API does not generate pre-alerts at the evening hour (it
serves the list `scripts/evaluate_ds2.py` last wrote), and there is no stateful
replay. The live ranking's arrival ranges come from DS1's model
(`backend/engine/eta.py`, fitted by `backend/scripts/fit_eta.py`); `engine.arrival`
serves the replay and this evaluation. DS1 supplies reviewed compatibility/stock
candidate selection. Tests and the offline pipeline do not establish real-world
clinical validity.

AI tool disclosure: Codex assisted with DS2 code, tests, documentation and evaluation.
