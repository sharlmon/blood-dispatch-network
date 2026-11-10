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
- Works for any `requested_at` in the dataset. Data and model load once per process,
  then each call takes ~60 ms.
- Bad input (non-RBC component, unknown group or facility, `units_needed` < 1) raises
  `ValueError` with a plain message. Catch it and show the message.
- If `eta_model.json` is missing, ranges fall back to rough defaults and
  `model_used` is `false`.

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
