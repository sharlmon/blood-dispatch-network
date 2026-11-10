# Ranking engine spec: "Nearest Blood, Honest Time"

Terumo BCT Africa Hackathon 2026 · Challenge area: Emergency request and dispatch.
Owner: Data scientist 1. Target: working engine plus tests by **Tue 18:00 EAT**.

## 1. What this engine is for

When a hospital's fridge can't cover an emergency red cell request, the engine:

1. finds every regional centre or hospital that can **spare** compatible units,
2. ranks them by an **honest arrival range** (most likely time plus an 80% window),
3. returns plain-language reasons and safety flags as JSON.

The API, the screens and the SMS panel (built by teammates) call it. It is a plain
Python package with no web code inside. Teammates build against the JSON contract in
section 9, so keep that contract stable.

## 2. Hackathon rules the code must respect

- All code is written now, during the build window. Do not paste in code from elsewhere.
  Open-source libraries are fine.
- Commit after each working step, with clear messages. One big commit at the end gets
  checked closely.
- Data is the synthetic starter dataset only. Never use real patient, donor or facility data.
- **AI must never:** release a unit, decide blood group compatibility, override a lab
  result or quarantine, rank patients on anything but clinical need, or present a guess
  as fact. So:
  - compatibility is a **fixed lookup table** (section 5), not a model;
  - every time estimate has a range;
  - every stock figure is labelled as the previous day's count, unconfirmed;
  - the engine **suggests** and never dispatches. People accept, change or reject.
- No LLM generates any number. Reasons come from string templates filled with computed values.

## 3. Stack and layout

- Python 3.11, pandas, numpy, PyYAML, pytest. SQLite through the standard `sqlite3` module.
- Data folder from the env var `DATA_DIR` (CSV files from the starter kit).

```
engine/
  __init__.py
  config.py      # loads config/<country>.yaml
  load.py        # CSV -> SQLite (data/blood.db) and cached pandas frames
  compat.py      # fixed red cell compatibility table
  stock.py       # previous-day snapshot, safety stock, lendable units, near-expiry
  eta.py         # fit and query the arrival-time distribution; baseline quote
  rank.py        # rank_sources() and baseline_sources()
  reasons.py     # plain-language reason templates
config/
  kenya.yaml
scripts/
  build_db.py    # one-off: CSVs -> SQLite, plus precomputed tables
  fit_eta.py     # fit ETA quantiles, print holdout metrics
tests/
  test_compat.py  test_stock.py  test_eta.py  test_rank.py  test_golden.py
```

## 4. Data used, and its quirks

| Table | Use |
|---|---|
| `facilities.csv` | type, lat/lon, `supply_centre_id`, `has_blood_fridge_backup_power`, `connectivity` |
| `routes.csv` | `typical_travel_hours` and `road_km` between every pair |
| `daily_stock.csv` | end-of-day stock by facility, component, blood group |
| `units.csv` | near-expiry counts (expiry_date, current_facility_id, status, status_date) |
| `transfers.csv` + `requests.csv` | fitting the ETA (emergency transfers only) |

Quirks to handle:
- Satellite centres (`SAT-*`) hold **no stock** in `daily_stock`, so they are never candidates.
- Use `facility_id`, never `facility_name_raw` (14% of names are messy).
- About 5% of emergency requests have patient group `unknown`.
- About 3% of transfers have no `received_at`. Drop them when fitting road time.
- Red cells can be `RBC` or `WB` (whole blood). Treat both as red cell supply for v1.
- Times are East Africa Time. Dataset period: 2025-11-01 to 2026-10-31.
- Units still `in_stock` at the end of the dataset have a **blank `status_date`**. Treat
  blank as "still on the shelf" in the near-expiry count (decided 2026-11-10). With the
  literal `status_date > as_of` rule, late-2026 requests miss almost every shelved unit
  (2026-10-30: 134 units found vs 1,329 in `daily_stock`). This moves golden case 1's
  National Referral near-expiry count from 3 to about 14; the ranking direction holds.
- `build_db` validates these assumptions (no satellite stock, complete 365-day stock
  series, full route coverage, blank `status_date` only for `in_stock`) and refuses to
  build if any fail.

## 5. Compatibility (fixed table, not AI)

Red cell compatibility, from patient group to acceptable unit groups:

| Patient | Acceptable units |
|---|---|
| O- | O- |
| O+ | O+, O- |
| A- | A-, O- |
| A+ | A+, A-, O+, O- |
| B- | B-, O- |
| B+ | B+, B-, O+, O- |
| AB- | AB-, A-, B-, O- |
| AB+ | all eight groups |

- `unknown` follows the emergency protocol: **group O units only** (O- and O+). Set the
  flag `group_unknown_emergency_O` and the note "Emergency group O per hospital protocol.
  Lab confirms before release."
- Every response carries `"compatibility_note": "From a fixed table. A qualified person
  crossmatches and releases every unit."`

## 6. Stock and what a site can spare

`as_of` = the request date minus one day, using end-of-day stock. That is the latest count
known at request time.

For a request at hospital `H` for patient group `g`, needing `need` units:

- **Candidates:** every facility except `H` and except satellites.
- **Regional centre:** can spare all its compatible stock (`RBC` + `WB`).
- **Hospital:** keeps its own safety stock. For each compatible group,
  `spare = max(0, stock - max(usual_level, min_keep))`, where
  - `usual_level` = median end-of-day stock for that facility and group (precompute once),
  - `min_keep` = 2 (from config).
- **O-negative reserve:** a hospital never lends O- that would take it below
  `o_neg_reserve` (config, default 2). O- is kept for O- patients and for women of
  childbearing age.
- **Sharing switch:** if config `sharing_allowed: false`, only regional centres are candidates.
- **Edges of the dataset (decided 2026-11-10):** requests on the first day (2025-11-01)
  have no previous-day count, so they use that day's closing count, and
  `as_of_stock_date` says so. Requests after the dataset ends (a live demo clock) use
  the last count.
- **Near-expiry count:** units of compatible groups at that facility with
  `collection_date <= as_of`, `status_date > as_of` (still on the shelf), and expiry within
  `near_expiry_days` (default 10) of the request date. Cap at `spare`. This approximates
  "on the shelf that day" from final-status data; say so in a code comment.
- Return per candidate: `stock_seen`, `spare`, `near_expiry`, `has_backup_power`, `connectivity`.

Precompute a stock lookup (dict or indexed frame keyed by date, facility, group) so one
ranking call takes under 200 ms.

## 7. Arrival range (ETA)

Arrival time = dispatch wait + road time.

**Fit** (`scripts/fit_eta.py`), on emergency transfers (`transfer_type` starting `emergency`)
joined to `requests.requested_at` and `routes.typical_travel_hours`:
- `wait_h = dispatched_at - requested_at`
- `ratio = (received_at - dispatched_at) / typical_travel_hours`
- **Train** on requests before 2026-07-01. **Test** on 2026-07-01 onwards.
- Store empirical samples (or a fine quantile grid) of `wait_h` and `ratio` in
  `data/eta_model.json`.

**Query** `eta_window(travel_hours, lender_is_hospital)`:
- Monte Carlo with a fixed seed: sample wait and ratio independently (they are independent
  in the data), arrival = wait + extra + ratio × travel_hours, where `extra` =
  `hospital_extra_dispatch_h` (config, default 0) when the lender is a hospital.
- Return `p10`, `p50`, `p90`, plus the parts for the reason: `wait_p50`, `road_p50`.
- **Fallback when the model file is missing:** wait 2.0 h, ratio 1.2, window ±50%. Set
  `model_used: false`.

**Baseline quote:** `typical_travel_hours + 2.0`, a single number with no range.

**Holdout metrics** (print from `fit_eta.py` and save to `data/eta_metrics.json`). These are
the expected values on the test period:
- MAE, map time only: about 2.74 h
- MAE, map time + 2 h: about 1.17 h
- MAE, model p50: about 0.95 h
- Share of actual arrivals inside p10–p90: about 0.79

If your numbers are far off, check the join and the emergency-type filter before anything else.

## 8. Ranking

`rank_sources(request, mode="model", top_n=5, config=...)`

- `request` = `{request_id?, facility_id, patient_group, units_needed, component: "RBC",
  clinical_indication, requested_at}`.
- `mode="model"`:
  1. Build candidates (section 6) with `spare >= units_needed`.
  2. Compute the ETA window for each.
  3. Sort by `round(p50 * 4) / 4` (quarter-hour buckets), then `near_expiry` descending,
     then `has_backup_power` (True first), then `spare` descending.
  4. If **no** candidate has enough, return the best partial options (largest `spare`
     within the shortest p50), each flagged `partial`, and set
     `advice: "no_full_source"`. Partial options are sites with at least 1 spare unit,
     sorted exactly like full options, fastest first (decided 2026-11-10).
- `mode="baseline"` (today's rule, also the **fallback**): the hospital's supply centre if
  it has enough stock, otherwise the other regional centres by `road_km`, nearest first,
  taking the first with enough stock (decided 2026-11-10; "the 2 nearest" would leave
  golden case 1 with no baseline). Quote = map time + 2 h, no window. If no centre has
  enough, `baseline.facility_id`, `name` and `quote_hours` are `null`.
  - The JSON has the same shape as model mode. `options` lists the baseline sites in rule
    order. Each still carries an `eta` range, and its `reason` says it is today's rule and
    gives today's single-number quote.
- **Clinician advice:** if the top option's `p90 > clinician_limit_h` (config, default 6),
  set `advice: "consider_emergency_O_or_transfer"`. This wins over `no_full_source` when
  both apply; the `partial` flags still show that no site covers the full request.
- Always return the baseline choice alongside the model ranking, so the UI can show both.
- Out-of-scope input raises `ValueError`: a component other than `RBC`, `units_needed`
  below 1, a patient group outside the table, or an unknown `facility_id`.

## 9. Output JSON contract (keep stable; teammates build on it)

```json
{
  "request": {"facility_id": "HSP-004", "patient_group": "O+", "units_needed": 1,
              "requested_at": "2026-10-31T00:58:00", "as_of_stock_date": "2026-10-30"},
  "mode": "model",
  "model_used": true,
  "sharing_allowed": true,
  "compatibility_note": "From a fixed table. A qualified person crossmatches and releases every unit.",
  "stock_note": "Yesterday's closing count. Unconfirmed until the supplying site confirms.",
  "advice": null,
  "options": [
    {
      "rank": 1,
      "facility_id": "HSP-001",
      "name": "National Referral Hospital (Nairobi)",
      "facility_type": "national_referral",
      "is_hospital": true,
      "spare": 24,
      "stock_seen": 96,
      "near_expiry": 3,
      "has_backup_power": true,
      "connectivity": "4G",
      "travel_hours_map": 0.48,
      "eta": {"p10": 1.4, "p50": 2.6, "p90": 3.8, "wait_p50": 2.0, "road_p50": 0.58},
      "flags": [],
      "reason": "Has 24 spare compatible units above its own safety stock. About 2.0 h to pack and dispatch, 0.6 h on the road. Most likely 2.6 h; 8 in 10 arrive within 1.4-3.8 h. 3 units expire within 10 days, so sharing them avoids waste."
    }
  ],
  "baseline": {
    "facility_id": "RBTC-ELD",
    "name": "Eldoret Regional Blood Transfusion Centre",
    "quote_hours": 8.9,
    "rule": "Supply centre first, then the nearest regional centres. Quote = map time + 2 h."
  }
}
```

Flags vocabulary: `no_backup_power`, `partial`, `group_unknown_emergency_O`,
`o_neg_reserve_applied`, `low_connectivity_2g`.

`o_neg_reserve_applied` appears only when the O- reserve held back units that the normal
safety stock (`max(usual_level, min_keep)`) would have lent. With the default config
(`o_neg_reserve` = `min_keep` = 2) it never fires; raise `o_neg_reserve` to see it.

## 10. Config (`config/kenya.yaml`)

```yaml
country: Kenya
sharing_allowed: true          # hospital-to-hospital sharing; confirm with the blood-service expert
min_keep: 2                    # units a hospital always keeps per group
o_neg_reserve: 2
near_expiry_days: 10
hospital_extra_dispatch_h: 0   # sensitivity: try 1 and 2
clinician_limit_h: 6
baseline_quote_extra_h: 2.0
eta_train_before: "2026-07-01"
language: en
```

A second country = a second YAML file. No code changes.

## 11. Golden test cases (from the real dataset)

These were checked by hand. Ranks can shift slightly with your ETA fit, but the
**direction** must hold.

| Request | Hospital | Need | Expected |
|---|---|---|---|
| REQ-020421 (2026-10-31 00:58) | HSP-004 Westlands Private | 1 × O+ | Nairobi centre (0.47 h) has 0 compatible units. City Maternity (0.47 h) holds 8 but is at its usual level, so spare 0. Top options are nearby hospitals: National Referral (0.48 h, spare 22, 14 near expiry) and Eastlands County (0.68 h, spare 2). Baseline = Eldoret centre (6.93 h map). Model p50 ≈ 2.6 h vs baseline quote ≈ 8.9 h. |
| REQ-005594 (2025-12-26 23:17) | HSP-009 Kilifi County | 1 × O+ | Mombasa centre (1.59 h, 3 units) and Coast Teaching (1.60 h, spare 18, 6 near expiry) are both near the top. The baseline agrees with the model. |
| REQ-003159 (2025-11-03 02:41) | HSP-032 Garissa County Referral | 4 × O+ | Nothing with spare stock within 8 h (Kitui 7.5 h has 0 spare). National Referral (11.7 h) holds 56 O+ against a usual level of 72, so spare 0. Nearest full source is Nakuru centre (14.1 h, spare 15), then Mombasa centre (14.2 h, spare 53). `advice = consider_emergency_O_or_transfer`. |

Stock figures above were updated on 2026-11-10 to what section 6 gives on the starter
data. The first hand-checked values (City Maternity ~5, Coast Teaching ~13, National
Referral ~18 in case 3) could not be reproduced by section 6 or by 54 alternative
definitions of `usual_level`. ETA and baseline figures are checked in steps 4 and 5.

Also test:
- the requester is never a candidate;
- satellites never appear;
- a hospital's `spare` never takes it below `max(usual_level, 2)`;
- `sharing_allowed: false` returns centres only;
- `unknown` patient group returns only O- and O+ units plus the flag;
- ETA quantiles satisfy p10 < p50 < p90, and p50 grows with travel time;
- a missing ETA model file falls back without crashing (`model_used: false`).

## 12. Build order (commit after each)

1. `build_db.py`: CSVs into SQLite, plus the precomputed `usual_level` table and stock lookup.
2. `compat.py` and its tests.
3. `stock.py`: snapshot, spare, near-expiry, and tests.
4. `fit_eta.py` and `eta.py`: fit, holdout metrics, query, fallback, and tests.
5. `rank.py` and `reasons.py`: model mode, baseline mode, advice, JSON output.
6. Golden tests (section 11).
7. A tiny CLI: `python -m engine.rank --request-id REQ-020421` prints the JSON. Handy for
   teammates and the demo.

**Done** means `pytest` passes, the CLI prints valid JSON for the 3 golden requests, and
`data/eta_metrics.json` exists.

## 13. Out of scope for this engine

- Web API, UI, SMS parsing (teammates).
- The year-long replay and results numbers (data scientist 2). Make sure `rank_sources`
  works with any `requested_at` in the dataset so the replay can call it in a loop.
- Platelets and plasma, other regions, a live map.
