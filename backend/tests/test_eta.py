"""Step 4: ETA fit, holdout metrics, query, fallback (spec section 7)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from engine import config, eta

CFG = config.load_config("kenya")

# A small hand-made model: waits 1-3 h, road ratio 1.0-1.4.
TOY = {"wait_h": [1.0, 1.5, 2.0, 2.5, 3.0], "ratio": [1.0, 1.1, 1.2, 1.3, 1.4]}


@pytest.fixture
def toy_model():
    return eta.EtaModel.from_dict(TOY)


# --------------------------------------------------------------------------- query


@pytest.mark.parametrize("travel", [0.3, 1.0, 5.0, 14.0, 33.0])
def test_quantiles_are_strictly_ordered(toy_model, travel):
    w = eta.eta_window(travel, False, CFG, toy_model)
    assert w["p10"] < w["p50"] < w["p90"]


def test_p50_grows_with_travel_time(toy_model):
    p50s = [eta.eta_window(t, False, CFG, toy_model)["p50"] for t in (0.5, 1, 2, 4, 8, 16)]
    assert all(a < b for a, b in zip(p50s, p50s[1:]))


def test_hospital_extra_shifts_the_whole_window(toy_model):
    cfg = {**CFG, "hospital_extra_dispatch_h": 1.5}
    centre = eta.eta_window(2.0, False, cfg, toy_model)
    hospital = eta.eta_window(2.0, True, cfg, toy_model)
    for k in ("p10", "p50", "p90", "wait_p50"):
        assert hospital[k] == pytest.approx(centre[k] + 1.5)
    assert hospital["road_p50"] == pytest.approx(centre["road_p50"])


def test_default_config_adds_no_hospital_extra(toy_model):
    assert eta.eta_window(2.0, True, CFG, toy_model) == eta.eta_window(2.0, False, CFG, toy_model)


def test_parts_add_up_to_about_p50(toy_model):
    w = eta.eta_window(3.0, False, CFG, toy_model)
    assert w["wait_p50"] == pytest.approx(2.0, abs=0.01)
    assert w["road_p50"] == pytest.approx(1.2 * 3.0, abs=0.05)
    assert w["p50"] == pytest.approx(w["wait_p50"] + w["road_p50"], abs=0.3)


def test_same_input_gives_same_answer():
    a = eta.EtaModel.from_dict(TOY)
    b = eta.EtaModel.from_dict(TOY)
    assert eta.eta_window(4.2, False, CFG, a) == eta.eta_window(4.2, False, CFG, b)


def test_vectorised_matches_single(toy_model):
    travels = [0.5, 2.0, 9.0]
    batch = toy_model.quantiles(travels)
    for i, t in enumerate(travels):
        single = eta.eta_window(t, False, CFG, toy_model)
        assert batch["p50"][i] == pytest.approx(single["p50"])


# --------------------------------------------------------------------------- fallback


def test_missing_model_file_falls_back(tmp_path):
    model = eta.load_model(tmp_path / "nope.json")
    assert model.model_used is False
    w = eta.eta_window(1.0, False, CFG, model)
    assert w["p50"] == pytest.approx(2.0 + 1.2 * 1.0)
    assert w["p10"] == pytest.approx(0.5 * w["p50"])
    assert w["p90"] == pytest.approx(1.5 * w["p50"])
    assert w["wait_p50"] == pytest.approx(2.0)
    assert w["road_p50"] == pytest.approx(1.2)


def test_no_path_falls_back():
    assert eta.load_model(None).model_used is False


def test_corrupt_model_file_falls_back_with_warning(tmp_path):
    bad = tmp_path / "eta_model.json"
    bad.write_text("{not json")
    with pytest.warns(UserWarning, match="unreadable"):
        model = eta.load_model(bad)
    assert model.model_used is False


def test_empty_model_file_falls_back(tmp_path):
    bad = tmp_path / "eta_model.json"
    bad.write_text(json.dumps({"wait_h": [], "ratio": []}))
    with pytest.warns(UserWarning):
        assert eta.load_model(bad).model_used is False


def test_fallback_respects_hospital_extra():
    cfg = {**CFG, "hospital_extra_dispatch_h": 1.0}
    w = eta.eta_window(1.0, True, cfg, eta.EtaModel.fallback())
    assert w["p50"] == pytest.approx(3.0 + 1.2)


def test_saved_model_round_trips(tmp_path):
    path = tmp_path / "eta_model.json"
    eta.save_json(TOY, path)
    loaded = eta.load_model(path)
    assert loaded.model_used is True
    assert eta.eta_window(2.0, False, CFG, loaded) == eta.eta_window(2.0, False, CFG, eta.EtaModel.from_dict(TOY))


def test_baseline_quote_is_map_time_plus_two_hours():
    assert eta.baseline_quote(6.93, CFG) == pytest.approx(8.93)


# --------------------------------------------------------------------------- real data


@pytest.fixture(scope="module")
def fitted(frames):
    return eta.fit(frames, CFG["eta_train_before"])


def test_fit_uses_only_emergency_transfers_before_the_cutoff(frames, fitted):
    model, metrics = fitted
    em = eta.emergency_transfers(frames)
    assert set(em["transfer_type"]) == {"emergency_request", "emergency_cross_region"}
    train = em[em["requested_at"] < "2026-07-01"]
    assert model["n_wait"] == len(train)
    assert model["n_ratio"] == train["ratio"].notna().sum()  # rows with no received_at dropped
    assert metrics["test_from"] >= "2026-07-01"


def test_wait_and_ratio_are_independent_in_training_data(fitted):
    model, _ = fitted
    assert abs(model["wait_ratio_corr"]) < 0.05


def test_holdout_metrics_match_spec(fitted):
    _, m = fitted
    assert m["mae_map_only_h"] == pytest.approx(2.74, abs=0.1)
    assert m["mae_map_plus_2h_h"] == pytest.approx(1.17, abs=0.1)
    assert m["mae_model_p50_h"] == pytest.approx(0.95, abs=0.1)
    assert m["coverage_p10_p90"] == pytest.approx(0.79, abs=0.03)
    assert m["mae_model_p50_h"] < m["mae_map_plus_2h_h"] < m["mae_map_only_h"]


def test_golden_case_1_p50_is_about_2_6_hours(frames, fitted):
    model = eta.EtaModel.from_dict(fitted[0])
    travel = frames.travel_hours[("HSP-001", "HSP-004")]
    w = eta.eta_window(travel, True, CFG, model)
    assert w["p50"] == pytest.approx(2.6, abs=0.15)
    assert w["wait_p50"] == pytest.approx(2.0, abs=0.1)


def test_query_for_all_candidates_is_fast(frames, fitted):
    import time

    model = eta.EtaModel.from_dict(fitted[0])
    travels = np.linspace(0.3, 33, 37)
    start = time.perf_counter()
    model.quantiles(travels)
    assert time.perf_counter() - start < 0.05
