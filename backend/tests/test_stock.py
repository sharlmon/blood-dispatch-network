"""Step 3: previous-day snapshot, spare, near-expiry (spec section 6)."""

from __future__ import annotations

import time

import pandas as pd
import pytest

from engine import config, stock
from engine.load import frames_from_tables

CFG = config.load_config("kenya")

# --------------------------------------------------------------------------- tiny dataset
#
# Facilities: one regional centre, the requesting hospital, a lending hospital,
# a 2G hospital with no backup power, and a satellite.

FACILITIES = pd.DataFrame(
    [
        ("RBTC-A", "Centre A", "regional_blood_centre", None, True, "4G"),
        ("HSP-R", "Requesting Hospital", "county_referral", "RBTC-A", True, "4G"),
        ("HSP-B", "Lending Hospital", "county_referral", "RBTC-A", True, "4G"),
        ("HSP-C", "Remote Hospital", "county_hospital", "RBTC-A", False, "2G"),
        ("SAT-S", "Satellite", "satellite_blood_centre", "RBTC-A", True, "3G"),
    ],
    columns=["facility_id", "name", "facility_type", "supply_centre_id",
             "has_blood_fridge_backup_power", "connectivity"],
)

DAY_BEFORE, REQUEST_DAY = "2026-03-09", "2026-03-10"
REQUESTED_AT = f"{REQUEST_DAY} 01:00:00"


def make_frames(stock_rows, usual_rows=(), unit_rows=()):
    """stock_rows: (facility, group, units) on DAY_BEFORE (plus a zero day before it)."""
    red_stock = pd.DataFrame(
        [(DAY_BEFORE, f, g, n) for f, g, n in stock_rows]
        + [("2026-03-01", "RBTC-A", "O+", 0)],
        columns=["date", "facility_id", "blood_group", "units"],
    )
    usual = pd.DataFrame(list(usual_rows), columns=["facility_id", "blood_group", "usual_level"])
    units = pd.DataFrame(
        list(unit_rows),
        columns=["component", "current_facility_id", "blood_group",
                 "collection_date", "expiry_date", "status_date"],
    )
    routes = pd.DataFrame(columns=["from_facility_id", "to_facility_id", "road_km", "typical_travel_hours"])
    return frames_from_tables(FACILITIES, routes, units, red_stock, usual)


def run(frames, group="O+", cfg=CFG, requester="HSP-R"):
    as_of, cands = stock.candidates(frames, requester, group, REQUESTED_AT, cfg)
    return as_of, {c.facility_id: c for c in cands}


# --------------------------------------------------------------------------- as_of


def test_as_of_is_the_previous_day():
    fr = make_frames([("RBTC-A", "O+", 1)])
    assert stock.as_of_date(fr, REQUESTED_AT) == DAY_BEFORE
    assert stock.as_of_date(fr, f"{REQUEST_DAY}T23:59:59") == DAY_BEFORE


def test_as_of_after_the_data_ends_uses_the_last_count():
    fr = make_frames([("RBTC-A", "O+", 1)])
    assert stock.as_of_date(fr, "2026-12-25 03:00") == DAY_BEFORE


def test_as_of_before_the_data_starts_uses_the_first_count():
    fr = make_frames([("RBTC-A", "O+", 1)])
    assert stock.as_of_date(fr, "2026-01-01 03:00") == "2026-03-01"


# --------------------------------------------------------------------------- candidates


def test_requester_and_satellites_are_never_candidates():
    fr = make_frames([("HSP-R", "O+", 50), ("SAT-S", "O+", 50)])
    _, c = run(fr)
    assert set(c) == {"RBTC-A", "HSP-B", "HSP-C"}


def test_sharing_off_returns_centres_only():
    fr = make_frames([("HSP-B", "O+", 50)])
    _, c = run(fr, cfg={**CFG, "sharing_allowed": False})
    assert set(c) == {"RBTC-A"}


def test_unknown_requesting_facility_is_rejected():
    fr = make_frames([])
    with pytest.raises(ValueError, match="Unknown facility_id"):
        run(fr, requester="HSP-404")


# --------------------------------------------------------------------------- spare


def test_regional_centre_can_spare_all_compatible_stock():
    fr = make_frames([("RBTC-A", "O+", 7), ("RBTC-A", "O-", 3), ("RBTC-A", "A+", 40)],
                     usual_rows=[("RBTC-A", "O+", 50)])
    _, c = run(fr, group="O+")
    assert c["RBTC-A"].stock_seen == 10
    assert c["RBTC-A"].spare == 10
    assert c["RBTC-A"].is_hospital is False


@pytest.mark.parametrize(
    "stock_units, usual, expected",
    [
        (8, 5, 3),   # keeps its usual level of 5
        (3, 0, 1),   # usual level 0, still keeps min_keep = 2
        (2, 0, 0),   # exactly at min_keep
        (4, 9, 0),   # below its usual level: lends nothing
    ],
)
def test_hospital_keeps_max_of_usual_level_and_min_keep(stock_units, usual, expected):
    fr = make_frames([("HSP-B", "O+", stock_units)], usual_rows=[("HSP-B", "O+", usual)])
    _, c = run(fr)
    assert c["HSP-B"].spare == expected
    assert c["HSP-B"].stock_seen == stock_units
    assert c["HSP-B"].is_hospital is True


def test_spare_adds_up_across_compatible_groups():
    fr = make_frames([("HSP-B", "O+", 10), ("HSP-B", "O-", 6)],
                     usual_rows=[("HSP-B", "O+", 4), ("HSP-B", "O-", 1)])
    _, c = run(fr, group="O+")
    assert c["HSP-B"].spare_by_group == {"O+": 6, "O-": 4}
    assert c["HSP-B"].spare == 10


def test_o_negative_reserve_is_kept_and_flagged_when_it_binds():
    cfg = {**CFG, "o_neg_reserve": 4}
    fr = make_frames([("HSP-B", "O-", 5)], usual_rows=[("HSP-B", "O-", 0)])
    _, c = run(fr, group="O-", cfg=cfg)
    assert c["HSP-B"].spare == 1          # keeps 4, not just min_keep = 2
    assert "o_neg_reserve_applied" in c["HSP-B"].flags


def test_o_negative_reserve_not_flagged_when_safety_stock_already_covers_it():
    fr = make_frames([("HSP-B", "O-", 5)], usual_rows=[("HSP-B", "O-", 3)])
    _, c = run(fr, group="O-")             # default reserve 2 < usual 3
    assert c["HSP-B"].spare == 2
    assert "o_neg_reserve_applied" not in c["HSP-B"].flags


def test_o_negative_reserve_does_not_apply_to_centres():
    fr = make_frames([("RBTC-A", "O-", 3)])
    _, c = run(fr, group="O-", cfg={**CFG, "o_neg_reserve": 10})
    assert c["RBTC-A"].spare == 3


def test_incompatible_stock_is_ignored():
    fr = make_frames([("RBTC-A", "A+", 30), ("RBTC-A", "O+", 2)])
    _, c = run(fr, group="O+")
    assert c["RBTC-A"].stock_seen == 2
    assert set(c["RBTC-A"].stock_by_group) == {"O+", "O-"}


def test_unknown_group_counts_only_group_o_and_is_flagged():
    fr = make_frames([("RBTC-A", "A+", 30), ("RBTC-A", "O+", 2), ("RBTC-A", "O-", 1)])
    _, c = run(fr, group="unknown")
    assert c["RBTC-A"].stock_seen == 3
    assert set(c["RBTC-A"].stock_by_group) == {"O-", "O+"}
    assert "group_unknown_emergency_O" in c["RBTC-A"].flags


def test_site_flags():
    fr = make_frames([])
    _, c = run(fr)
    assert "no_backup_power" in c["HSP-C"].flags
    assert "low_connectivity_2g" in c["HSP-C"].flags
    assert c["HSP-B"].flags == []


# --------------------------------------------------------------------------- near-expiry


def _unit(fac="RBTC-A", group="O+", collected="2026-02-01", expiry="2026-03-15",
          status_date="2026-03-20", component="RBC"):
    return (component, fac, group, collected, expiry, status_date)


def test_near_expiry_counts_only_units_on_the_shelf_that_expire_soon():
    units = [
        _unit(),                                    # counts: expires in 5 days, left shelf after as_of
        _unit(component="WB"),                      # counts: whole blood is red cell supply
        _unit(status_date=None),                    # counts: blank status_date = still in stock
        _unit(expiry=REQUEST_DAY),                  # counts: expires on the request day
        _unit(expiry="2026-03-20"),                 # counts: exactly 10 days out
        _unit(expiry="2026-03-21"),                 # no: 11 days out
        _unit(expiry="2026-03-09"),                 # no: expired before the request day
        _unit(collected=REQUEST_DAY),               # no: collected after as_of
        _unit(status_date="2026-03-08"),            # no: left the shelf before as_of
        _unit(status_date=DAY_BEFORE),              # no: left the shelf on as_of
        _unit(group="A+"),                          # no: incompatible with O+
        _unit(component="PLT"),                     # no: not red cells
        _unit(fac="HSP-B"),                         # counted at HSP-B, not RBTC-A
    ]
    fr = make_frames([("RBTC-A", "O+", 50)], unit_rows=units)
    _, c = run(fr)
    assert c["RBTC-A"].near_expiry == 5


def test_near_expiry_is_capped_at_spare():
    units = [_unit(fac="HSP-B") for _ in range(6)]
    fr = make_frames([("HSP-B", "O+", 5)], usual_rows=[("HSP-B", "O+", 2)], unit_rows=units)
    _, c = run(fr)
    assert c["HSP-B"].spare == 3
    assert c["HSP-B"].near_expiry == 3


# --------------------------------------------------------------------------- real data


@pytest.fixture(scope="module")
def emergency_sample(frames):
    rq = frames.requests
    em = rq[(rq.urgency == "emergency") & (rq.component_requested == "RBC")]
    return em.sample(150, random_state=7)


def test_real_requests_never_return_requester_or_satellites(frames, emergency_sample):
    for r in emergency_sample.itertuples():
        _, cands = stock.candidates(frames, r.facility_id, r.patient_blood_group, r.requested_at, CFG)
        ids = {c.facility_id for c in cands}
        assert r.facility_id not in ids
        assert not any(i.startswith("SAT") for i in ids)
        assert len(ids) == 37  # 47 facilities - 9 satellites - requester


def test_real_hospitals_never_drop_below_safety_stock(frames, emergency_sample):
    for r in emergency_sample.itertuples():
        _, cands = stock.candidates(frames, r.facility_id, r.patient_blood_group, r.requested_at, CFG)
        for c in cands:
            assert 0 <= c.near_expiry <= c.spare <= c.stock_seen
            if not c.is_hospital:
                assert c.spare == c.stock_seen
                continue
            for g, units in c.stock_by_group.items():
                keep = max(frames.usual_level.get((c.facility_id, g), 0), CFG["min_keep"])
                assert units - c.spare_by_group[g] >= min(units, keep)


def test_real_sharing_off_returns_the_six_centres(frames):
    _, cands = stock.candidates(frames, "HSP-004", "O+", "2026-10-31 00:58:20",
                                {**CFG, "sharing_allowed": False})
    assert {c.facility_id for c in cands} == {
        "RBTC-NBO", "RBTC-MSA", "RBTC-KSM", "RBTC-ELD", "RBTC-NKR", "RBTC-EMB"}


def test_real_unknown_group_counts_only_o(frames):
    _, cands = stock.candidates(frames, "HSP-004", "unknown", "2026-10-31 00:58:20", CFG)
    for c in cands:
        assert set(c.stock_by_group) == {"O-", "O+"}
        assert "group_unknown_emergency_O" in c.flags


def test_real_stock_step_is_fast(frames):
    stock.candidates(frames, "HSP-004", "O+", "2026-10-31 00:58:20", CFG)  # warm up
    start = time.perf_counter()
    for _ in range(10):
        stock.candidates(frames, "HSP-004", "O+", "2026-10-31 00:58:20", CFG)
    assert (time.perf_counter() - start) / 10 < 0.1  # leaves room in the 200 ms budget
