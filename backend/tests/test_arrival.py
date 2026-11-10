"""Arrival tests use hand-computable batches, never generated success metrics."""

import copy
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.arrival import ArrivalModel, estimate_arrival, evaluate_arrival_model, fit_arrival_model


def fixture_rows(wait=2, transit=1, *, date="2026-01-01", request_id="R1"):
    requested = datetime.fromisoformat(date + "T10:00:00")
    dispatched = requested + timedelta(hours=wait)
    received = dispatched + timedelta(hours=transit)
    request = {"request_id": request_id, "facility_id": "HSP-001", "requested_at": requested.isoformat()}
    transfer = {
        "transfer_id": "T-" + request_id,
        "unit_id": "U-" + request_id,
        "transfer_type": "emergency_request",
        "request_id": request_id,
        "from_facility_id": "RBTC-001",
        "to_facility_id": "HSP-001",
        "dispatched_at": dispatched.isoformat(),
        "received_at": received.isoformat(),
    }
    routes = {("RBTC-001", "HSP-001"): {"typical_travel_hours": "1.0"}}
    return [request], [transfer], routes


def fitted(*, min_samples=1):
    requests, transfers, routes = fixture_rows()
    return fit_arrival_model(requests, transfers, routes, trained_before=datetime(2026, 2, 1), min_samples=min_samples)


def test_exact_empirical_quantiles_preserve_wait_transport_pairing():
    # Both observed journeys took 10h. Independently mixing the marginals would
    # invent 0h/20h journeys, which paired observations correctly avoid.
    model = ArrivalModel(((0, 10), (10, 0)), datetime(2026, 2, 1), min_samples=2)
    estimate = estimate_arrival(1, model=model)
    assert (estimate["p10_hours"], estimate["p50_hours"], estimate["p90_hours"]) == (10, 10, 10)
    assert estimate["interval_probability"] == 0.8
    assert estimate["time_origin"] == "request_submission"
    assert estimate["arrival_endpoint"] == "receiving_facility"


def test_linear_quantiles_are_ordered_and_reproducible():
    model = ArrivalModel(((0, 1), (0, 2), (0, 3), (0, 4)), datetime(2026, 2, 1), min_samples=4)
    first = estimate_arrival(2, model=model)
    assert first["p10_hours"] == pytest.approx(2.6)
    assert first["p50_hours"] == 5
    assert first["p90_hours"] == pytest.approx(7.4)
    assert first == estimate_arrival(2, model=model)
    assert first["model_used"] is True


def test_fit_uses_last_received_units_own_dispatch_not_independent_maximum():
    requests, transfers, routes = fixture_rows(wait=1, transit=4)
    later_dispatch = dict(transfers[0], unit_id="U2", dispatched_at="2026-01-01T12:00:00", received_at="2026-01-01T14:00:00")
    # First unit arrives last at 15:00; its dispatch was 11:00 (not 12:00).
    model = fit_arrival_model(requests, transfers + [later_dispatch], routes, trained_before=datetime(2026, 2, 1), min_samples=1)
    assert model.samples == ((1, 4),)
    assert model.sample_count == 1
    assert model.exclusions["collapsed_unit_rows"] == 1
    assert estimate_arrival(1, model=model)["p50_hours"] == 5


def test_repeated_unit_rows_do_not_inflate_sample_count():
    requests, transfers, routes = fixture_rows()
    model = fit_arrival_model(requests, transfers * 4, routes, trained_before=datetime(2026, 2, 1), min_samples=2)
    assert model.sample_count == 1
    assert estimate_arrival(1, model=model)["model_used"] is False
    assert model.exclusions["collapsed_unit_rows"] == 3


def test_partial_request_still_has_observed_batch_completion():
    requests, transfers, routes = fixture_rows()
    requests[0].update(outcome="partially_fulfilled", units_requested="3", units_issued="1")
    model = fit_arrival_model(requests, transfers, routes, trained_before=datetime(2026, 2, 1), min_samples=1)
    assert model.sample_count == 1
    assert estimate_arrival(1, model=model)["unit_of_analysis"] == "request_source_batch_last_receipt"


def test_missing_receipt_excludes_entire_batch():
    requests, transfers, routes = fixture_rows()
    transfers.append(dict(transfers[0], unit_id="U2", received_at=""))
    model = fit_arrival_model(requests, transfers, routes, trained_before=datetime(2026, 2, 1))
    assert model.sample_count == 0
    assert model.exclusions["missing_or_invalid_timestamp_shipments"] == 1


@pytest.mark.parametrize("field,value", [
    ("dispatched_at", ""),
    ("received_at", "2026-01-01T09:00:00"),
    ("dispatched_at", "2026-01-01T09:00:00"),
    ("to_facility_id", "HSP-OTHER"),
    ("request_id", "missing"),
    ("transfer_type", "routine"),
])
def test_invalid_or_unrelated_transfers_are_not_training_samples(field, value):
    requests, transfers, routes = fixture_rows()
    transfers[0][field] = value
    model = fit_arrival_model(requests, transfers, routes, trained_before=datetime(2026, 2, 1))
    assert model.sample_count == 0


def test_future_receipt_not_usable_even_when_request_was_before_training_cutoff():
    requests, transfers, routes = fixture_rows(date="2026-01-31")
    transfers[0]["received_at"] = "2026-02-01T00:00:00"
    model = fit_arrival_model(requests, transfers, routes, trained_before=datetime(2026, 2, 1))
    assert model.sample_count == 0
    assert model.exclusions["receipt_at_or_after_cutoff_shipments"] == 1


def test_request_exactly_at_cutoff_is_excluded():
    requests, transfers, routes = fixture_rows(date="2026-02-01")
    model = fit_arrival_model(requests, transfers, routes, trained_before=datetime(2026, 2, 1, 10))
    assert model.sample_count == 0


def test_duplicate_request_ids_are_ambiguous_and_excluded():
    requests, transfers, routes = fixture_rows()
    model = fit_arrival_model(requests * 2, transfers, routes, trained_before=datetime(2026, 2, 1))
    assert model.sample_count == 0
    assert model.exclusions["unlinked_or_ambiguous_request_rows"] == 1


@pytest.mark.parametrize("route", [None, {}, {"typical_travel_hours": ""}, {"typical_travel_hours": 0}, {"typical_travel_hours": -1}, {"typical_travel_hours": math.nan}])
def test_missing_or_invalid_route_is_counted_without_inventing_zero_travel(route):
    requests, transfers, _ = fixture_rows()
    routes = {} if route is None else {("RBTC-001", "HSP-001"): route}
    model = fit_arrival_model(requests, transfers, routes, trained_before=datetime(2026, 2, 1))
    assert model.sample_count == 0
    assert model.exclusions["missing_or_invalid_route_shipments"] == 1


def test_aware_utc_and_naive_eat_timestamps_have_same_result():
    requests, transfers, routes = fixture_rows()
    naive = fit_arrival_model(requests, transfers, routes, trained_before=datetime(2026, 2, 1), min_samples=1)
    requests[0]["requested_at"] = "2026-01-01T07:00:00Z"
    transfers[0]["dispatched_at"] = "2026-01-01T09:00:00+00:00"
    transfers[0]["received_at"] = "2026-01-01T10:00:00+00:00"
    aware = fit_arrival_model(requests, transfers, routes, trained_before=datetime(2026, 1, 31, 21, tzinfo=timezone.utc), min_samples=1)
    assert naive.samples == aware.samples
    assert naive.trained_before == aware.trained_before


def test_configured_fallback_has_no_fabricated_interval():
    estimate = estimate_arrival(3, settings={"arrival": {"dispatch_wait_hours": 1, "road_time_multiplier": 2}})
    assert estimate["p50_hours"] == 7
    assert estimate["p10_hours"] is None
    assert estimate["p90_hours"] is None
    assert estimate["interval_probability"] is None
    assert estimate["model_used"] is False


def test_hospital_lending_is_explicitly_labelled_extrapolation():
    estimate = estimate_arrival(1, model=fitted(), source_kind="hospital")
    assert "hospital_lending_extrapolation_not_validated" in estimate["warnings"]


@pytest.mark.parametrize("travel", [-1, math.nan, math.inf, None, True, "unknown"])
def test_invalid_travel_fails_loudly(travel):
    with pytest.raises(ValueError, match="travel_hours"):
        estimate_arrival(travel)


def test_invalid_configuration_fails_loudly():
    with pytest.raises(ValueError, match="dispatch_wait_hours"):
        estimate_arrival(1, settings={"arrival": {"dispatch_wait_hours": -1}})
    with pytest.raises(ValueError, match="settings.arrival"):
        estimate_arrival(1, settings={"arrival": None})
    with pytest.raises(ValueError, match="source_kind"):
        estimate_arrival(1, source_kind="unknown")
    with pytest.raises(ValueError, match="overflowed"):
        estimate_arrival(1e308, settings={"arrival": {"road_time_multiplier": 100}})


def test_model_persistence_retains_predictions_and_metadata(tmp_path):
    model = fitted()
    path = tmp_path / "arrival.json"
    model.save(path)
    reloaded = ArrivalModel.load(path)
    assert model.to_dict() == reloaded.to_dict()
    assert estimate_arrival(4, model=model) == estimate_arrival(4, model=reloaded)
    assert json.loads(path.read_text())["schema_version"] == 1


@pytest.mark.parametrize("change", [
    {"schema_version": 999}, {"schema_version": True}, {"model_type": "unknown"}, {"min_samples": 0},
    {"seed": True}, {"samples": [[-1, 1]]}, {"samples": [[0, math.inf]]},
    {"samples": [[1]]}, {"trained_before": "invalid"}, {"exclusions": {"invalid": -1}},
    {"samples": ["12"]}, {"samples": "12"},
])
def test_invalid_persistence_is_rejected(change):
    payload = copy.deepcopy(fitted().to_dict())
    payload.update(change)
    with pytest.raises(ValueError):
        ArrivalModel.from_dict(payload)


def test_validation_metrics_are_calculated_on_later_batches_only():
    model = fitted()  # Predicts 3h for 1h map travel; interval is [3,3].
    req1, tr1, routes = fixture_rows(wait=2, transit=1, date="2026-02-05", request_id="test1")
    req2, tr2, _ = fixture_rows(wait=3, transit=1, date="2026-02-06", request_id="test2")
    train_req, train_tr, _ = fixture_rows()
    report = evaluate_arrival_model(
        model, req1 + req2 + train_req, tr1 + tr2 + train_tr, routes,
        start=datetime(2026, 2, 1), end=datetime(2026, 3, 1),
    )
    assert report["sample_count"] == 2
    assert report["interval_sample_count"] == 2
    assert report["metrics"]["mean_absolute_error_hours"] == 0.5
    assert report["metrics"]["median_absolute_error_hours"] == 0.5
    assert report["metrics"]["p10_p90_coverage"] == 0.5
    assert report["metrics"]["fraction_after_p90"] == 0.5
    assert report["metrics"]["mean_interval_width_hours"] == 0
    assert report["metrics"]["baseline_map_plus_2_mean_absolute_error_hours"] == 0.5
    assert report["exclusions"]["outside_request_window_shipments"] == 1


def test_no_evaluation_samples_means_null_metrics_not_zero_error():
    report = evaluate_arrival_model(fitted(), [], [], {}, start=datetime(2026, 2, 1), end=datetime(2026, 3, 1))
    assert report["sample_count"] == 0
    assert report["metrics"]["mean_absolute_error_hours"] is None
    assert report["metrics"]["p10_p90_coverage"] is None


def test_censored_evaluation_batch_is_counted_and_not_used_as_zero_duration():
    requests, transfers, routes = fixture_rows(date="2026-02-28")
    transfers[0]["received_at"] = "2026-03-01T00:00:00"
    report = evaluate_arrival_model(fitted(), requests, transfers, routes, start=datetime(2026, 2, 1), end=datetime(2026, 3, 1))
    assert report["sample_count"] == 0
    assert report["metrics"]["mean_absolute_error_hours"] is None
    assert report["exclusions"]["receipt_at_or_after_cutoff_shipments"] == 1


def test_outside_evaluation_period_missing_receipt_does_not_inflate_censoring():
    requests, transfers, routes = fixture_rows(date="2026-01-01")
    transfers[0]["received_at"] = ""
    report = evaluate_arrival_model(fitted(), requests, transfers, routes, start=datetime(2026, 2, 1), end=datetime(2026, 3, 1))
    assert report["exclusions"]["outside_request_window_shipments"] == 1
    assert report["exclusions"].get("missing_or_invalid_timestamp_shipments", 0) == 0


def test_insufficient_model_still_evaluates_fallback_without_coverage():
    requests, transfers, routes = fixture_rows(date="2026-02-10")
    report = evaluate_arrival_model(fitted(min_samples=20), requests, transfers, routes, start=datetime(2026, 2, 1), end=datetime(2026, 3, 1))
    assert report["sample_count"] == 1
    assert report["interval_sample_count"] == 0
    assert report["metrics"]["p10_p90_coverage"] is None
    assert report["metrics"]["mean_absolute_error_hours"] == pytest.approx(0.2)


def test_training_and_evaluation_overlap_is_rejected():
    with pytest.raises(ValueError, match="overlap"):
        evaluate_arrival_model(fitted(), [], [], {}, start=datetime(2026, 1, 1), end=datetime(2026, 3, 1))


def test_inverted_evaluation_period_is_rejected():
    with pytest.raises(ValueError, match="after start"):
        evaluate_arrival_model(fitted(), [], [], {}, start=datetime(2026, 3, 1), end=datetime(2026, 2, 1))
