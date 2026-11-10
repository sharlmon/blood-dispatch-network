"""The Flask API around the engine: health, facilities and stateless ranking.

Runs on the tiny in-memory engine from conftest.py, so no DATA_DIR or network is needed.
"""

from __future__ import annotations

import json
import threading
import time
import weakref
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from dotenv import dotenv_values

from app import engine_service, load_settings
from app.engine_service import EngineService, EngineUnavailable
from engine import config, rank
from engine.config import REPO_ROOT

CFG = config.load_config("kenya")
REQUEST = {"facility_id": "HSP-R", "patient_group": "O+", "units_needed": 2, "requested_at": "2026-03-10T01:00:00"}
FACILITY_KEYS = ["facility_id", "name", "facility_type", "is_hospital", "is_centre", "is_satellite", "county",
                 "lat", "lon", "supply_centre_id", "connectivity", "has_backup_power"]
SITE_KEYS = ["facility_id", "name", "facility_type", "county", "lat", "lon", "road_km", "travel_hours_map"]
STATUS_KEYS = ["state", "model_used", "stock_first", "stock_last", "message"]
BUILD_HINT = "Run `python scripts/build_db.py` from backend/ first."


def strict_json(resp):
    """The body as strict JSON: NaN or Infinity anywhere fails the test."""
    def refuse(name):
        raise AssertionError(f"{name} in a JSON response")

    return json.loads(resp.get_data(as_text=True), parse_constant=refuse)


def rank_body(client, **change):
    r = client.post("/api/rank", json={**REQUEST, **change})
    assert r.status_code == 200, r.get_json()
    return strict_json(r)


def ids(result):
    return [o["facility_id"] for o in result["ranking"]["options"]]


@pytest.fixture
def no_data(monkeypatch, tmp_path):
    """DATA_DIR points at an empty folder, so loading the engine fails (even with real data around)."""
    empty = tmp_path / "no-data"
    empty.mkdir()
    monkeypatch.setenv("DATA_DIR", str(empty))
    monkeypatch.delenv("ENGINE_DB_PATH", raising=False)
    return empty


# --------------------------------------------------------------------------- health


def test_health_reports_a_ready_engine(api_client):
    body = strict_json(api_client.get("/api/health"))
    assert body["status"] == "ok"
    assert body["country"] == load_settings(str(REPO_ROOT / "backend/config/settings.default.yaml"))["country"]
    assert list(body["engine"]) == STATUS_KEYS
    assert body["engine"] == {"state": "ready", "model_used": True, "stock_first": "2026-03-09",
                              "stock_last": "2026-03-09", "message": None}


def test_health_is_idle_before_first_use_then_error_without_data(make_api_app, no_data):
    client = make_api_app(EngineService()).test_client()
    assert strict_json(client.get("/api/health"))["engine"] == {
        "state": "idle", "model_used": None, "stock_first": None, "stock_last": None, "message": None}

    r = client.get("/api/facilities")
    assert r.status_code == 503
    error = strict_json(r)["error"]
    assert error["code"] == "engine_unavailable"
    assert str(no_data) not in r.get_data(as_text=True)  # DATA_DIR is outside the repo here

    health = client.get("/api/health")
    engine = strict_json(health)["engine"]
    assert engine["state"] == "error" and engine["model_used"] is None
    assert engine["message"].startswith("No database at blood.db.")
    assert str(no_data) not in health.get_data(as_text=True)
    assert error["message"] == engine["message"]  # the reason; the screens add "use the phone process"


def test_a_data_dir_that_is_not_a_folder_is_named_without_the_servers_folders(make_api_app, monkeypatch, no_data):
    monkeypatch.setenv("DATA_DIR", str(no_data / "missing"))
    client = make_api_app(EngineService()).test_client()
    r = client.post("/api/rank", json=REQUEST)
    assert r.status_code == 503 and strict_json(r)["error"]["code"] == "engine_unavailable"
    health = client.get("/api/health")
    message = strict_json(health)["engine"]["message"]
    assert message == strict_json(r)["error"]["message"]
    assert "missing" in message and "not a folder" in message
    for body in (r, health):
        assert str(no_data) not in body.get_data(as_text=True)


@pytest.mark.parametrize(
    "exc, shown",
    [
        (FileNotFoundError(f"No database at /srv/bdn/data/blood.db. {BUILD_HINT}"),
         f"No database at blood.db. {BUILD_HINT}"),
        (config.ConfigError("DATA_DIR='/srv/bdn/nope' resolves to /srv/bdn/nope, which is not a folder."),
         "DATA_DIR='nope' resolves to nope, which is not a folder."),
        (PermissionError(13, "Permission denied", "/srv/bdn/data/blood.db"),
         "Cannot read the engine data: [Errno 13] Permission denied: 'blood.db'"),
        (config.ConfigError(f"No settings file at {REPO_ROOT / 'backend' / 'config' / 'xx.yaml'}."),
         "No settings file at backend/config/xx.yaml."),
    ],
)
def test_engine_problems_keep_file_names_but_not_folders(exc, shown, caplog):
    assert engine_service._reason(exc) == shown
    assert str(exc) in caplog.text  # the operator's log keeps the full text


def test_error_messages_do_not_show_the_servers_folders(monkeypatch, no_data):
    monkeypatch.setenv("ENGINE_DB_PATH", "data/missing-for-test.db")  # inside the repo
    engine = EngineService()
    with pytest.raises(EngineUnavailable):
        engine.facilities()
    message = engine.status()["message"]
    assert message.startswith("No database at data/missing-for-test.db.")
    assert str(REPO_ROOT) not in message


def test_health_answers_at_once_while_the_engine_loads(make_api_app, monkeypatch, no_data):
    started, release = threading.Event(), threading.Event()

    def slow_load(path):
        started.set()
        release.wait(10)
        raise FileNotFoundError("No database here.")

    monkeypatch.setattr(engine_service, "load_frames", slow_load)
    engine = EngineService(load_wait_s=0.05)
    client = make_api_app(engine).test_client()
    loader = threading.Thread(target=engine.warm_up)
    loader.start()
    try:
        assert started.wait(5)
        t0 = time.perf_counter()
        body = strict_json(client.get("/api/health"))
        assert time.perf_counter() - t0 < 1.0
        assert body["engine"]["state"] == "loading"

        # Other calls wait only a bounded time for a load in progress.
        r = client.get("/api/facilities")
        assert r.status_code == 503 and "still loading" in strict_json(r)["error"]["message"].lower()
    finally:
        release.set()
        loader.join(10)
    assert strict_json(client.get("/api/health"))["engine"]["state"] == "error"


def test_a_failed_load_is_retried_at_most_every_30_seconds(monkeypatch, no_data, api_frames):
    calls = []

    def missing(path):
        calls.append(path)
        raise FileNotFoundError("No database here.")

    monkeypatch.setattr(engine_service, "load_frames", missing)
    engine = EngineService()
    assert engine.retry_after_s == 30
    for _ in range(3):
        with pytest.raises(EngineUnavailable):
            engine.facilities()
    assert len(calls) == 1  # no retry within 30 s

    # Later the data is there: the next call after the wait loads it.
    monkeypatch.setattr(engine_service, "load_frames", lambda path: api_frames)
    engine.retry_after_s = 0
    assert [f["facility_id"] for f in engine.facilities()][:1] == ["RBTC-A"]
    status = engine.status()
    assert status["state"] == "ready" and status["stock_last"] == "2026-03-09"
    assert status["model_used"] is False and "rough defaults" in status["message"]  # no eta_model.json


def test_a_forked_worker_does_not_inherit_a_held_load_lock(monkeypatch, no_data, api_frames):
    engine = EngineService(load_wait_s=0.05)
    engine._lock.acquire()  # held by a loading thread that does not exist after a fork
    engine._state = "loading"
    engine_service._reset_after_fork(weakref.ref(engine))  # what os.register_at_fork runs in the child
    assert engine.status()["state"] == "idle"
    monkeypatch.setattr(engine_service, "load_frames", lambda path: api_frames)
    assert engine.facilities() and engine.status()["state"] == "ready"


def test_warm_up_runs_one_ranking_and_never_raises(api_engine, monkeypatch, no_data):
    seen = []
    real = engine_service.engine_rank.rank_sources
    monkeypatch.setattr(engine_service.engine_rank, "rank_sources",
                        lambda request, **kw: seen.append(request) or real(request, **kw))
    api_engine.warm_up()
    assert [r["facility_id"] for r in seen] == ["HSP-B"]  # the first hospital by id

    failing = EngineService()
    failing.warm_up()  # no exception
    assert failing.status()["state"] == "error"

    monkeypatch.setattr(engine_service.engine_rank, "rank_sources", lambda *a, **kw: 1 / 0)
    api_engine.warm_up()  # an unexpected error is logged, not raised


class FakeEngine:
    def __init__(self, state="idle"):
        self.state, self.warmed = state, threading.Event()

    def status(self):
        return {"state": self.state, "model_used": None, "stock_first": None, "stock_last": None, "message": None}

    def warm_up(self):
        self.warmed.set()


def test_create_app_warms_the_engine_up_in_the_background(make_api_app, monkeypatch):
    monkeypatch.delenv("ENGINE_WARMUP")  # default: on
    engine = FakeEngine()
    make_api_app(engine)
    assert engine.warmed.wait(5)

    for off in ("0", "false", "FALSE"):
        monkeypatch.setenv("ENGINE_WARMUP", off)
        engine = FakeEngine()
        make_api_app(engine)
        assert not engine.warmed.wait(0.1)

    monkeypatch.setenv("ENGINE_WARMUP", "1")
    engine = FakeEngine(state="ready")  # injected and ready: nothing to warm up
    make_api_app(engine)
    assert not engine.warmed.wait(0.1)


# --------------------------------------------------------------------------- facilities


def test_facilities_shape_and_types(api_client):
    facilities = strict_json(api_client.get("/api/facilities"))["facilities"]
    assert [f["name"] for f in facilities] == sorted(f["name"] for f in facilities)
    assert {f["facility_id"] for f in facilities} == {"RBTC-A", "RBTC-B", "HSP-R", "HSP-B", "HSP-C", "SAT-S"}
    by_id = {f["facility_id"]: f for f in facilities}
    for f in facilities:
        assert list(f) == FACILITY_KEYS
        assert [f["is_hospital"], f["is_centre"], f["is_satellite"]].count(True) == 1
        assert all(type(f[k]) is bool for k in ("is_hospital", "is_centre", "is_satellite", "has_backup_power"))
    assert by_id["RBTC-A"]["is_centre"] and by_id["HSP-B"]["is_hospital"] and by_id["SAT-S"]["is_satellite"]
    assert by_id["HSP-R"] == {
        "facility_id": "HSP-R", "name": "Requesting Hospital", "facility_type": "county_referral",
        "is_hospital": True, "is_centre": False, "is_satellite": False, "county": "Kiambu",
        "lat": -1.17, "lon": 36.83, "supply_centre_id": "RBTC-A", "connectivity": "4G", "has_backup_power": True,
    }
    assert by_id["HSP-C"]["has_backup_power"] is False and by_id["HSP-C"]["connectivity"] == "2G"
    assert (by_id["SAT-S"]["county"], by_id["SAT-S"]["lat"], by_id["SAT-S"]["lon"]) == (None, None, None)
    assert by_id["RBTC-A"]["supply_centre_id"] is None


def test_facilities_are_json_safe_with_numpy_values_and_nan(make_api_app, api_engine, api_frames):
    info = api_frames.facility_info
    info["HSP-B"].update(lat=np.float64(-1.3), lon=np.float32(36.5), has_blood_fridge_backup_power=np.bool_(False))
    info["SAT-S"].update(lat=np.float64("nan"), lon=float("inf"), county=float("nan"), name=np.str_("Satellite"))
    facilities = strict_json(make_api_app(api_engine).test_client().get("/api/facilities"))["facilities"]
    by_id = {f["facility_id"]: f for f in facilities}
    assert by_id["HSP-B"]["lat"] == -1.3 and by_id["HSP-B"]["has_backup_power"] is False
    assert by_id["HSP-B"]["lon"] == pytest.approx(36.5)
    assert (by_id["SAT-S"]["lat"], by_id["SAT-S"]["lon"], by_id["SAT-S"]["county"]) == (None, None, None)


# --------------------------------------------------------------------------- rank


def test_rank_returns_the_engines_json_unchanged_plus_sites(api_client, api_frames, api_eta):
    body = rank_body(api_client)
    direct = rank.rank_sources({**REQUEST, "component": "RBC"}, config=CFG, frames=api_frames, eta_model=api_eta)
    assert list(body) == ["ranking", "clinician_limit_h", "requester", "sites"]
    assert body["ranking"] == direct
    assert list(body["ranking"]) == list(direct)  # the engine's key order survives
    assert ids(body) == ["HSP-B", "RBTC-A", "RBTC-B"]
    assert body["ranking"]["baseline"]["facility_id"] == "RBTC-A"
    assert body["clinician_limit_h"] == CFG["clinician_limit_h"] == 6.0
    assert body["requester"] == {"facility_id": "HSP-R", "name": "Requesting Hospital",
                                 "facility_type": "county_referral", "county": "Kiambu", "lat": -1.17, "lon": 36.83}
    assert list(body["sites"]) == ["HSP-B", "RBTC-A", "RBTC-B"]  # options, then the baseline (already listed)
    assert all(list(s) == SITE_KEYS for s in body["sites"].values())
    assert body["sites"]["RBTC-B"] == {"facility_id": "RBTC-B", "name": "Centre B",
                                       "facility_type": "regional_blood_centre", "county": "Nakuru", "lat": -0.3,
                                       "lon": 36.07, "road_km": 200.0, "travel_hours_map": 4.0}
    for o in body["ranking"]["options"]:
        assert body["sites"][o["facility_id"]]["travel_hours_map"] == o["travel_hours_map"]


def test_the_baseline_site_is_included_when_it_is_not_an_option(api_client):
    body = rank_body(api_client, top_n=1)
    assert ids(body) == ["HSP-B"]
    assert list(body["sites"]) == ["HSP-B", "RBTC-A"]
    assert body["sites"]["RBTC-A"]["road_km"] == 100.0


def test_without_a_baseline_the_sites_are_the_options_only(api_client):
    body = rank_body(api_client, patient_group="B-")  # B- patients: only RBTC-A's 2 O- units
    assert ids(body) == ["RBTC-A"] and body["ranking"]["baseline"]["facility_id"] == "RBTC-A"
    body = rank_body(api_client, patient_group="B-", units_needed=50)
    assert body["ranking"]["baseline"]["facility_id"] is None
    assert body["ranking"]["advice"] == "no_full_source"
    assert list(body["sites"]) == ids(body) == ["RBTC-A"]


@pytest.mark.parametrize("group", ["AB\u2212", "ab\u2013", " AB- "])
def test_unicode_minus_and_case_are_accepted(api_client, group):
    body = rank_body(api_client, patient_group=group, units_needed=1)
    assert body["ranking"]["request"]["patient_group"] == "AB-"
    assert ids(body) == ["RBTC-A"]  # the only O- spare


def test_unknown_group_gets_group_o_only_with_the_flag(api_client):
    body = rank_body(api_client, patient_group="Unknown")
    assert body["ranking"]["request"]["patient_group"] == "unknown"
    assert body["ranking"]["options"]
    assert all("group_unknown_emergency_O" in o["flags"] for o in body["ranking"]["options"])


def test_limit_h_is_the_clinicians_limit_for_this_call(api_client):
    assert rank_body(api_client)["ranking"]["advice"] is None  # top p90 = 3.0 h, limit 6 h
    body = rank_body(api_client, limit_h=2.5)
    assert body["clinician_limit_h"] == 2.5
    assert body["ranking"]["advice"] == "consider_emergency_O_or_transfer"
    assert rank_body(api_client, limit_h=72)["clinician_limit_h"] == 72.0
    assert rank_body(api_client)["clinician_limit_h"] == 6.0  # one call never changes the next


def test_mode_top_n_and_component_options(api_client):
    body = rank_body(api_client, mode="baseline")
    assert body["ranking"]["mode"] == "baseline" and ids(body) == ["RBTC-A", "RBTC-B"]
    assert len(rank_body(api_client, top_n=2)["ranking"]["options"]) == 2
    assert rank_body(api_client, component="rbc")["ranking"]["options"]
    assert rank_body(api_client, component=None, mode=None, top_n=None, limit_h=None)["clinician_limit_h"] == 6.0


def test_unknown_fields_are_ignored_and_never_echoed(api_client):
    r = api_client.post("/api/rank", json={**REQUEST, "patient_name": "Sentinel Name-7731",
                                           "clinical_indication": "Sentinel indication-7731"})
    assert r.status_code == 200
    assert "7731" not in r.get_data(as_text=True)


@pytest.mark.parametrize(
    "change, words",
    [
        ({"units_needed": True}, "units_needed"),
        ({"units_needed": 1.5}, "units_needed"),
        ({"units_needed": 2.0}, "units_needed"),
        ({"units_needed": "2"}, "units_needed"),
        ({"units_needed": 0}, "units_needed"),
        ({"units_needed": -1}, "units_needed"),
        ({"units_needed": 101}, "units_needed"),
        ({"units_needed": None}, "units_needed"),
        ({"patient_group": "Z+"}, "Unknown patient group"),
        ({"patient_group": ""}, "patient_group"),
        ({"patient_group": 7}, "patient_group"),
        ({"facility_id": "HSP-404"}, "Unknown facility_id"),
        ({"facility_id": ""}, "facility_id"),
        ({"facility_id": ["HSP-R"]}, "facility_id"),
        ({"component": "PLT"}, "out of scope"),
        ({"component": 5}, "component"),
        ({"limit_h": 0}, "limit_h"),
        ({"limit_h": -2}, "limit_h"),
        ({"limit_h": 100}, "limit_h"),
        ({"limit_h": "6"}, "limit_h"),
        ({"limit_h": True}, "limit_h"),
        ({"top_n": 0}, "top_n"),
        ({"top_n": 11}, "top_n"),
        ({"top_n": 2.5}, "top_n"),
        ({"mode": "llm"}, "mode"),
        ({"requested_at": "yesterday"}, "requested_at"),
        ({"requested_at": "2026-13-45T00:00:00"}, "requested_at"),
        ({"requested_at": 1762300000}, "requested_at"),
        ({"requested_at": "1850-01-01T00:00:00"}, "requested_at"),
    ],
)
def test_bad_input_is_a_400_with_a_plain_message(api_client, change, words):
    r = api_client.post("/api/rank", json={**REQUEST, **change})
    assert r.status_code == 400
    error = strict_json(r)["error"]
    assert error["code"] == "invalid_request" and words in error["message"]


@pytest.mark.parametrize("field", ["facility_id", "patient_group", "units_needed"])
def test_required_fields(api_client, field):
    r = api_client.post("/api/rank", json={k: v for k, v in REQUEST.items() if k != field})
    assert r.status_code == 400 and field in strict_json(r)["error"]["message"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"json": [REQUEST]},
        {"json": "HSP-R O+ 2"},
        {"data": "null", "content_type": "application/json"},
        {"data": "{not json", "content_type": "application/json"},
        {"data": json.dumps(REQUEST), "content_type": "text/plain"},
        {},
    ],
)
def test_a_body_that_is_not_a_json_object_is_a_400(api_client, kwargs):
    r = api_client.post("/api/rank", **kwargs)
    assert r.status_code == 400 and strict_json(r)["error"]["code"] == "invalid_request"


def test_engine_unavailable_is_a_503_envelope(make_api_app, no_data):
    client = make_api_app(EngineService()).test_client()
    r = client.post("/api/rank", json=REQUEST)
    assert r.status_code == 503
    body = strict_json(r)
    assert list(body) == ["error"] and body["error"]["code"] == "engine_unavailable"
    assert body["error"]["message"]


# --------------------------------------------------------------------------- clock


def test_requested_at_with_an_offset_is_converted_to_east_africa_time(api_client):
    for given in ("2026-03-09T22:00:00Z", "2026-03-09T22:00:00+00:00", "2026-03-10T01:00:00+03:00",
                  "2026-03-10T00:00:00+02:00"):
        assert rank_body(api_client, requested_at=given)["ranking"]["request"]["requested_at"] == "2026-03-10T01:00:00"


@pytest.mark.parametrize("given", ["2026-03-08T23:59:00", "2026-03-09T00:59:00+05:00", "2000-01-01T00:00:00"])
def test_a_request_before_the_first_stock_count_is_a_400(api_client, given):
    """The tiny data's only count is 2026-03-09: a request before that day has no count to rank on."""
    r = api_client.post("/api/rank", json={**REQUEST, "requested_at": given})
    assert r.status_code == 400
    error = strict_json(r)["error"]
    assert error["code"] == "invalid_request" and "no stock count before 2026-03-09" in error["message"]


def test_a_request_on_the_first_stock_day_uses_that_days_count(api_client):
    """Spec section 6: the first day has no previous-day count, so it uses its own, and says so."""
    body = rank_body(api_client, requested_at="2026-03-08T21:00:00Z")  # 2026-03-09 00:00 East Africa Time
    assert body["ranking"]["request"]["requested_at"] == "2026-03-09T00:00:00"
    assert body["ranking"]["request"]["as_of_stock_date"] == "2026-03-09"


def test_without_a_clock_a_request_now_is_dated_with_the_last_count(api_client):
    """No requested_at, DEMO_CLOCK or demo_clock: the real time is after the data ends, so the last
    count is used and as_of_stock_date names that day, not yesterday."""
    r = api_client.post("/api/rank", json={k: v for k, v in REQUEST.items() if k != "requested_at"})
    request = strict_json(r)["ranking"]["request"]
    assert request["requested_at"][:10] > "2026-03-10"
    assert request["as_of_stock_date"] == strict_json(api_client.get("/api/health"))["engine"]["stock_last"]


def settings_with_clock(tmp_path, clock) -> str:
    settings = load_settings(str(REPO_ROOT / "backend/config/settings.default.yaml"))
    path = tmp_path / "settings.yaml"
    import yaml

    path.write_text(yaml.safe_dump({**settings, "demo_clock": clock}))
    return str(path)


def test_default_request_time_is_demo_clock_then_settings_then_now(make_api_app, api_engine, monkeypatch, tmp_path):
    no_time = {k: v for k, v in REQUEST.items() if k != "requested_at"}

    def requested_at(client):
        r = client.post("/api/rank", json=no_time)
        assert r.status_code == 200
        return strict_json(r)["ranking"]["request"]["requested_at"]

    settings_clock = make_api_app(api_engine, settings_path=settings_with_clock(tmp_path, "2026-03-10T02:00:00"))
    assert requested_at(settings_clock.test_client()) == "2026-03-10T02:00:00"

    monkeypatch.setenv("DEMO_CLOCK", "2026-03-10T03:30:00")  # the environment wins
    assert requested_at(settings_clock.test_client()) == "2026-03-10T03:30:00"

    monkeypatch.setenv("DEMO_CLOCK", "not a time")  # ignored, with a warning
    assert requested_at(settings_clock.test_client()) == "2026-03-10T02:00:00"

    monkeypatch.delenv("DEMO_CLOCK")
    now_app = make_api_app(api_engine, settings_path=settings_with_clock(tmp_path, None))
    got = datetime.fromisoformat(requested_at(now_app.test_client()))
    now_eat = datetime.now(timezone(timedelta(hours=3))).replace(tzinfo=None)
    assert abs((now_eat - got).total_seconds()) < 60


def test_a_yaml_timestamp_demo_clock_works(make_api_app, api_engine, tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("country: KE\ndemo_clock: 2026-03-09T22:00:00+00:00\n")  # YAML parses this to a datetime
    r = make_api_app(api_engine, settings_path=path).test_client().post(
        "/api/rank", json={k: v for k, v in REQUEST.items() if k != "requested_at"})
    assert strict_json(r)["ranking"]["request"]["requested_at"] == "2026-03-10T01:00:00"


# --------------------------------------------------------------------------- HTTP details


def test_unknown_paths_and_methods_answer_with_the_error_envelope(api_client):
    r = api_client.get("/api/nothing-here")
    assert r.status_code == 404 and strict_json(r)["error"]["code"] == "not_found"
    r = api_client.get("/api/rank")
    assert r.status_code == 405 and strict_json(r)["error"]["code"] == "method_not_allowed"
    assert "POST" in r.headers["Allow"]
    assert api_client.get("/not-the-api").status_code == 404


def test_unexpected_errors_answer_500_with_the_envelope(api_app, monkeypatch):
    monkeypatch.setattr(api_app.extensions["engine"], "facilities", lambda: 1 / 0)
    r = api_app.test_client().get("/api/facilities")
    assert r.status_code == 500
    assert strict_json(r)["error"]["code"] == "internal_error"


def test_cors_allows_posts_with_authorization_and_json(api_client):
    origin = "http://localhost:3000"
    r = api_client.options("/api/requests", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization, content-type"})
    assert r.status_code == 200
    assert r.headers["Access-Control-Allow-Origin"] == origin
    assert "POST" in r.headers["Access-Control-Allow-Methods"]
    allowed = r.headers["Access-Control-Allow-Headers"].lower()
    assert "authorization" in allowed and "content-type" in allowed
    r = api_client.post("/api/rank", json=REQUEST, headers={"Origin": origin})
    assert r.headers["Access-Control-Allow-Origin"] == origin
    r = api_client.post("/api/rank", json={}, headers={"Origin": origin})  # errors carry CORS too
    assert r.status_code == 400 and r.headers["Access-Control-Allow-Origin"] == origin


# --------------------------------------------------------------------------- real data


def test_golden_case_1_through_the_api(make_api_app, frames, eta_model):
    """REQ-020421: Westlands (HSP-004), 1 x O+, 2026-10-31 00:58 (spec section 11)."""
    engine = EngineService(config=CFG, frames=frames, eta_model=eta_model)
    client = make_api_app(engine).test_client()
    body = rank_body(client, facility_id="HSP-004", patient_group="O+", units_needed=1,
                     requested_at="2026-10-31T00:58:20")
    ranking = body["ranking"]
    assert ranking["request"]["as_of_stock_date"] == "2026-10-30"
    assert ranking["options"][0]["facility_id"] == "HSP-001"
    assert ranking["baseline"]["facility_id"] == "RBTC-ELD"
    assert body["requester"]["facility_id"] == "HSP-004"
    assert body["sites"]["RBTC-ELD"]["travel_hours_map"] == pytest.approx(6.93, abs=0.01)
    assert body["sites"]["HSP-001"]["lat"] is not None
    assert strict_json(client.get("/api/health"))["engine"]["state"] == "ready"
    assert len(strict_json(client.get("/api/facilities"))["facilities"]) == len(frames.facility_info)


def test_the_example_env_clock_ranks_on_the_previous_days_count(make_api_app, monkeypatch, frames, eta_model):
    """.env.example freezes the demo clock inside the synthetic data, so "Yesterday's count" is true."""
    clock = dotenv_values(REPO_ROOT / ".env.example").get("DEMO_CLOCK")
    assert clock, ".env.example should set DEMO_CLOCK for demos on the synthetic data"
    monkeypatch.setenv("DEMO_CLOCK", clock)
    client = make_api_app(EngineService(config=CFG, frames=frames, eta_model=eta_model)).test_client()
    request = rank_body(client, facility_id="HSP-004", requested_at=None)["ranking"]["request"]
    day_before = (datetime.fromisoformat(clock) - timedelta(days=1)).date().isoformat()
    assert (request["requested_at"], request["as_of_stock_date"]) == (clock, day_before)
