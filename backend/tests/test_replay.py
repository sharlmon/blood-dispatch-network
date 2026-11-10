"""Counterfactual-policy invariants, using small and explainable stock fixtures."""

from datetime import date, datetime

import pytest

from engine.arrival import ArrivalModel
from engine.dataset import Dataset
from engine.replay import Candidate, ReferenceCandidateProvider, run_replay

DAY = date(2026, 9, 1)
START, END = datetime(2026, 9, 2), datetime(2026, 9, 3)


def dataset():
    facilities = {"HSP-1": {"facility_type": "county_hospital", "supply_centre_id": "RBTC-1"},
                  "HSP-2": {"facility_type": "county_hospital", "supply_centre_id": "RBTC-1"}}
    facilities.update({f"RBTC-{index}": {"facility_type": "regional_blood_centre"} for index in range(1, 5)})
    facilities["SAT-1"] = {"facility_type": "satellite_blood_centre"}
    routes = {(source, "HSP-1"): {"road_km": str(distance), "typical_travel_hours": str(distance / 30)}
              for source, distance in (("RBTC-1", 120), ("RBTC-2", 90), ("RBTC-3", 100),
                                       ("RBTC-4", 110), ("HSP-2", 15), ("SAT-1", 1))}
    stock = {(DAY, fid, "RBC", "O+"): 0 for fid in facilities}
    stock[(DAY, "RBTC-4", "RBC", "O+")] = 10
    stock[(DAY, "HSP-2", "RBC", "O+")] = 8
    request = {"request_id": "REQ-1", "facility_id": "HSP-1", "requested_at": "2026-09-02T12:00:00",
               "patient_blood_group": "O+", "component_requested": "RBC", "units_requested": "2",
               "units_issued": "0", "outcome": "not_fulfilled", "urgency": "emergency",
               "last_unit_available_at": ""}
    return Dataset(facilities, routes, [request], [], stock, {})


def test_ladder_baseline_checks_nearest_before_stock_and_hospitals_require_reserve():
    data = dataset()
    settings = {"replay": {"hospital_reserve_units": {"O+": 5}}}
    result = run_replay(data, start=START, end=END, settings=settings)
    policies = result["policies"]
    assert policies["baseline"]["no_source_found"] == 1
    assert policies["all_centres"]["full_source_found"] == 1
    assert policies["centres_and_hospitals"]["hospital_sources_selected"] == 1
    assert policies["centres_and_hospitals"]["previously_unfulfilled_p50_opportunities"] == 1
    assert result["evaluation_type"] == "independent_request_snapshot_feasibility"


def test_hospitals_disabled_without_explicit_reserves_and_lending_flag():
    data = dataset()
    provider = ReferenceCandidateProvider(data)
    assert all(row.source_kind == "centre" for row in provider(data.requests[0], START, include_hospitals=True))
    provider = ReferenceCandidateProvider(data, {"lending": {"enabled": False},
                                               "replay": {"hospital_reserve_units": {"O+": 1}}})
    assert all(row.source_kind == "centre" for row in provider(data.requests[0], START, include_hospitals=True))


def test_partial_never_counts_as_full_and_unknown_groups_require_review():
    data = dataset()
    data.stock[(DAY, "RBTC-4", "RBC", "O+")] = 1
    result = run_replay(data, start=START, end=END)
    assert result["policies"]["all_centres"]["partial_source_only"] == 1
    assert result["policies"]["all_centres"]["full_source_p50_within_deadline"] == 0
    data.requests[0]["patient_blood_group"] = "unknown"
    result = run_replay(data, start=START, end=END)
    assert result["exclusions"]["unknown_group_requires_human_review"] == 1
    assert result["policies"]["all_centres"]["evaluated_requests"] == 0


def test_missing_prior_stock_is_not_zero_and_current_stock_cannot_leak():
    data = dataset()
    del data.stock[(DAY, "HSP-1", "RBC", "O+")]
    data.stock[(START.date(), "HSP-1", "RBC", "O+")] = 0
    result = run_replay(data, start=START, end=END)
    assert result["exclusions"]["missing_requester_prior_day_snapshot"] == 1


def test_partial_observed_bedside_time_not_counted_as_complete():
    data = dataset()
    data.requests[0].update(outcome="partially_fulfilled", units_issued="1",
                            last_unit_available_at="2026-09-02T14:00:00")
    result = run_replay(data, start=START, end=END)
    assert result["observed_fully_served_timing_count"] == 0
    assert result["observed_fully_served_median_bedside_hours"] is None


def test_observed_completions_after_period_are_censored():
    data = dataset()
    data.requests[0].update(outcome="fulfilled", units_issued="2",
                            last_unit_available_at="2026-09-03T02:00:00")
    result = run_replay(data, start=START, end=END)
    assert result["observed_fully_served_timing_count"] == 0
    assert result["observed_timing_exclusions"]["completion_at_or_after_end"] == 1


def test_injected_ds1_provider_is_used_and_compared_on_paired_requests():
    data = dataset()
    calls = []
    def approved_provider(request, as_of, *, include_hospitals):
        calls.append((request["request_id"], as_of, include_hospitals))
        return [Candidate("RBTC-1", 2, 4, 120), Candidate("HSP-2", 2, .5, 15, "hospital")]
    result = run_replay(data, start=START, end=END, candidate_provider=approved_provider)
    assert len(calls) == 1
    assert result["paired_comparison"]["requests"] == 1
    assert result["paired_comparison"]["mean_p50_hours_saved"] == pytest.approx(4.2)


def test_model_training_cannot_overlap_replay():
    with pytest.raises(ValueError, match="trained before"):
        run_replay(dataset(), start=START, end=END,
                   model=ArrivalModel(samples=(), trained_before=END))


def test_reference_never_lends_o_negative_or_satellites():
    data = dataset()
    data.requests[0]["patient_blood_group"] = "O-"
    data.stock[(DAY, "HSP-2", "RBC", "O-")] = 100
    data.stock[(DAY, "SAT-1", "RBC", "O-")] = 100
    provider = ReferenceCandidateProvider(data, {"replay": {"hospital_reserve_units": {"O-": 0}}})
    assert provider(data.requests[0], START, include_hospitals=True) == []


@pytest.mark.parametrize("travel", [-1, float("nan"), float("inf")])
def test_invalid_candidate_travel_rejected(travel):
    with pytest.raises(ValueError):
        Candidate("RBTC-1", 2, travel, 20)


@pytest.mark.parametrize("quantity", [True, 1.5, float("nan"), -1])
def test_invalid_candidate_quantity_rejected(quantity):
    with pytest.raises(ValueError):
        Candidate("RBTC-1", quantity, 1, 20)


def test_injected_duplicate_sources_rejected():
    def duplicate_provider(request, as_of, *, include_hospitals):
        return [Candidate("RBTC-1", 1, 1, 20)] * 2
    with pytest.raises(ValueError, match="duplicate facilities"):
        run_replay(dataset(), start=START, end=END, candidate_provider=duplicate_provider)
