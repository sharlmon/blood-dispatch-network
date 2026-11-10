# Ranking engine

Finds sites that can spare compatible red cells for an emergency request, ranks them by
an honest arrival range, and returns JSON. It suggests; people decide. Full spec:
[docs/RANKING_ENGINE_SPEC.md](../../docs/RANKING_ENGINE_SPEC.md).

## Set up (once)

From `backend/`, with the starter CSVs in the repo's `data/` folder (git-ignored):

```bash
python -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
export DATA_DIR=data                # relative paths resolve from the repo root
python scripts/build_db.py          # CSVs -> data/blood.db, with data checks (~10 s)
python scripts/fit_eta.py           # arrival model -> data/eta_model.json + eta_metrics.json
```

## Use it

Command line:

```bash
python -m engine.rank --request-id REQ-020421
python -m engine.rank --request-id REQ-020421 --mode baseline
python -m engine.rank --facility HSP-004 --group O+ --units 1 --at 2026-10-31T00:58
```

From Python (API, replay):

```python
from engine.rank import rank_sources

out = rank_sources({
    "facility_id": "HSP-004", "patient_group": "O+", "units_needed": 1,
    "component": "RBC", "requested_at": "2026-10-31T00:58:00",
})
```

- Returns the spec section 9 JSON as a dict. Keys are stable; build against them.
  New fields may be added, but existing keys won't be renamed or removed.
- Works for any `requested_at` in the dataset.
- If `eta_model.json` is missing, ranges fall back to rough defaults and
  `model_used` is `false`.

### For the Flask API

- **Warm up at startup.** The first call loads the data (~14 s); after that each call
  takes ~0.07 s. Call `rank_sources` once inside `create_app()` so the first demo
  click doesn't hang. Don't pass a fresh `frames` per request; the default reuses
  the cached data.
- **Bad input raises `ValueError`** with a plain message: unknown facility or blood
  group, a component other than RBC, or `units_needed` < 1. Return it as HTTP 400
  with the message.
- **Paths.** `DATA_DIR` resolves from the repo root (`DATA_DIR=data`, not `../data`).
  The engine's database is `ENGINE_DB_PATH` (default `$DATA_DIR/blood.db`), kept apart
  from the API's own `DB_PATH`.

## Sample outputs (no Python needed)

[`examples/`](examples/) holds real outputs for building screens and SMS replies.
`tests/test_examples.py` fails if they go stale; regenerate with
`python scripts/make_examples.py`.

| File | Shows |
|---|---|
| `full_source.json` | Normal case: nearby hospitals can cover it (REQ-020421) |
| `baseline_mode.json` | Same request under today's rule (`mode: "baseline"`) |
| `partial.json` | No site can cover all 6 units: `partial` flags, `advice: "no_full_source"` |
| `too_long.json` | Nothing close: `advice: "consider_emergency_O_or_transfer"` (REQ-003159) |

## What the fields mean

All times are in **hours**. All stock is **yesterday's closing count, unconfirmed**.

| Field | Meaning |
|---|---|
| `request.as_of_stock_date` | Date of the stock count used (the day before the request) |
| `advice` | `null`; `no_full_source` (no site has enough; options are partial); `consider_emergency_O_or_transfer` (even the best option's slow end, p90, is over 6 h) |
| `options[].stock_seen` | Compatible red cell units the site held at yesterday's close |
| `options[].spare` | Of those, what it can lend. Hospitals keep `max(usual level, 2)` per group and their O- reserve; regional centres can lend all |
| `options[].spare_by_group` | `spare` split by blood group, e.g. `{"O+": 21, "O-": 1}` |
| `options[].near_expiry` | Spare units expiring within 10 days of the request (sharing them avoids waste) |
| `options[].travel_hours_map` | Map driving time from the routes table |
| `options[].eta.p50` | Most likely arrival time, from request to delivery |
| `options[].eta.p10` / `p90` | 8 in 10 deliveries arrive between these two times |
| `options[].eta.wait_p50` | Typical time to pack and dispatch |
| `options[].eta.road_p50` | Typical actual road time (usually longer than `travel_hours_map`) |
| `options[].flags` | `partial`, `no_backup_power`, `low_connectivity_2g`, `group_unknown_emergency_O`, `o_neg_reserve_applied` |
| `baseline` | Today's rule: supply centre first, then nearest regional centre with stock; quote = map time + 2 h, no range |

Reasons are about 250 characters, too long for one SMS; the SMS reply should be built from the fields.

## Limits to state in the demo

- **Hospital lending is assumed.** The dataset has no hospital-to-hospital lending.
  Hospital arrival times reuse regional-centre dispatch waits, and the reasons say so.
  The validation (0.95 h typical error against 1.17 h for today's rule; 80% of arrivals
  inside the range) is on regional-centre deliveries only.
- **The result holds if hospitals are slower.** Golden case REQ-020421, from
  `python scripts/sensitivity.py`:

| Scenario | Top option | Most likely | 8 in 10 within | Today's quote |
|---|---|---|---|---|
| Sharing off (today's network) | Eldoret centre | 10.3 h | 8.3-12.3 h | 8.9 h |
| Sharing on, hospitals +0 h to dispatch | National Referral | 2.6 h | 1.4-3.8 h | 8.9 h |
| +1 h | National Referral | 3.6 h | 2.4-4.8 h | 8.9 h |
| +2 h | National Referral | 4.6 h | 3.4-5.8 h | 8.9 h |
| +3 h | National Referral | 5.6 h | 4.4-6.8 h (advice fires: p90 over 6 h) | 8.9 h |

- **Remote and 2G sites are not served worse.** Holdout from `python scripts/fit_eta.py`
  (typical error in hours; "inside" = share of arrivals within the 8-in-10 range):

| Group | Deliveries | Today's rule | Model | Inside range | Range width |
|---|---|---|---|---|---|
| Map time under 2 h | 900 | 0.74 | 0.72 | 82% | 2.4 h |
| Map time 2-5 h | 546 | 1.05 | 0.89 | 77% | 2.8 h |
| Map time 5 h+ | 288 | 2.75 | 1.76 | 79% | 5.8 h |
| Receiving hospital on 2G | 113 | 2.76 | 1.83 | 79% | 6.1 h |

  Error grows with distance, but the range widens to match, and the gain over today's
  rule is largest for the most remote hospitals.

- **Arrival is not ready-to-transfuse.** Crossmatch, cold-chain checks and approval of
  the transfer come on top.
- **No reservation.** The engine doesn't remember suggestions, so two requests at the same time
  can be offered the same units. A person confirms every transfer.
- **Lookahead in replay numbers.** `usual_level` is a median over the whole year, and
  near-expiry uses each unit's final status, so replays see some later information.

## Settings

`backend/config/kenya.yaml` holds sharing on/off, safety stock, O- reserve, near-expiry
window, clinician time limit. A new country is a new YAML file, with no code change.

## Tests

```bash
DATA_DIR=data python -m pytest      # ~3 min; real-data tests skip if DATA_DIR is unset
```

## Files

| File | What it does |
|---|---|
| `config.py` | `DATA_DIR` / `ENGINE_DB_PATH` from the environment; loads `config/<country>.yaml` |
| `load.py` | CSV -> SQLite, data checks, `usual_level`, stock lookup |
| `compat.py` | Fixed red cell compatibility table |
| `stock.py` | Yesterday's stock, what each site can spare, near-expiry count |
| `eta.py` | Fit and query the arrival range (p10/p50/p90) |
| `rank.py` | `rank_sources()`, baseline mode, advice, JSON, CLI |
| `reasons.py` | Plain-language reason templates |
