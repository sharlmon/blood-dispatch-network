# Arrival estimates

This module predicts **hours from request submission to the last recorded unit
arriving at the receiving facility from one source**. It does not predict bedside
readiness, crossmatching time, or whether the source can supply the full request.
The ranking engine must first check eligibility and available quantity.

```python
from datetime import datetime
from engine.arrival import fit_arrival_model, estimate_arrival

model = fit_arrival_model(
    requests,
    transfers,
    routes,  # {(source_id, destination_id): CSV route row}
    trained_before=datetime(2026, 8, 1),
)
estimate = estimate_arrival(
    1.5,
    model=model,
    settings=country_settings,  # Full mapping containing the arrival section.
    source_kind="centre",     # Or "hospital", with an extrapolation warning.
)
```

## How it works

1. Keep emergency-request and emergency-cross-region transfers linked to an
   unambiguous request ID. Facility IDs, rather than typed facility names, define
   the destination.
2. Group unit rows by request and source. Exclude a batch if any unit lacks a
   valid dispatch or receipt time. This avoids counting several units in one
   supplied batch as independent observations.
3. Take the unit with the latest receipt. Record its own request-to-dispatch wait
   and its transit duration divided by mapped travel time. Keep these values
   together, preserving their observed dependence.
4. For a proposed route, compute `wait + multiplier * mapped_hours` for every
   paired observation. Return interpolated empirical p10, p50 and p90. Exact
   empirical quantiles are deterministic and cached; no random simulation noise
   is introduced.

A partially fulfilled request can have a fully observed supplied batch. Its
timing can be learned without claiming that the entire request was fulfilled.
The model pools routes; it is not calibrated for each individual route. Hospital
lending was not observed in the starter data, so hospital estimates explicitly
carry an extrapolation warning.

## Cutoffs, missing data and fallback

Training uses requests **and every batch receipt strictly before**
`trained_before`. Timestamps without an offset are interpreted as East Africa
Time (UTC+3); offset-aware values are normalized to UTC. Missing routes, invalid
durations, unlinked requests and incomplete batches are counted and excluded.
Exclusion metadata distinguishes unit rows from grouped supplied batches.

With fewer than `min_samples` observations (default 20), return
`dispatch_wait_hours + road_time_multiplier * mapped_hours`. Defaults are 2 hours
and 1.2. The interval bounds are `null`, `model_used` is false, and the response
explains the fallback. A missing route must be handled upstream: do not pass zero
to represent an unknown route. Zero is accepted only for a genuinely zero-length
route.

The p10–p90 bounds describe an estimated **80% interval**, whose empirical
reliability must be checked on held-out data. They do not mean an almost-certain
arrival. Modelled uncertainty does not include stock accuracy, confirmation
failure, cold-chain suitability or clinical readiness.

## Validation and persistence

`evaluate_arrival_model(..., start=..., end=...)` requires the training cutoff
to be at or before the evaluation start. It evaluates requests in `[start, end)`
whose supplied batches were completely received before `end`; incomplete or
censored batches are counted separately. Reports contain median/mean absolute
error, p10–p90 coverage, interval width, fraction beyond p90 and errors for the
mapped-travel-plus-two-hours baseline. Empty metrics and unavailable coverage
remain `null`.

`ArrivalModel.save(path)` and `ArrivalModel.load(path)` persist a versioned JSON
model. `to_dict()` and `from_dict()` support integration without filesystem I/O.
All scientific calculations use the Python standard library.
