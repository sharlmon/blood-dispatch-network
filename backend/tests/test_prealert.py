"""Contract and leakage checks for the evening shortage review rule."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.prealert import evaluate_prealerts, generate_prealerts


FACILITIES = {"HSP-001": {"name": "Hospital"}, "HSP-002": {}, "RBTC-001": {}}
DAY = date(2026, 1, 1)
START = datetime(2026, 1, 2, 18)
END = datetime(2026, 1, 3, 18)


def stock(units, facility="HSP-001", component="RBC", group="O+", day=DAY):
    return {(day, facility, component, group): units}


def request(request_id="REQ-1", facility="HSP-001", issued=0, **changes):
    return {
        "request_id": request_id,
        "facility_id": facility,
        "requested_at": "2026-01-03 01:00:00",
        "urgency": "emergency",
        "patient_blood_group": "O+",
        "component_requested": "RBC",
        "units_requested": "2",
        "units_issued": str(issued),
        **changes,
    }


def evaluate(inventory, requests, **kwargs):
    return evaluate_prealerts(inventory, FACILITIES, requests, start=START, end=END, **kwargs)


def test_zero_generates_human_review_alert_missing_is_not_zero():
    result = generate_prealerts(stock(0), FACILITIES, as_of=START)
    assert result["stock_as_of"] == "2026-01-01"
    assert len(result["alerts"]) == 1
    alert = result["alerts"][0]
    assert alert["facility_id"] == "HSP-001"
    assert alert["recorded_units"] == 0
    assert alert["human_review_required"] is True
    assert alert["generated_at"].endswith("+03:00")
    assert result["missing_snapshot"][0]["facility_id"] == "HSP-002"


def test_only_yesterday_snapshot_is_used_never_older_current_or_future():
    inventory = {
        **stock(0, day=DAY - timedelta(days=1)),
        **stock(0, day=DAY + timedelta(days=1)),
        **stock(0, day=DAY + timedelta(days=2)),
    }
    result = generate_prealerts(inventory, {"HSP-001": {}}, as_of=START)
    assert result["alerts"] == []
    assert len(result["missing_snapshot"]) == 1
    inventory.update(stock(4))
    assert generate_prealerts(inventory, {"HSP-001": {}}, as_of=START)["alerts"] == []


def test_centres_never_alert_and_components_are_not_pooled():
    inventory = {**stock(0), **stock(8, component="WB"), **stock(0, facility="RBTC-001")}
    settings = {"prealert": {"components": ["RBC", "WB"]}}
    result = generate_prealerts(inventory, FACILITIES, as_of=START, settings=settings)
    assert [(row["facility_id"], row["component"]) for row in result["alerts"]] == [("HSP-001", "RBC")]
    assert len(result["missing_snapshot"]) == 2


def test_precision_counts_alerts_and_recall_counts_unmet_requests():
    inventory = {**stock(0), **stock(3, facility="HSP-002")}
    rows = [request(), request("REQ-2", issued=1), request("REQ-3", facility="HSP-002")]
    metrics = evaluate(inventory, rows)["metrics"]
    assert metrics["true_positive_alert_count"] == 1
    assert metrics["detected_unmet_request_count"] == 2
    assert metrics["missed_unmet_request_count"] == 1
    assert metrics["precision"] == 1
    assert metrics["precision_denominator_alerts"] == 1
    assert metrics["recall"] == pytest.approx(2 / 3)
    assert metrics["recall_denominator_unmet_requests"] == 3


def test_alert_without_matching_unmet_demand_is_false_positive():
    metrics = evaluate(stock(0), [request(issued=2)])["metrics"]
    assert metrics["false_positive_alert_count"] == 1
    assert metrics["precision"] == 0
    assert metrics["recall"] is None


def test_missing_snapshot_demand_is_excluded_not_counted_as_false_negative():
    metrics = evaluate({}, [request()])["metrics"]
    assert metrics["unmet_requests_excluded_missing_snapshot"] == 1
    assert metrics["missed_unmet_request_count"] == 0
    assert metrics["observed_unmet_request_count"] == 0
    assert metrics["unknown_snapshot_exposure_count"] == 2
    assert metrics["precision"] is None
    assert metrics["recall"] is None


def test_incomplete_final_window_is_censored_even_without_requests():
    result = evaluate_prealerts(stock(0), FACILITIES, [], start=START, end=END - timedelta(hours=1))
    metrics = result["metrics"]
    assert metrics["censored_window_count"] == 1
    assert metrics["censored_alert_count"] == 1
    assert metrics["evaluated_alert_count"] == 0
    assert metrics["false_positive_alert_count"] == 0
    assert metrics["precision"] is None


def test_censored_observed_demand_is_reported_without_entering_recall():
    result = evaluate_prealerts(stock(0), FACILITIES, [request()], start=START, end=END - timedelta(hours=1))
    metrics = result["metrics"]
    assert metrics["requests_excluded_censoring"] == 1
    assert metrics["unmet_requests_excluded_censoring"] == 1
    assert metrics["recall_denominator_unmet_requests"] == 0


def test_unknown_groups_and_routine_demand_do_not_create_positive_outcomes():
    rows = [request(patient_blood_group="unknown"), request("REQ-2", urgency="routine")]
    result = evaluate(stock(0), rows)
    assert result["metrics"]["false_positive_alert_count"] == 1
    assert result["ignored_requests"]["unknown_blood_group"] == 1
    assert result["ignored_requests"]["other_urgency"] == 1


def test_window_boundary_is_half_open_and_identical_rows_are_deduplicated():
    rows = [request(requested_at=START.isoformat()), request(requested_at=START.isoformat()), request("REQ-2", requested_at=END.isoformat())]
    result = evaluate(stock(0), rows)
    assert result["metrics"]["detected_unmet_request_count"] == 1
    assert result["ignored_requests"]["duplicate_request_id"] == 1
    assert result["ignored_requests"]["outside_observation_period"] == 1


def test_conflicting_duplicate_request_ids_are_rejected():
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        evaluate(stock(0), [request(), request(issued=1)])


def test_aware_timestamp_is_normalized_to_dataset_timezone():
    utc_cutoff = datetime(2026, 1, 2, 15, tzinfo=timezone.utc)
    assert generate_prealerts(stock(0), FACILITIES, as_of=utc_cutoff)["generated_at"] == "2026-01-02T18:00:00+03:00"


@pytest.mark.parametrize("config", [
    {"blood_groups": []}, {"blood_groups": ["unknown"]}, {"components": ["INVALID"]},
    {"run_hour": 24}, {"run_hour": True}, {"horizon_hours": 0},
    {"horizon_hours": 25}, {"horizon_hours": float("nan")},
    {"max_snapshot_age_days": 0},
])
def test_invalid_settings_are_rejected(config):
    with pytest.raises(ValueError):
        generate_prealerts(stock(0), FACILITIES, as_of=START, settings={"prealert": config})


@pytest.mark.parametrize("units", [-1, 1.5, True])
def test_invalid_stock_does_not_silently_become_a_shortage(units):
    with pytest.raises(ValueError, match="Stock must be"):
        generate_prealerts(stock(units), FACILITIES, as_of=START)


def test_empty_or_reversed_observation_period_is_rejected():
    with pytest.raises(ValueError, match="start must precede"):
        evaluate_prealerts({}, FACILITIES, [], start=START, end=START)


def test_invalid_requests_are_counted_and_no_raw_request_records_are_returned():
    result = evaluate(stock(0), [request(requested_at="bad timestamp"), request("REQ-2", units_issued="")])
    assert result["ignored_requests"]["invalid_time_or_quantity"] == 2
    assert "REQ-1" not in str(result)


def test_adjacent_daily_windows_count_boundary_request_once():
    inventory = {**stock(0), **stock(0, day=DAY + timedelta(days=1))}
    result = evaluate_prealerts(
        inventory, {"HSP-001": {}}, [request(requested_at=END.isoformat())],
        start=START, end=END + timedelta(days=1),
    )
    assert result["metrics"]["evaluated_window_count"] == 2
    assert result["metrics"]["detected_unmet_request_count"] == 1
    assert result["metrics"]["true_positive_alert_count"] == 1
    assert result["metrics"]["false_positive_alert_count"] == 1
