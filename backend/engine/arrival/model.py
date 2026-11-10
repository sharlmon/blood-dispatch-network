"""Small, deterministic empirical arrival model with no scientific dependencies."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from statistics import mean, median
from typing import Any

LOCAL_TIMEZONE = timezone(timedelta(hours=3))
MODEL_VERSION = "paired_empirical_v1"
EMERGENCY_TYPES = frozenset({"emergency_request", "emergency_cross_region"})
Row = Mapping[str, Any]
Routes = Mapping[tuple[str, str], Row]


def _timestamp(value: Any) -> datetime:
    """Interpret dataset's naive timestamps as EAT; compare aware values safely."""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
    return parsed.astimezone(timezone.utc)


def _nonnegative(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return number


def _integer(value: Any, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or (positive and value <= 0):
        raise ValueError(f"{name} must be {'a positive ' if positive else 'an '}integer")
    return value


@dataclass(frozen=True, eq=False)
class ArrivalModel:
    """Serializable, immutable shipment observations; sample rows are (wait, ratio).

    ``seed`` is recorded for reproducibility across consumers. Exact empirical
    quantiles use every paired observation, so this implementation has no sampling
    noise and does not depend on random-number-generator state.
    """

    samples: tuple[tuple[float, float], ...]
    trained_before: datetime
    min_samples: int = 20
    seed: int = 42
    exclusions: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _integer(self.min_samples, "min_samples", positive=True)
        _integer(self.seed, "seed")
        normalized = []
        for sample in self.samples:
            if len(sample) != 2:
                raise ValueError("Each sample must contain preparation hours and road multiplier")
            normalized.append((
                _nonnegative(sample[0], "preparation_hours"),
                _nonnegative(sample[1], "road_multiplier"),
            ))
        counts = {}
        for key, value in self.exclusions.items():
            _integer(value, f"exclusions.{key}")
            if value < 0:
                raise ValueError("Exclusion counts cannot be negative")
            counts[str(key)] = value
        # Copy inputs: mutating a caller's list cannot invalidate cached estimates.
        object.__setattr__(self, "samples", tuple(normalized))
        object.__setattr__(self, "trained_before", _timestamp(self.trained_before))
        object.__setattr__(self, "exclusions", counts)

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "model_type": MODEL_VERSION,
            "trained_before": self.trained_before.isoformat(),
            "min_samples": self.min_samples,
            "seed": self.seed,
            "samples": [list(sample) for sample in self.samples],
            "exclusions": dict(self.exclusions),
            "time_origin": "request_submission",
            "arrival_endpoint": "receiving_facility",
            "unit_of_analysis": "request_source_batch_last_receipt",
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ArrivalModel:
        if not isinstance(payload, Mapping):
            raise ValueError("Arrival model must be a JSON object")
        if type(payload.get("schema_version")) is not int or payload.get("schema_version") != 1 or payload.get("model_type") != MODEL_VERSION:
            raise ValueError("Unsupported arrival model schema or model type")
        try:
            if not isinstance(payload["samples"], (list, tuple)) or any(
                not isinstance(row, (list, tuple)) or len(row) != 2 for row in payload["samples"]
            ):
                raise ValueError("samples must be an array of numeric pairs")
            return cls(
                samples=tuple(tuple(row) for row in payload["samples"]),
                trained_before=_timestamp(payload["trained_before"]),
                min_samples=payload["min_samples"],
                seed=payload["seed"],
                exclusions=payload.get("exclusions", {}),
            )
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("Invalid arrival model payload") from error

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> ArrivalModel:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        # The evaluation CLI wraps artifacts with provenance; standalone save()
        # writes the plain model. Both formats retain the same model contract.
        if isinstance(payload, Mapping) and "result" in payload:
            payload = payload["result"]
        return cls.from_dict(payload)


@dataclass(frozen=True)
class _Observation:
    wait: float
    ratio: float
    travel: float
    actual: float


def _observations(
    requests: Sequence[Row],
    transfers: Sequence[Row],
    routes: Routes,
    *,
    before: datetime,
    start: datetime | None = None,
) -> tuple[list[_Observation], dict[str, int]]:
    """Create one observed supplied-batch completion per (request, source).

    Unit rows in one request-source batch do not provide independent evidence.
    The last-received unit supplies the paired preparation and transport times.
    A batch with any missing receipt is excluded. A completed supplied batch may
    still fulfil only part of the original request. Counts explicitly distinguish
    input rows and grouped shipments (supplied batches).
    """
    counts: Counter[str] = Counter(input_transfer_rows=len(transfers))
    by_id: dict[str, Row] = {}
    ambiguous_ids: set[str] = set()
    for request in requests:
        request_id = str(request.get("request_id", ""))
        if request_id in by_id:
            ambiguous_ids.add(request_id)
        by_id[request_id] = request

    grouped: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for row in transfers:
        if row.get("transfer_type") not in EMERGENCY_TYPES:
            counts["non_emergency_transfer_rows"] += 1
            continue
        counts["emergency_transfer_rows"] += 1
        request_id = str(row.get("request_id", ""))
        if not request_id or request_id not in by_id or request_id in ambiguous_ids:
            counts["unlinked_or_ambiguous_request_rows"] += 1
            continue
        grouped[(request_id, str(row.get("from_facility_id", "")))].append(row)

    counts["grouped_shipments"] = len(grouped)
    observations = []
    for (request_id, source), rows in grouped.items():
        counts["collapsed_unit_rows"] += len(rows) - 1
        request = by_id[request_id]
        destination = str(request.get("facility_id", ""))
        if not source or not destination or any(row.get("to_facility_id") != destination for row in rows):
            counts["destination_mismatch_shipments"] += 1
            continue
        try:
            requested = _timestamp(request.get("requested_at", ""))
        except (ValueError, TypeError, OverflowError):
            counts["missing_or_invalid_timestamp_shipments"] += 1
            continue
        if requested >= before or (start is not None and requested < start):
            counts["outside_request_window_shipments"] += 1
            continue
        try:
            dispatches = [_timestamp(row.get("dispatched_at", "")) for row in rows]
            receipts = [_timestamp(row.get("received_at", "")) for row in rows]
        except (ValueError, TypeError, OverflowError):
            counts["missing_or_invalid_timestamp_shipments"] += 1
            continue
        # Labels after the cutoff are unknown at training/evaluation time.
        if max(receipts) >= before:
            counts["receipt_at_or_after_cutoff_shipments"] += 1
            continue
        if any(dispatched < requested or received < dispatched for dispatched, received in zip(dispatches, receipts)):
            counts["invalid_chronology_shipments"] += 1
            continue
        route = routes.get((source, destination))
        try:
            travel = _nonnegative(route["typical_travel_hours"], "typical_travel_hours", positive=True) if route else None
        except (KeyError, ValueError, TypeError):
            travel = None
        if travel is None:
            counts["missing_or_invalid_route_shipments"] += 1
            continue
        # Keep the actual last unit's preparation/transit pair together. Taking
        # the maximum dispatch independently would break the observed pairing.
        received, dispatched = max(zip(receipts, dispatches))
        wait = (dispatched - requested).total_seconds() / 3600
        transit = (received - dispatched).total_seconds() / 3600
        ratio = transit / travel
        if not math.isfinite(ratio):
            counts["nonfinite_derived_multiplier_shipments"] += 1
            continue
        observations.append(_Observation(wait, ratio, travel, wait + transit))
    counts["valid_shipments"] = len(observations)
    return observations, dict(sorted(counts.items()))


def fit_arrival_model(
    requests: Sequence[Row],
    transfers: Sequence[Row],
    routes: Routes,
    *,
    trained_before: datetime,
    min_samples: int = 20,
    seed: int = 42,
) -> ArrivalModel:
    """Fit only completed emergency shipments known strictly before the cutoff.

    Models pool routes because individual routes may be sparse. Preparation time
    and road multiplier remain paired, preserving their observed dependence.
    Route estimates and the request-to-receipt target are not bedside-ready time.
    """
    _integer(min_samples, "min_samples", positive=True)
    _integer(seed, "seed")
    before = _timestamp(trained_before)
    observations, counts = _observations(requests, transfers, routes, before=before)
    return ArrivalModel(
        samples=tuple((sample.wait, sample.ratio) for sample in observations),
        trained_before=before,
        min_samples=min_samples,
        seed=seed,
        exclusions=counts,
    )


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    """Linear interpolation between adjacent empirical order statistics."""
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)


@lru_cache(maxsize=512)
def _quantiles(model: ArrivalModel, travel: float) -> tuple[float, float, float]:
    durations = sorted(wait + ratio * travel for wait, ratio in model.samples)
    if any(not math.isfinite(duration) for duration in durations):
        raise ValueError("Arrival duration overflowed; check travel time and model values")
    return tuple(_quantile(durations, percentile) for percentile in (0.1, 0.5, 0.9))


def estimate_arrival(
    travel_hours: float,
    *,
    model: ArrivalModel | None = None,
    settings: Mapping[str, Any] | None = None,
    source_kind: str = "centre",
) -> dict[str, Any]:
    """Estimate request-to-arrival hours for a route.

    ``settings`` is the complete country-settings mapping, with an ``arrival``
    section. Fallback estimates use dispatch_wait_hours (default 2) plus
    road_time_multiplier (default 1.2) times map travel. Bounds are deliberately
    null when no adequately fitted model exists. Do not substitute zero for a
    missing route; handle unavailable routes before calling this function.
    """
    travel = _nonnegative(travel_hours, "travel_hours")
    if source_kind not in {"centre", "hospital"}:
        raise ValueError("source_kind must be 'centre' or 'hospital'")
    if model is not None and not isinstance(model, ArrivalModel):
        raise ValueError("model must be an ArrivalModel or None")
    if settings is not None and not isinstance(settings, Mapping):
        raise ValueError("settings must be a mapping")
    arrival = (settings or {}).get("arrival", {})
    if not isinstance(arrival, Mapping):
        raise ValueError("settings.arrival must be a mapping")
    warnings = []
    if source_kind == "hospital":
        warnings.append("hospital_lending_extrapolation_not_validated")
    count = model.sample_count if model else 0
    used = model is not None and count >= model.min_samples
    if used:
        p10, p50, p90 = _quantiles(model, travel)
        warnings.append("pooled_emergency_shipment_distribution_not_route_specific")
    else:
        wait = _nonnegative(arrival.get("dispatch_wait_hours", 2.0), "dispatch_wait_hours")
        multiplier = _nonnegative(arrival.get("road_time_multiplier", 1.2), "road_time_multiplier")
        p10, p50, p90 = None, wait + multiplier * travel, None
        if not math.isfinite(p50):
            raise ValueError("Arrival duration overflowed; check fallback settings")
        warnings.append("insufficient_training_shipments" if model else "arrival_model_unavailable")
        warnings.append("fallback_point_estimate_has_no_validated_interval")
    return {
        "p10_hours": p10,
        "p50_hours": p50,
        "p90_hours": p90,
        "model_used": used,
        "estimate_basis": "historical_paired_empirical" if used else "configured_fallback",
        "sample_count": count,
        "interval_probability": 0.8 if used else None,
        "time_origin": "request_submission",
        "arrival_endpoint": "receiving_facility",
        "unit_of_analysis": "request_source_batch_last_receipt",
        "warnings": warnings,
    }


def evaluate_arrival_model(
    model: ArrivalModel,
    requests: Sequence[Row],
    transfers: Sequence[Row],
    routes: Routes,
    *,
    start: datetime,
    end: datetime,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate on later, completed shipments in [start, end), never training rows.

    Receipt timestamps must also precede ``end``. This evaluates observed completed
    shipments only; censored/unconfirmed deliveries are counted as exclusions and
    no claims about their timing are inferred. Baseline is map travel plus 2 hours.
    """
    start_time, end_time = _timestamp(start), _timestamp(end)
    if end_time <= start_time:
        raise ValueError("Evaluation end must be after start")
    if model.trained_before > start_time:
        raise ValueError("Model training cutoff must not overlap the evaluation period")
    observations, exclusions = _observations(
        requests, transfers, routes, before=end_time, start=start_time,
    )
    errors, baseline_errors, widths, covered, after_p90 = [], [], [], [], []
    for row in observations:
        estimate = estimate_arrival(row.travel, model=model, settings=settings)
        errors.append(abs(estimate["p50_hours"] - row.actual))
        baseline_errors.append(abs(row.travel + 2 - row.actual))
        if estimate["model_used"]:
            widths.append(estimate["p90_hours"] - estimate["p10_hours"])
            covered.append(estimate["p10_hours"] <= row.actual <= estimate["p90_hours"])
            after_p90.append(row.actual > estimate["p90_hours"])
    sample_count = len(observations)
    return {
        "schema_version": 1,
        "evaluation_period": {"start_inclusive": start_time.isoformat(), "end_exclusive": end_time.isoformat()},
        "trained_before": model.trained_before.isoformat(),
        "model_type": MODEL_VERSION,
        "training_sample_count": model.sample_count,
        "sample_count": sample_count,
        "interval_sample_count": len(covered),
        "unit_of_analysis": "request_source_batch_last_receipt",
        "time_origin": "request_submission",
        "arrival_endpoint": "receiving_facility",
        "metrics": {
            "median_absolute_error_hours": median(errors) if errors else None,
            "mean_absolute_error_hours": mean(errors) if errors else None,
            "p10_p90_coverage": mean(covered) if covered else None,
            "nominal_interval_probability": 0.8,
            "mean_interval_width_hours": mean(widths) if widths else None,
            "fraction_after_p90": mean(after_p90) if after_p90 else None,
            "baseline_map_plus_2_mean_absolute_error_hours": mean(baseline_errors) if baseline_errors else None,
            "baseline_map_plus_2_median_absolute_error_hours": median(baseline_errors) if baseline_errors else None,
        },
        "exclusions": exclusions,
        "limitations": [
            "Synthetic starter data; performance does not establish clinical or real-world validity.",
            "Completed emergency shipments only; unconfirmed or censored shipments are excluded.",
            "Pooled route distribution; hospital-to-hospital lending is not validated.",
            "Receiving-facility arrival excludes bedside preparation and crossmatching.",
            "Completion means all recorded units in a request-source batch, not all units originally requested.",
        ],
    }
