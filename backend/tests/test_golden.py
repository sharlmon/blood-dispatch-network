"""Step 6: golden cases from the real dataset (spec section 11).

Stock figures are exact: they follow from section 6 and the starter data, with no
randomness. Arrival times come from the fitted model, so they get a tolerance; the
spec says ranks may shift slightly with the fit but the direction must hold.
"""

from __future__ import annotations

import pytest

from engine import config, eta, rank

CFG = config.load_config("kenya")


@pytest.fixture(scope="module")
def golden(frames, eta_model):
    def run(request_id, **kw):
        req = rank.request_from_dataset(frames, request_id)
        return rank.rank_sources(req, config=CFG, frames=frames, eta_model=eta_model, **kw)

    return run


def by_id(out):
    return {o["facility_id"]: o for o in out["options"]}


# --------------------------------------------------------------------------- case 1


def test_case_1_westlands_nearby_hospitals_beat_todays_rule(golden, frames):
    """REQ-020421, 2026-10-31 00:58, HSP-004 Westlands Private, 1 x O+."""
    out = golden("REQ-020421")
    assert out["request"] == {
        "facility_id": "HSP-004", "patient_group": "O+", "units_needed": 1,
        "requested_at": "2026-10-31T00:58:20", "as_of_stock_date": "2026-10-30",
    }
    opts = by_id(out)

    # Nairobi centre (0.47 h) has 0 compatible units; City Maternity (0.47 h) is at its
    # usual level, so 0 spare. Neither is offered.
    assert "RBTC-NBO" not in opts and "HSP-003" not in opts

    # Top options are nearby hospitals: National Referral, then Eastlands County.
    top1, top2 = out["options"][:2]
    assert (top1["facility_id"], top2["facility_id"]) == ("HSP-001", "HSP-002")
    assert top1["is_hospital"] and top2["is_hospital"]
    assert (top1["spare"], top1["near_expiry"], top1["stock_seen"]) == (22, 14, 96)
    assert top1["travel_hours_map"] == 0.48
    assert top2["spare"] == 2 and top2["travel_hours_map"] == 0.68

    # Model p50 ~2.6 h against today's quote of ~8.9 h from Eldoret (6.93 h map).
    assert top1["eta"]["p50"] == pytest.approx(2.6, abs=0.15)
    assert top1["eta"]["p10"] < top1["eta"]["p50"] < top1["eta"]["p90"]
    assert out["baseline"]["facility_id"] == "RBTC-ELD"
    assert frames.travel_hours[("RBTC-ELD", "HSP-004")] == 6.93
    assert out["baseline"]["quote_hours"] == 8.9
    assert top1["eta"]["p90"] < out["baseline"]["quote_hours"]  # even the slow end beats the quote
    assert out["advice"] is None


def test_case_1_reason_text(golden):
    reason = golden("REQ-020421")["options"][0]["reason"]
    assert reason.startswith("Has 22 spare compatible units above its own safety stock.")
    assert "Most likely 2.6 h" in reason
    assert "14 units expire within 10 days, so sharing them avoids waste." in reason


# --------------------------------------------------------------------------- case 2


def test_case_2_kilifi_baseline_agrees_with_the_model(golden, frames):
    """REQ-005594, 2025-12-26 23:17, HSP-009 Kilifi County, 1 x O+."""
    out = golden("REQ-005594")
    assert out["request"]["as_of_stock_date"] == "2025-12-25"
    opts = by_id(out)

    # Mombasa centre (1.59 h, 3 units) and Coast Teaching (1.60 h, spare 18) are both at the top.
    assert {o["facility_id"] for o in out["options"][:2]} == {"RBTC-MSA", "HSP-008"}
    assert opts["RBTC-MSA"]["spare"] == opts["RBTC-MSA"]["stock_seen"] == 3
    assert opts["RBTC-MSA"]["travel_hours_map"] == 1.59
    assert (opts["HSP-008"]["spare"], opts["HSP-008"]["near_expiry"]) == (18, 6)
    assert opts["HSP-008"]["travel_hours_map"] == 1.6

    # Today's rule picks the supply centre, which the model also ranks at the top.
    assert out["baseline"]["facility_id"] == "RBTC-MSA"
    assert out["baseline"]["quote_hours"] == 3.6
    assert out["advice"] is None


# --------------------------------------------------------------------------- case 3


def test_case_3_garissa_nothing_close_so_advise_clinician(golden, frames):
    """REQ-003159, 2025-11-03 02:41, HSP-032 Garissa County Referral, 4 x O+."""
    out = golden("REQ-003159")
    assert out["request"]["units_needed"] == 4
    assert out["request"]["as_of_stock_date"] == "2025-11-02"

    # Nothing with enough spare within 8 h; Kitui (7.5 h) has 0 spare.
    assert frames.travel_hours[("HSP-029", "HSP-032")] == pytest.approx(7.51)
    assert "HSP-029" not in by_id(out)
    assert all(o["travel_hours_map"] > 8 for o in out["options"])

    # National Referral (11.7 h) holds 56 O+ against a usual level of 72: 0 spare.
    assert "HSP-001" not in by_id(out)

    # Nearest full source is Nakuru centre (14.1 h, spare 15), then Mombasa centre (spare 53).
    top1, top2 = out["options"][:2]
    assert (top1["facility_id"], top1["spare"]) == ("RBTC-NKR", 15)
    assert (top2["facility_id"], top2["spare"]) == ("RBTC-MSA", 53)
    assert all("partial" not in o["flags"] for o in out["options"])
    assert top1["eta"]["p90"] > CFG["clinician_limit_h"]
    assert out["advice"] == "consider_emergency_O_or_transfer"
    assert out["baseline"]["facility_id"] == "RBTC-NKR"


# --------------------------------------------------------------------------- "also test" list


def test_golden_output_is_deterministic(golden):
    for rid in ("REQ-020421", "REQ-005594", "REQ-003159"):
        assert golden(rid) == golden(rid)


def test_sharing_off_gives_centres_only_end_to_end(frames, eta_model):
    req = rank.request_from_dataset(frames, "REQ-020421")
    out = rank.rank_sources(req, config={**CFG, "sharing_allowed": False},
                            frames=frames, eta_model=eta_model)
    assert out["sharing_allowed"] is False
    assert out["options"] and all(not o["is_hospital"] for o in out["options"])
    assert out["options"][0]["facility_id"] == "RBTC-ELD"  # first centre with O+ stock


def test_unknown_group_end_to_end(frames, eta_model):
    req = {**rank.request_from_dataset(frames, "REQ-020421"), "patient_group": "unknown"}
    out = rank.rank_sources(req, config=CFG, frames=frames, eta_model=eta_model)
    assert out["request"]["patient_group"] == "unknown"
    assert out["options"]
    for o in out["options"]:
        assert "group_unknown_emergency_O" in o["flags"]
        assert "Emergency group O per hospital protocol. Lab confirms before release." in o["reason"]


def test_real_eta_quantiles_ordered_and_growing(eta_model, frames):
    travels = sorted(set(frames.travel_hours.values()))
    q = eta_model.quantiles(travels)
    assert (q["p10"] < q["p50"]).all() and (q["p50"] < q["p90"]).all()
    assert (q["p50"][1:] >= q["p50"][:-1]).all()
    assert q["p50"][-1] > q["p50"][0]


def test_missing_model_file_falls_back_end_to_end(frames, tmp_path):
    req = rank.request_from_dataset(frames, "REQ-020421")
    out = rank.rank_sources(req, config=CFG, frames=frames,
                            eta_model=eta.load_model(tmp_path / "missing.json"))
    assert out["model_used"] is False
    assert out["options"][0]["facility_id"] == "HSP-001"  # stock-driven choice unchanged
    e = out["options"][0]["eta"]
    assert e["p10"] < e["p50"] < e["p90"]
