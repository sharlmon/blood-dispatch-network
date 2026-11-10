"""Step 5: ranking, baseline, advice, reasons and the JSON contract (spec sections 8 and 9)."""

from __future__ import annotations

import json
import re
import time

import pandas as pd
import pytest

from engine import config, eta, rank, reasons
from engine.load import frames_from_tables

CFG = config.load_config("kenya")

# Constant wait 2 h and road ratio 1.0, so p50 = 2 + map time. Keeps expectations exact.
FLAT_ETA = eta.EtaModel.from_dict({"wait_h": [2.0], "ratio": [1.0]})

FACILITIES = pd.DataFrame(
    [
        ("RBTC-A", "Centre A", "regional_blood_centre", None, True, "4G"),
        ("RBTC-B", "Centre B", "regional_blood_centre", None, True, "4G"),
        ("RBTC-C", "Centre C", "regional_blood_centre", None, True, "4G"),
        ("HSP-R", "Requesting Hospital", "county_referral", "RBTC-A", True, "4G"),
        ("HSP-B", "Lending Hospital", "county_referral", "RBTC-A", True, "4G"),
        ("HSP-C", "Remote Hospital", "county_hospital", "RBTC-A", False, "2G"),
        ("SAT-S", "Satellite", "satellite_blood_centre", "RBTC-A", True, "3G"),
    ],
    columns=["facility_id", "name", "facility_type", "supply_centre_id",
             "has_blood_fridge_backup_power", "connectivity"],
)
# (from, hours to HSP-R, km to HSP-R)
ROUTES = [("RBTC-A", 2.0, 100), ("RBTC-B", 4.0, 200), ("RBTC-C", 3.0, 150),
          ("HSP-B", 1.0, 40), ("HSP-C", 0.5, 20), ("SAT-S", 0.2, 5)]
DAY_BEFORE = "2026-03-09"
REQUEST = {"facility_id": "HSP-R", "patient_group": "O+", "units_needed": 2,
           "component": "RBC", "requested_at": "2026-03-10T01:00:00"}


def make_frames(stock_rows, usual_rows=(), unit_rows=(), routes=ROUTES):
    red_stock = pd.DataFrame(
        [(DAY_BEFORE, f, g, n) for f, g, n in stock_rows] + [("2026-03-01", "RBTC-A", "AB+", 0)],
        columns=["date", "facility_id", "blood_group", "units"],
    )
    usual = pd.DataFrame(list(usual_rows), columns=["facility_id", "blood_group", "usual_level"])
    units = pd.DataFrame(
        list(unit_rows),
        columns=["component", "current_facility_id", "blood_group",
                 "collection_date", "expiry_date", "status_date"],
    )
    rt = pd.DataFrame(
        [(a, "HSP-R", km, h) for a, h, km in routes],
        columns=["from_facility_id", "to_facility_id", "road_km", "typical_travel_hours"],
    )
    return frames_from_tables(FACILITIES, rt, units, red_stock, usual)


def run(frames, request=REQUEST, cfg=CFG, model=FLAT_ETA, **kw):
    return rank.rank_sources(request, config=cfg, frames=frames, eta_model=model, **kw)


def ids(out):
    return [o["facility_id"] for o in out["options"]]


def expiring(fac, n):
    return [("RBC", fac, "O+", "2026-02-01", "2026-03-15", None)] * n


# --------------------------------------------------------------------------- JSON contract

TOP_KEYS = ["request", "mode", "model_used", "sharing_allowed", "compatibility_note",
            "stock_note", "advice", "options", "baseline"]
REQUEST_KEYS = ["facility_id", "patient_group", "units_needed", "requested_at", "as_of_stock_date"]
OPTION_KEYS = ["rank", "facility_id", "name", "facility_type", "is_hospital", "spare", "stock_seen",
               "near_expiry", "has_backup_power", "connectivity", "travel_hours_map", "eta",
               "flags", "reason"]
ETA_KEYS = ["p10", "p50", "p90", "wait_p50", "road_p50"]
BASELINE_KEYS = ["facility_id", "name", "quote_hours", "rule"]
FLAG_VOCAB = {"no_backup_power", "partial", "group_unknown_emergency_O",
              "o_neg_reserve_applied", "low_connectivity_2g"}


def assert_contract(out):
    assert list(out) == TOP_KEYS
    assert list(out["request"]) == REQUEST_KEYS
    assert list(out["baseline"]) == BASELINE_KEYS
    assert out["mode"] in ("model", "baseline")
    assert isinstance(out["model_used"], bool) and isinstance(out["sharing_allowed"], bool)
    assert out["advice"] in (None, "no_full_source", "consider_emergency_O_or_transfer")
    assert out["compatibility_note"] == (
        "From a fixed table. A qualified person crossmatches and releases every unit.")
    assert out["stock_note"] == (
        "Yesterday's closing count. Unconfirmed until the supplying site confirms.")
    for i, o in enumerate(out["options"], 1):
        assert list(o) == OPTION_KEYS
        assert list(o["eta"]) == ETA_KEYS
        assert o["rank"] == i
        assert type(o["spare"]) is int and type(o["stock_seen"]) is int and type(o["near_expiry"]) is int
        assert type(o["is_hospital"]) is bool and type(o["has_backup_power"]) is bool
        assert all(type(v) is float for v in o["eta"].values())
        assert o["eta"]["p10"] <= o["eta"]["p50"] <= o["eta"]["p90"]
        assert set(o["flags"]) <= FLAG_VOCAB
        assert isinstance(o["reason"], str) and o["reason"]
    json.loads(json.dumps(out))  # plain JSON types only


def test_output_matches_the_section_9_contract():
    fr = make_frames([("RBTC-A", "O+", 9), ("HSP-B", "O+", 9)], unit_rows=expiring("HSP-B", 1))
    out = run(fr)
    assert_contract(out)
    assert out["request"] == {"facility_id": "HSP-R", "patient_group": "O+", "units_needed": 2,
                              "requested_at": "2026-03-10T01:00:00", "as_of_stock_date": DAY_BEFORE}
    assert out["mode"] == "model" and out["model_used"] is True and out["sharing_allowed"] is True


# --------------------------------------------------------------------------- ranking


def test_only_sites_with_enough_spare_are_ranked_fastest_first():
    fr = make_frames([("RBTC-A", "O+", 5), ("RBTC-B", "O+", 5), ("HSP-B", "O+", 9), ("HSP-C", "O+", 3)])
    out = run(fr)  # HSP-C spare = 3 - 2 = 1 < 2 needed
    assert ids(out) == ["HSP-B", "RBTC-A", "RBTC-B"]
    assert [o["eta"]["p50"] for o in out["options"]] == [3.0, 4.0, 6.0]
    assert out["advice"] is None


def test_requester_and_satellites_never_appear():
    fr = make_frames([("HSP-R", "O+", 99), ("SAT-S", "O+", 99), ("RBTC-A", "O+", 5)])
    assert ids(run(fr)) == ["RBTC-A"]


def test_same_quarter_hour_bucket_breaks_ties_by_near_expiry_then_power_then_spare():
    routes = [("RBTC-A", 1.00, 50), ("RBTC-B", 1.05, 55), ("RBTC-C", 1.10, 60), ("HSP-B", 1.02, 40),
              ("HSP-C", 1.04, 20), ("SAT-S", 0.2, 5)]
    fr = make_frames(
        [("RBTC-A", "O+", 5), ("RBTC-B", "O+", 8), ("RBTC-C", "O+", 5), ("HSP-B", "O+", 6), ("HSP-C", "O+", 30)],
        unit_rows=expiring("RBTC-C", 3), routes=routes,
    )
    out = run(fr)
    # RBTC-C: most near-expiry. Then backup power before none (HSP-C last). Then spare: B 8, A 5, HSP-B 4.
    assert ids(out) == ["RBTC-C", "RBTC-B", "RBTC-A", "HSP-B", "HSP-C"]


def test_a_faster_bucket_beats_more_near_expiry():
    fr = make_frames([("RBTC-A", "O+", 5), ("HSP-B", "O+", 9)], unit_rows=expiring("RBTC-A", 4))
    assert ids(run(fr)) == ["HSP-B", "RBTC-A"]


def test_top_n_limits_the_list():
    fr = make_frames([("RBTC-A", "O+", 5), ("RBTC-B", "O+", 5), ("RBTC-C", "O+", 5), ("HSP-B", "O+", 9)])
    out = run(fr, top_n=2)
    assert ids(out) == ["HSP-B", "RBTC-A"]
    assert [o["rank"] for o in out["options"]] == [1, 2]


def test_sharing_off_ranks_centres_only():
    fr = make_frames([("RBTC-A", "O+", 5), ("HSP-B", "O+", 9)])
    out = run(fr, cfg={**CFG, "sharing_allowed": False})
    assert ids(out) == ["RBTC-A"]
    assert out["sharing_allowed"] is False


def test_hospital_extra_dispatch_time_moves_hospitals_down():
    fr = make_frames([("RBTC-A", "O+", 5), ("HSP-B", "O+", 9)])
    out = run(fr, cfg={**CFG, "hospital_extra_dispatch_h": 2.0})
    assert ids(out) == ["RBTC-A", "HSP-B"]
    assert out["options"][1]["eta"]["p50"] == 5.0


# --------------------------------------------------------------------------- partial and advice


def test_no_full_source_returns_partials_fastest_first():
    fr = make_frames([("RBTC-A", "O+", 1), ("RBTC-B", "O+", 3), ("HSP-B", "O+", 4)])
    out = run(fr, request={**REQUEST, "units_needed": 4})
    assert ids(out) == ["HSP-B", "RBTC-A", "RBTC-B"]  # HSP-B spare 2; zero-spare sites left out
    assert all("partial" in o["flags"] for o in out["options"])
    assert out["advice"] == "no_full_source"
    assert "Can cover only 2 of the 4 units needed." in out["options"][0]["reason"]


def test_nothing_anywhere_gives_empty_options_and_advice():
    out = run(make_frames([]))
    assert out["options"] == []
    assert out["advice"] == "no_full_source"
    assert out["baseline"]["facility_id"] is None and out["baseline"]["quote_hours"] is None
    assert_contract(out)


def test_advice_when_the_top_option_p90_is_over_the_clinician_limit():
    fr = make_frames([("RBTC-B", "O+", 5)])  # p90 = 6.0
    assert run(fr)["advice"] is None  # 6.0 is not over 6
    assert run(fr, cfg={**CFG, "clinician_limit_h": 5.9})["advice"] == "consider_emergency_O_or_transfer"


def test_too_long_advice_wins_over_no_full_source():
    fr = make_frames([("RBTC-B", "O+", 1)])
    out = run(fr, cfg={**CFG, "clinician_limit_h": 5.0})
    assert "partial" in out["options"][0]["flags"]
    assert out["advice"] == "consider_emergency_O_or_transfer"


# --------------------------------------------------------------------------- baseline


def test_baseline_is_the_supply_centre_when_it_has_enough():
    fr = make_frames([("RBTC-A", "O+", 2), ("RBTC-C", "O+", 50), ("HSP-B", "O+", 9)])
    out = run(fr)
    assert out["baseline"] == {"facility_id": "RBTC-A", "name": "Centre A", "quote_hours": 4.0,
                               "rule": reasons.BASELINE_RULE}
    assert ids(out)[0] == "HSP-B"  # model ranking still shown alongside


def test_baseline_moves_to_the_nearest_other_centre_with_enough():
    fr = make_frames([("RBTC-A", "O+", 1), ("RBTC-B", "O+", 9), ("RBTC-C", "O+", 9), ("HSP-B", "O+", 99)])
    assert run(fr)["baseline"]["facility_id"] == "RBTC-C"  # 150 km beats 200 km; hospitals never used
    fr = make_frames([("RBTC-A", "O+", 1), ("RBTC-B", "O+", 9), ("RBTC-C", "O+", 1)])
    out = run(fr)
    assert out["baseline"]["facility_id"] == "RBTC-B"
    assert out["baseline"]["quote_hours"] == 6.0


def test_baseline_mode_has_the_same_shape_and_follows_rule_order():
    fr = make_frames([("RBTC-A", "O+", 1), ("RBTC-B", "O+", 9), ("RBTC-C", "O+", 9), ("HSP-B", "O+", 99)])
    out = run(fr, mode="baseline")
    assert_contract(out)
    assert out["mode"] == "baseline"
    assert ids(out) == ["RBTC-C", "RBTC-B"]
    assert out["baseline"]["facility_id"] == "RBTC-C"
    assert out["options"][0]["reason"].startswith("Today's rule: the supply centre is short")
    assert "Today's quote would be 5.0 h (map time + 2 h, no range)." in out["options"][0]["reason"]


def test_baseline_mode_with_no_centre_stock():
    out = run(make_frames([("HSP-B", "O+", 99)]), mode="baseline")
    assert out["options"] == [] and out["advice"] == "no_full_source"


# --------------------------------------------------------------------------- unknown group, fallback


def test_unknown_group_uses_group_o_only_and_flags_every_option():
    fr = make_frames([("RBTC-A", "A+", 50), ("RBTC-A", "O-", 2), ("RBTC-B", "O+", 3)])
    out = run(fr, request={**REQUEST, "patient_group": "unknown"})
    assert ids(out) == ["RBTC-A", "RBTC-B"]
    assert out["options"][0]["stock_seen"] == 2  # the 50 A+ are not counted
    for o in out["options"]:
        assert "group_unknown_emergency_O" in o["flags"]
        assert "Emergency group O per hospital protocol. Lab confirms before release." in o["reason"]


def test_missing_eta_model_falls_back_without_crashing(tmp_path):
    fr = make_frames([("RBTC-A", "O+", 5)])
    out = run(fr, model=eta.load_model(tmp_path / "missing.json"))
    assert_contract(out)
    assert out["model_used"] is False
    e = out["options"][0]["eta"]
    assert (e["p10"], e["p50"], e["p90"]) == (2.2, 4.4, 6.6)  # (2.0 + 1.2 x 2.0) +-50%
    assert "rough defaults" in out["options"][0]["reason"]


# --------------------------------------------------------------------------- reasons


def test_reason_matches_the_spec_example_word_for_word():
    option = {"is_hospital": True, "spare": 24, "near_expiry": 3, "flags": [],
              "eta": {"p10": 1.4, "p50": 2.6, "p90": 3.8, "wait_p50": 2.0, "road_p50": 0.58}}
    assert reasons.option_reason(option, need=1, days=10, model_used=True, patient_group="O+") == (
        "Has 24 spare compatible units above its own safety stock. About 2.0 h to pack and "
        "dispatch, 0.6 h on the road. Most likely 2.6 h; 8 in 10 arrive within 1.4-3.8 h. "
        "3 units expire within 10 days, so sharing them avoids waste."
    )


def test_reason_singular_and_site_flags():
    fr = make_frames([("HSP-C", "O+", 3)], unit_rows=expiring("HSP-C", 1))
    out = run(fr, request={**REQUEST, "units_needed": 1})
    r = out["options"][0]["reason"]
    assert r.startswith("Has 1 spare compatible unit above its own safety stock.")
    assert "1 unit expires within 10 days" in r
    assert "Its blood fridge has no backup power." in r
    assert "It has 2G only, so confirmation may be slow." in r


def test_every_number_in_a_reason_is_a_value_from_the_json():
    fr = make_frames([("RBTC-A", "O+", 7), ("HSP-B", "O+", 9)], unit_rows=expiring("HSP-B", 2))
    for o in run(fr)["options"]:
        allowed = {f"{o['eta'][k]:.1f}" for k in o["eta"]} | {
            str(o["spare"]), str(o["near_expiry"]), str(CFG["near_expiry_days"]), "8", "10", "2"}
        for number in re.findall(r"\d+(?:\.\d+)?", o["reason"]):
            assert number in allowed, (number, o["reason"])


# --------------------------------------------------------------------------- input checks


@pytest.mark.parametrize(
    "change, message",
    [
        ({"component": "PLT"}, "out of scope"),
        ({"units_needed": 0}, "units_needed"),
        ({"units_needed": 1.5}, "units_needed"),
        ({"patient_group": "Z+"}, "Unknown patient group"),
        ({"facility_id": "HSP-404"}, "Unknown facility_id"),
    ],
)
def test_bad_requests_are_rejected(change, message):
    with pytest.raises(ValueError, match=message):
        run(make_frames([]), request={**REQUEST, **change})


def test_missing_fields_and_bad_mode_are_rejected():
    with pytest.raises(ValueError, match="missing facility_id"):
        run(make_frames([]), request={k: v for k, v in REQUEST.items() if k != "facility_id"})
    with pytest.raises(ValueError, match="mode must be"):
        run(make_frames([]), mode="llm")


# --------------------------------------------------------------------------- real data


def test_real_requests_all_year_return_valid_json_fast(frames, eta_model):
    model = eta_model
    rq = frames.requests
    sample = rq[(rq.urgency == "emergency") & (rq.component_requested == "RBC")].sample(120, random_state=3)
    rank.rank_sources(rank.request_from_dataset(frames, sample.iloc[0].request_id),
                      config=CFG, frames=frames, eta_model=model)  # warm up
    start = time.perf_counter()
    for rid in sample.request_id:
        req = rank.request_from_dataset(frames, rid)
        out = rank.rank_sources(req, config=CFG, frames=frames, eta_model=model)
        assert_contract(out)
        assert req["facility_id"] not in ids(out)
        assert not any(i.startswith("SAT") for i in ids(out))
        assert all(o["spare"] >= req["units_needed"] or "partial" in o["flags"] for o in out["options"])
        for o in out["options"]:
            assert o["eta"]["p10"] < o["eta"]["p50"] < o["eta"]["p90"]
    assert (time.perf_counter() - start) / len(sample) < 0.2  # spec: under 200 ms per call


def test_first_and_last_day_requests_work(frames):
    model = eta.EtaModel.fallback()
    for when, as_of in [("2025-11-01T00:30:00", "2025-11-01"), ("2026-10-31T23:00:00", "2026-10-30")]:
        out = rank.rank_sources({**REQUEST, "facility_id": "HSP-004", "requested_at": when},
                                config=CFG, frames=frames, eta_model=model)
        assert out["request"]["as_of_stock_date"] == as_of
