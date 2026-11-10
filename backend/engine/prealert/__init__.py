"""Evening review alerts and retrospective evaluation of recorded shortages.

This is a stock rule, not a demand forecast or an automatic replenishment order.
Components are evaluated independently; whole blood is never silently treated as
an interchangeable red-cell unit. All naive timestamps refer to dataset EAT.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite
from typing import Mapping, Sequence


EAT = timezone(timedelta(hours=3), name="EAT")
StockKey = tuple[date, str, str, str]
ExposureKey = tuple[str, str, str]
BLOOD_GROUPS = frozenset(("O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"))
COMPONENTS = frozenset(("RBC", "WB", "PLT", "FFP", "CRYO"))


@dataclass(frozen=True)
class _Settings:
    blood_groups: tuple[str, ...]
    components: tuple[str, ...]
    run_hour: int
    horizon_hours: float
    max_snapshot_age_days: int


def _settings(settings: Mapping | None) -> _Settings:
    config = (settings or {}).get("prealert", {})
    if not isinstance(config, Mapping):
        raise ValueError("prealert settings must be a mapping")

    def selected(name: str, default: tuple[str, ...], allowed: frozenset) -> tuple[str, ...]:
        values = config.get(name, default)
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError(f"prealert.{name} must be a nonempty list")
        if any(not isinstance(value, str) or value not in allowed for value in values):
            raise ValueError(f"prealert.{name} contains an unsupported value")
        return tuple(dict.fromkeys(values))

    hour = config.get("run_hour", 18)
    if isinstance(hour, bool) or not isinstance(hour, int) or not 0 <= hour <= 23:
        raise ValueError("prealert.run_hour must be an integer from 0 to 23")
    horizon = config.get("horizon_hours", 24)
    if isinstance(horizon, bool) or not isinstance(horizon, (float, int)):
        raise ValueError("prealert.horizon_hours must be a number")
    if not isfinite(horizon) or not 0 < horizon <= 24:
        raise ValueError("prealert.horizon_hours must be greater than 0 and at most 24")
    age = config.get("max_snapshot_age_days", 1)
    if isinstance(age, bool) or not isinstance(age, int) or age < 1:
        raise ValueError("prealert.max_snapshot_age_days must be an integer of at least 1")
    return _Settings(
        selected("blood_groups", ("O+",), BLOOD_GROUPS),
        selected("components", ("RBC",), COMPONENTS),
        hour,
        float(horizon),
        age,
    )


def _local(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("timestamps must be datetime values")
    return value.replace(tzinfo=EAT) if value.tzinfo is None else value.astimezone(EAT)


def _hospital_keys(facilities: Mapping[str, Mapping], config: _Settings):
    for facility_id in sorted(facilities):
        if facility_id.startswith("HSP-"):
            for component in config.components:
                for group in config.blood_groups:
                    yield facility_id, component, group


def _stock_value(stock: Mapping[StockKey, int], day: date, key: ExposureKey) -> int | None:
    value = stock.get((day, *key))
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise ValueError(f"Stock must be a nonnegative integer for {(day, *key)!r}")
    return value


def _assumptions(config: _Settings) -> list[str]:
    return [
        "Synthetic starter dataset; results do not describe real facilities.",
        "Naive timestamps are East Africa Time (UTC+03:00).",
        "Only the exact previous day's closing stock is available at each cutoff; "
        "missing snapshots are unknown and older stock is never carried forward.",
        "Only configured exact blood groups and components are evaluated; "
        "components are not pooled and compatibility substitution is not inferred.",
        "A zero-stock alert requires human review and is not a prediction or an order.",
        f"Daily evaluation windows last {config.horizon_hours:g} hours; "
        "windows are half-open and cannot overlap.",
        "Alert association with later unmet demand does not establish that "
        "replenishment would have prevented a shortage.",
    ]


def generate_prealerts(
    stock: Mapping[StockKey, int],
    facilities: Mapping[str, Mapping[str, str]],
    *,
    as_of: datetime,
    settings: Mapping | None = None,
) -> dict:
    """Return known zero-stock alerts using yesterday's closing snapshot.

    ``stock`` keys are ``(date, facility_id, component, blood_group)``. Missing
    records remain unknown, even when older/current/future snapshots exist. The
    caller schedules generation; calling before run_hour does not advance time.
    Settings live under ``settings['prealert']``. Defaults: O+, RBC, 18:00, 24h.
    """
    config = _settings(settings)
    cutoff = _local(as_of)
    stock_day = cutoff.date() - timedelta(days=1)
    alerts = []
    missing = []
    for key in _hospital_keys(facilities, config):
        facility_id, component, group = key
        units = _stock_value(stock, stock_day, key)
        record = {
            "facility_id": facility_id,
            "component": component,
            "blood_group": group,
            "stock_as_of": stock_day.isoformat(),
        }
        if units is None:
            missing.append({**record, "reason": "missing_previous_day_snapshot"})
        elif units == 0:
            alerts.append({
                **record,
                "recorded_units": units,
                "generated_at": cutoff.isoformat(),
                "reason": "known_zero_stock_for_component_previous_closing_snapshot",
                "human_review_required": True,
            })
    return {
        "generated_at": cutoff.isoformat(),
        "stock_as_of": stock_day.isoformat(),
        "alerts": alerts,
        "missing_snapshot": missing,
        "assumptions": _assumptions(config),
    }


def _request_events(requests, facilities, config, start, end):
    """Index once so evaluation does not rescan every request for every evening."""
    events = defaultdict(list)
    ignored = defaultdict(int)
    seen = {}
    for row in requests:
        try:
            raw_time = row["requested_at"]
            timestamp = _local(raw_time if isinstance(raw_time, datetime) else datetime.fromisoformat(raw_time))
        except (KeyError, TypeError, ValueError):
            ignored["invalid_time_or_quantity"] += 1
            continue
        if not start <= timestamp < end:
            ignored["outside_observation_period"] += 1
            continue
        if row.get("urgency") not in ("emergency", "urgent"):
            ignored["other_urgency"] += 1
            continue
        group = row.get("patient_blood_group")
        if group not in BLOOD_GROUPS:
            ignored["unknown_blood_group"] += 1
            continue
        component = row.get("component_requested")
        if group not in config.blood_groups or component not in config.components:
            ignored["outside_configured_groups_or_components"] += 1
            continue
        facility_id = row.get("facility_id", "")
        if facility_id not in facilities or not facility_id.startswith("HSP-"):
            ignored["not_a_known_hospital"] += 1
            continue
        try:
            requested = int(row["units_requested"])
            issued = int(row["units_issued"])
            if requested <= 0 or issued < 0 or issued > requested:
                raise ValueError("invalid quantity")
        except (KeyError, TypeError, ValueError):
            ignored["invalid_time_or_quantity"] += 1
            continue
        request_id = row.get("request_id")
        if not request_id:
            ignored["missing_request_id"] += 1
            continue
        signature = (timestamp, facility_id, component, group, requested, issued)
        if request_id in seen:
            if seen[request_id] != signature:
                raise ValueError(f"Conflicting duplicate request_id: {request_id}")
            ignored["duplicate_request_id"] += 1
            continue
        seen[request_id] = signature
        events[(facility_id, component, group)].append((timestamp, issued < requested))
    for values in events.values():
        values.sort()
    return events, dict(sorted(ignored.items()))


def evaluate_prealerts(
    stock: Mapping[StockKey, int],
    facilities: Mapping[str, Mapping[str, str]],
    requests: Sequence[Mapping[str, str]],
    *,
    start: datetime,
    end: datetime,
    settings: Mapping | None = None,
) -> dict:
    """Evaluate daily zero-stock alerts against later partial/unmet requests.

    ``end`` is the caller's explicit observed-through boundary, not a request
    maximum inferred from the data. A window whose end exceeds it is censored
    and excluded from precision/recall, even if no request happens to appear.

    Precision measures alerts followed by at least one matching unmet request.
    Recall measures matching unmet requests covered by a zero-stock alert,
    among requests with a known previous-day snapshot. Unknown stock is counted
    separately. Denominators differ intentionally and are returned explicitly.
    """
    config = _settings(settings)
    first, observation_end = _local(start), _local(end)
    if first >= observation_end:
        raise ValueError("start must precede the observed-through end")
    events, ignored = _request_events(requests, facilities, config, first, observation_end)
    keys = tuple(_hospital_keys(facilities, config))
    timestamps = {key: [event[0] for event in values] for key, values in events.items()}
    counts = dict.fromkeys((
        "scheduled_window_count", "evaluated_window_count", "censored_window_count",
        "alert_count", "evaluated_alert_count", "censored_alert_count",
        "known_snapshot_exposure_count", "unknown_snapshot_exposure_count",
        "evaluated_request_count", "observed_unmet_request_count",
        "detected_unmet_request_count", "missed_unmet_request_count",
        "true_positive_alert_count", "false_positive_alert_count",
        "requests_excluded_missing_snapshot", "unmet_requests_excluded_missing_snapshot",
        "requests_excluded_censoring", "unmet_requests_excluded_censoring",
    ), 0)
    day = first.date()
    while day <= observation_end.date():
        cutoff = datetime.combine(day, time(config.run_hour), tzinfo=EAT)
        day += timedelta(days=1)
        if not first <= cutoff < observation_end:
            continue
        counts["scheduled_window_count"] += 1
        window_end = cutoff + timedelta(hours=config.horizon_hours)
        censored = window_end > observation_end
        counts["censored_window_count" if censored else "evaluated_window_count"] += 1
        stock_day = cutoff.date() - timedelta(days=1)
        for key in keys:
            units = _stock_value(stock, stock_day, key)
            is_alert = units == 0
            counts["alert_count"] += int(is_alert)
            times = timestamps.get(key, ())
            left = bisect_left(times, cutoff)
            right = bisect_left(times, min(window_end, observation_end))
            window_events = events.get(key, ())[left:right]
            request_count = len(window_events)
            unmet = sum(event[1] for event in window_events)
            if censored:
                counts["censored_alert_count"] += int(is_alert)
                counts["requests_excluded_censoring"] += request_count
                counts["unmet_requests_excluded_censoring"] += unmet
                continue
            if units is None:
                counts["unknown_snapshot_exposure_count"] += 1
                counts["requests_excluded_missing_snapshot"] += request_count
                counts["unmet_requests_excluded_missing_snapshot"] += unmet
                continue
            counts["known_snapshot_exposure_count"] += 1
            counts["evaluated_request_count"] += request_count
            counts["observed_unmet_request_count"] += unmet
            if is_alert:
                counts["evaluated_alert_count"] += 1
                counts["true_positive_alert_count" if unmet else "false_positive_alert_count"] += 1
                counts["detected_unmet_request_count"] += unmet
            else:
                counts["missed_unmet_request_count"] += unmet
    precision_denominator = counts["evaluated_alert_count"]
    recall_denominator = counts["observed_unmet_request_count"]
    return {
        "evaluation_period": {"start": first.isoformat(), "end_exclusive": observation_end.isoformat()},
        "settings": {
            "blood_groups": list(config.blood_groups),
            "components": list(config.components),
            "run_hour": config.run_hour,
            "horizon_hours": config.horizon_hours,
            "max_snapshot_age_days": config.max_snapshot_age_days,
        },
        "metrics": {
            **counts,
            "precision": counts["true_positive_alert_count"] / precision_denominator if precision_denominator else None,
            "precision_denominator_alerts": precision_denominator,
            "recall": counts["detected_unmet_request_count"] / recall_denominator if recall_denominator else None,
            "recall_denominator_unmet_requests": recall_denominator,
        },
        "ignored_requests": ignored,
        "assumptions": _assumptions(config),
        "limitations": [
            "Stock is a prior-day closing observation, not verified live inventory.",
            "The dataset generator omits stock series that are zero throughout the year; "
            "missing records are conservatively treated as unknown, not inferred zero.",
            "Only exact configured group/component demand and emergency/urgent requests are evaluated.",
            "Unmet means units_issued < units_requested; this is retrospective association, not a cause attribution.",
            "No supply, replenishment transport, or prevention benefit is simulated.",
            "Complete daily windows only; observations outside those windows do not enter metric denominators.",
        ],
    }


__all__ = ["generate_prealerts", "evaluate_prealerts"]
