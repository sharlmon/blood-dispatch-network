"""DS1's candidate rules plugged into the DS2 replay (docs/ds2-implementation.md, "Replay ladder")."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from engine import config
from engine.dataset import Dataset
from engine.load import frames_from_tables, red_stock_frame
from engine.replay import Candidate, DS1CandidateProvider, ReferenceCandidateProvider, run_replay

CFG = config.load_config("kenya")

# (facility_id, facility_type, supply_centre_id)
FACILITIES = [
    ("RBTC-A", "regional_blood_centre", None),
    ("RBTC-B", "regional_blood_centre", None),
    ("HSP-R", "county_referral", "RBTC-A"),  # the requester
    ("HSP-B", "county_referral", "RBTC-A"),
    ("HSP-N", "county_hospital", "RBTC-A"),  # no route on file to HSP-R
    ("SAT-S", "satellite_blood_centre", "RBTC-A"),
]
# Routes to HSP-R: source -> (typical_travel_hours, road_km)
ROUTES = {"RBTC-A": (2.0, 100.0), "RBTC-B": (4.0, 200.0), "HSP-B": (1.0, 40.0), "SAT-S": (0.2, 5.0)}
DAY_BEFORE, REQUEST_DAY = "2026-03-09", "2026-03-10"
SUBMITTED = datetime(2026, 3, 10, 1, 0)  # naive EAT, as run_replay passes it
REQUEST = {"request_id": "REQ-1", "facility_id": "HSP-R", "requested_at": "2026-03-10T01:00:00",
           "patient_blood_group": "O+", "component_requested": "RBC", "units_requested": "2",
           "units_issued": "0", "urgency": "emergency", "outcome": "not_fulfilled",
           "last_unit_available_at": ""}


def on(day, *rows):
    """daily_stock rows (date, facility, component, group, units) for one day."""
    return [(day, *row) for row in rows]


def make_frames(stock_rows, usual_rows=()):
    """DS1's frames, with red cell stock built from daily_stock rows the way build_db does."""
    daily = pd.DataFrame(list(stock_rows), columns=["date", "facility_id", "component", "blood_group",
                                                    "units_in_stock_end_of_day"])
    facilities = pd.DataFrame(
        [(fid, fid, kind, supply, True, "4G") for fid, kind, supply in FACILITIES],
        columns=["facility_id", "name", "facility_type", "supply_centre_id",
                 "has_blood_fridge_backup_power", "connectivity"],
    )
    routes = pd.DataFrame([(source, "HSP-R", km, hours) for source, (hours, km) in ROUTES.items()],
                          columns=["from_facility_id", "to_facility_id", "road_km", "typical_travel_hours"])
    units = pd.DataFrame(columns=["component", "current_facility_id", "blood_group",
                                  "collection_date", "expiry_date", "status_date"])
    usual = pd.DataFrame(list(usual_rows), columns=["facility_id", "blood_group", "usual_level"])
    return frames_from_tables(facilities, routes, units, red_stock_frame(daily), usual)


def make_dataset(stock_rows, request=REQUEST):
    """The same tables as DS2 sees them, for the reference provider and run_replay."""
    facilities = {fid: {"facility_id": fid, "facility_type": kind, "supply_centre_id": supply or ""}
                  for fid, kind, supply in FACILITIES}
    routes = {(source, "HSP-R"): {"typical_travel_hours": str(hours), "road_km": str(km)}
              for source, (hours, km) in ROUTES.items()}
    stock = {(date.fromisoformat(day), fid, component, group): units
             for day, fid, component, group, units in stock_rows}
    return Dataset(facilities, routes, [dict(request)], [], stock, {})


def offered(frames, request=REQUEST, as_of=SUBMITTED, include_hospitals=True, cfg=CFG):
    provider = DS1CandidateProvider(frames, cfg)
    return {c.facility_id: c for c in provider(request, as_of, include_hospitals=include_hospitals)}


def test_compatible_groups_and_whole_blood_count_unlike_exact_match():
    rows = on(DAY_BEFORE, ("RBTC-A", "RBC", "O+", 1), ("RBTC-A", "RBC", "O-", 1), ("RBTC-A", "RBC", "A+", 50),
              ("RBTC-B", "RBC", "O+", 1), ("RBTC-B", "WB", "O+", 2))
    ds1 = offered(make_frames(rows))
    assert ds1["RBTC-A"].available_units == 2  # O+ and O- from the fixed table; A+ never counts
    assert ds1["RBTC-B"].available_units == 3  # RBC and WB pooled as red cell supply
    reference = ReferenceCandidateProvider(make_dataset(rows))(REQUEST, SUBMITTED, include_hospitals=True)
    assert {c.facility_id: c.available_units for c in reference} == {"RBTC-A": 1, "RBTC-B": 1}


def test_hospitals_keep_their_safety_stock_and_centres_lend_everything():
    rows = on(DAY_BEFORE, ("HSP-B", "RBC", "O+", 10), ("HSP-B", "RBC", "O-", 3), ("RBTC-A", "RBC", "O+", 5))
    frames = make_frames(rows, usual_rows=[("HSP-B", "O+", 4), ("HSP-B", "O-", 0), ("RBTC-A", "O+", 50)])
    found = offered(frames)
    assert found["HSP-B"].available_units == 6 + 1  # O+ keeps its usual level 4; O- keeps min_keep 2
    assert found["HSP-B"].source_kind == "hospital"
    assert found["RBTC-A"].available_units == 5  # a centre's usual level holds nothing back
    assert found["RBTC-A"].source_kind == "centre"
    assert offered(frames, cfg={**CFG, "o_neg_reserve": 3})["HSP-B"].available_units == 6  # O- reserve keeps all 3


def test_without_hospitals_or_sharing_only_centres_are_offered():
    frames = make_frames(on(DAY_BEFORE, ("HSP-B", "RBC", "O+", 10), ("RBTC-A", "RBC", "O+", 5)))
    assert set(offered(frames)) == {"HSP-B", "RBTC-A"}
    assert set(offered(frames, include_hospitals=False)) == {"RBTC-A"}
    assert set(offered(frames, cfg={**CFG, "sharing_allowed": False})) == {"RBTC-A"}


def test_requester_satellites_and_sites_with_nothing_to_lend_are_never_offered():
    rows = on(DAY_BEFORE,
              ("HSP-R", "RBC", "O+", 99),  # the requester itself
              ("SAT-S", "RBC", "O+", 99),  # satellites never lend, even with stock
              ("HSP-N", "RBC", "O+", 99),  # no route on file to HSP-R
              ("HSP-B", "RBC", "O+", 4),   # exactly at its safety stock
              ("RBTC-B", "RBC", "O+", 0),  # empty shelf
              ("RBTC-A", "RBC", "O+", 1))
    found = offered(make_frames(rows, usual_rows=[("HSP-B", "O+", 4)]))
    assert list(found) == ["RBTC-A"]
    assert found["RBTC-A"] == Candidate("RBTC-A", 1, 2.0, 100.0, "centre")


def test_previous_day_snapshot_matches_the_reference_provider():
    # O- RBC at a centre: both providers count the same units, so only the day can differ.
    rows = [(day, "RBTC-A", "RBC", "O-", units)
            for day, units in (("2026-03-08", 9), (DAY_BEFORE, 3), (REQUEST_DAY, 20))]
    request = {**REQUEST, "patient_blood_group": "O-"}
    ds1 = DS1CandidateProvider(make_frames(rows), CFG)(request, SUBMITTED, include_hospitals=True)
    reference = ReferenceCandidateProvider(make_dataset(rows))(request, SUBMITTED, include_hospitals=True)
    assert ds1 == reference == [Candidate("RBTC-A", 3, 2.0, 100.0, "centre")]


def test_offset_aware_time_gives_the_same_result_as_naive_eat():
    frames = make_frames(on("2026-03-08", ("RBTC-A", "RBC", "O+", 7)) + on(DAY_BEFORE, ("RBTC-A", "RBC", "O+", 3)))
    utc = datetime(2026, 3, 9, 22, 0, tzinfo=timezone.utc)  # 01:00 EAT on the request day
    assert offered(frames, as_of=utc) == offered(frames, as_of=SUBMITTED)
    assert offered(frames, as_of=utc)["RBTC-A"].available_units == 3
    # Read as a naive time, 22:00 on 9 March would wrongly use the 8 March count.
    assert offered(frames, as_of=utc.replace(tzinfo=None))["RBTC-A"].available_units == 7


def test_a_later_count_is_refused_but_the_last_earlier_count_is_used():
    frames = make_frames(on(REQUEST_DAY, ("RBTC-A", "RBC", "O+", 5)))
    with pytest.raises(ValueError, match="later 2026-03-10 count"):
        offered(frames)  # before the data starts DS1 would read the request day's own close
    # After the data ends DS1 uses the last count, which was known at request time.
    assert offered(frames, as_of=datetime(2026, 3, 14, 1))["RBTC-A"].available_units == 5


@pytest.mark.parametrize("component", ["WB", "PLT", "FFP"])
def test_components_outside_ds1_scope_are_refused(component):
    frames = make_frames(on(DAY_BEFORE, ("RBTC-A", "RBC", "O+", 5), ("RBTC-A", "WB", "O+", 5)))
    with pytest.raises(ValueError, match="RBC"):
        offered(frames, request={**REQUEST, "component_requested": component})


def test_run_replay_refuses_a_cohort_ds1_cannot_rank():
    # A WB request the requester is short of. Offering no candidates would score DS1
    # "no source found" against the reference, which finds the centre's 5 units.
    rows = on(DAY_BEFORE, ("HSP-R", "WB", "O+", 0), ("RBTC-A", "WB", "O+", 5))
    data = make_dataset(rows, request={**REQUEST, "component_requested": "WB"})
    window = {"start": datetime(2026, 3, 10), "end": datetime(2026, 3, 11),
              "settings": {"replay": {"components": ["RBC", "WB"]}}}
    assert run_replay(data, **window)["policies"]["baseline"]["full_source_found"] == 1
    with pytest.raises(ValueError, match=r"set replay.components to \[RBC\]"):
        run_replay(data, **window, candidate_provider=DS1CandidateProvider(make_frames(rows), CFG))


def test_config_must_carry_ds1_stock_settings():
    frames = make_frames(on(DAY_BEFORE, ("RBTC-A", "RBC", "O+", 5)))
    with pytest.raises(ValueError, match="min_keep, o_neg_reserve, near_expiry_days"):
        DS1CandidateProvider(frames, {"sharing_allowed": True})


def test_run_replay_compares_ds1_with_the_reference_on_the_same_requests():
    rows = on(DAY_BEFORE, ("HSP-R", "RBC", "O+", 0),  # the requester is short, so the request is replayed
              ("RBTC-A", "RBC", "O+", 1), ("RBTC-A", "RBC", "O-", 1))
    data = make_dataset(rows)
    start, end = datetime(2026, 3, 10), datetime(2026, 3, 11)
    reference = run_replay(data, start=start, end=end)
    ds1 = run_replay(data, start=start, end=end, candidate_provider=DS1CandidateProvider(make_frames(rows), CFG))
    assert reference["candidate_provider"] == "ReferenceCandidateProvider"
    assert ds1["candidate_provider"] == "DS1CandidateProvider"
    for result in (reference, ds1):
        assert result["policies"]["baseline"]["evaluated_requests"] == 1
    # The supply centre has 1 exact-match O+ unit for 2 needed; with its O- unit it covers both.
    assert reference["policies"]["baseline"]["partial_source_only"] == 1
    assert ds1["policies"]["baseline"]["full_source_found"] == 1
