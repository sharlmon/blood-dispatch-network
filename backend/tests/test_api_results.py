"""Results (DS2 artifacts), the evening pre-alert list, and which endpoints need sign-in."""

from __future__ import annotations

import json

import pytest

from app import create_app
from app.engine_service import EngineService
from app.results import REPO_ROOT, RESULT_FILES

RESULTS = REPO_ROOT / "results"
PREALERT_KEYS = ["generated_at", "stock_as_of", "alerts", "missing_snapshot", "assumptions", "synthetic_data",
                 "source"]


def committed(*parts) -> dict:
    return json.loads(RESULTS.joinpath(*parts).read_text(encoding="utf-8"))


@pytest.fixture
def engine_down(monkeypatch, tmp_path):
    """An engine whose data cannot be loaded."""
    empty = tmp_path / "no-data"
    empty.mkdir()
    monkeypatch.setenv("DATA_DIR", str(empty))
    monkeypatch.delenv("ENGINE_DB_PATH", raising=False)
    return EngineService()


def write_prealerts(folder, alerts, missing=(), **envelope):
    folder.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": 1, "generated_at": "2026-11-10T15:00:00+03:00", "synthetic_data": True, **envelope,
           "result": {"generated_at": "2026-03-09T18:00:00+03:00", "stock_as_of": "2026-03-08",
                      "alerts": list(alerts), "missing_snapshot": list(missing), "assumptions": ["Synthetic data."]}}
    (folder / "prealerts.json").write_text(json.dumps(doc))
    return doc


# --------------------------------------------------------------------------- results


def test_index_lists_the_files_and_scenarios(api_client):
    body = api_client.get("/api/results").get_json()
    assert body["files"] == ["arrival_validation", "data_quality", "prealert_evaluation", "replay_summary",
                             "summary"]
    assert {"hospital-reserve-5", "hospital-reserve-10"} <= set(body["scenarios"])
    assert body["scenarios"] == sorted(body["scenarios"])


@pytest.mark.parametrize("name", RESULT_FILES)
def test_each_file_is_served_unchanged(api_client, name):
    r = api_client.get(f"/api/results/{name}")
    assert r.status_code == 200
    assert r.get_json() == committed(f"{name}.json")


@pytest.mark.parametrize("scenario", ["hospital-reserve-5", "hospital-reserve-10"])
def test_a_scenario_file(api_client, scenario):
    r = api_client.get(f"/api/results/replay_summary?scenario={scenario}")
    assert r.status_code == 200
    assert r.get_json() == committed(scenario, "replay_summary.json")
    assert api_client.get(f"/api/results/summary?scenario={scenario}&x=1").get_json() == committed(
        scenario, "summary.json")


@pytest.mark.parametrize(
    "url",
    [
        "/api/results/arrival_model",  # committed, but not one of the served files
        "/api/results/prealerts",
        "/api/results/summary.json",
        "/api/results/SUMMARY",
        "/api/results/nope",
        "/api/results/summary?scenario=nope",
        "/api/results/summary?scenario=..",
        "/api/results/summary?scenario=.",
        "/api/results/summary?scenario=../results",
        "/api/results/summary?scenario=%2e%2e",
        "/api/results/summary?scenario=%2e%2e%2f%2e%2e",
        "/api/results/summary?scenario=hospital-reserve-5/..",
        "/api/results/summary?scenario=hospital-reserve-5%2f..%2f..",
        "/api/results/summary?scenario=/etc",
        "/api/results/summary?scenario=%2Fetc",
        "/api/results/summary?scenario=..%5C..",
        "/api/results/summary?scenario=hospital-reserve-5%5C..",
        "/api/results/summary?scenario=hospital-reserve-5%00",
        "/api/results/..%2Fsummary",
        "/api/results/%2e%2e",
        "/api/results/%2e%2e%2f%2e%2e%2fbackend%2fconfig%2fkenya",
        "/api/results/..%5Csummary",
        "/api/results/%2Fetc%2Fpasswd",
        "/api/results/../../README",
        "/api/results/summary/..",
    ],
)
def test_unknown_names_scenarios_and_traversal_are_404(api_client, url):
    r = api_client.get(url)
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == "not_found"


def test_a_scenario_without_that_file_is_404(make_api_app, api_engine, tmp_path):
    (tmp_path / "res" / "only-summary").mkdir(parents=True)
    (tmp_path / "res" / "only-summary" / "summary.json").write_text('{"result": {}}')
    (tmp_path / "res" / "no-summary").mkdir()
    app = make_api_app(api_engine)
    app.config["RESULTS_DIR"] = tmp_path / "res"
    client = app.test_client()
    assert client.get("/api/results").get_json() == {"files": [], "scenarios": ["only-summary"]}
    assert client.get("/api/results/summary?scenario=only-summary").get_json() == {"result": {}}
    assert client.get("/api/results/replay_summary?scenario=only-summary").status_code == 404
    assert client.get("/api/results/summary?scenario=no-summary").status_code == 404
    assert client.get("/api/results/summary").status_code == 404


def test_results_dir_comes_from_env_relative_to_the_repo_root(make_api_app, api_engine, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RESULTS_DIR", "results")
    app = make_api_app(api_engine)
    assert app.config["RESULTS_DIR"] == RESULTS
    assert app.test_client().get("/api/results/summary").get_json() == committed("summary.json")

    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "summary.json").write_text('{"result": {"n": 1}}')
    monkeypatch.setenv("RESULTS_DIR", str(other))
    client = make_api_app(api_engine).test_client()
    assert client.get("/api/results").get_json() == {"files": ["summary"], "scenarios": []}
    assert client.get("/api/results/summary").get_json() == {"result": {"n": 1}}


def test_a_missing_results_dir_lists_nothing(make_api_app, api_engine, tmp_path):
    app = make_api_app(api_engine)
    app.config["RESULTS_DIR"] = tmp_path / "missing"
    client = app.test_client()
    assert client.get("/api/results").get_json() == {"files": [], "scenarios": []}
    assert client.get("/api/results/summary").status_code == 404


# --------------------------------------------------------------------------- pre-alerts


def test_prealerts_work_without_the_engine(make_api_app, engine_down):
    client = make_api_app(engine_down).test_client()
    r = client.get("/api/prealerts")
    assert r.status_code == 200
    body = r.get_json()
    artifact = committed("prealerts.json")
    assert list(body) == PREALERT_KEYS
    assert body["generated_at"] == artifact["result"]["generated_at"]
    assert body["stock_as_of"] == artifact["result"]["stock_as_of"]
    assert body["assumptions"] == artifact["result"]["assumptions"]
    assert body["synthetic_data"] is True
    assert body["source"] == "results/prealerts.json"
    assert len(body["alerts"]) == len(artifact["result"]["alerts"]) > 0
    assert len(body["missing_snapshot"]) == len(artifact["result"]["missing_snapshot"])
    unnamed = [{k: v for k, v in a.items() if k != "facility_name"} for a in body["alerts"]]
    assert unnamed == artifact["result"]["alerts"]
    assert all(row["facility_name"] is None for row in body["alerts"] + body["missing_snapshot"])
    assert client.get("/api/health").get_json()["engine"]["state"] == "error"


def test_prealerts_name_the_facilities_when_the_engine_is_up(make_api_app, api_engine, tmp_path):
    alert = {"facility_id": "HSP-B", "blood_group": "O+", "component": "RBC", "recorded_units": 0,
             "human_review_required": True, "reason": "known_zero_stock_for_component_previous_closing_snapshot"}
    write_prealerts(tmp_path / "res", [alert, {**alert, "facility_id": "HSP-404"}],
                    missing=[{"facility_id": "HSP-C", "blood_group": "O+", "component": "RBC"}])
    app = make_api_app(api_engine)
    app.config["RESULTS_DIR"] = tmp_path / "res"
    body = app.test_client().get("/api/prealerts").get_json()
    assert [a["facility_name"] for a in body["alerts"]] == ["Lending Hospital", None]
    assert body["alerts"][0] == {**alert, "facility_name": "Lending Hospital"}
    assert body["missing_snapshot"][0]["facility_name"] == "Remote Hospital"
    assert (body["generated_at"], body["stock_as_of"]) == ("2026-03-09T18:00:00+03:00", "2026-03-08")
    assert body["source"] == "prealerts.json"  # outside the repo: no server folders shown


def test_prealerts_never_claim_real_data_by_default(make_api_app, api_engine, tmp_path):
    doc = write_prealerts(tmp_path / "res", [])
    del doc["synthetic_data"]
    (tmp_path / "res" / "prealerts.json").write_text(json.dumps(doc))
    app = make_api_app(api_engine)
    app.config["RESULTS_DIR"] = tmp_path / "res"
    assert app.test_client().get("/api/prealerts").get_json()["synthetic_data"] is True


def test_missing_prealerts_artifact_is_404(make_api_app, api_engine, tmp_path):
    app = make_api_app(api_engine)
    app.config["RESULTS_DIR"] = tmp_path
    r = app.test_client().get("/api/prealerts")
    assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found"


# --------------------------------------------------------------------------- sign-in


PROTECTED = [
    ("get", "/api/facilities"),
    ("post", "/api/rank"),
    ("post", "/api/requests"),
    ("get", "/api/requests"),
    ("get", "/api/requests/BDN-00000000"),
    ("post", "/api/requests/BDN-00000000/events"),
    ("get", "/api/prealerts"),
    ("get", "/api/me"),
]


def test_without_clerk_protected_endpoints_fail_closed(make_api_app, api_engine):
    client = make_api_app(api_engine, auth="unconfigured").test_client()
    for method, path in PROTECTED:
        r = getattr(client, method)(path, json={"facility_id": "HSP-R"})
        assert r.status_code == 503, path
        assert r.get_json()["error"]["code"] == "auth_not_configured"
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/results").status_code == 200
    assert client.get("/api/results/summary").status_code == 200
    assert client.get("/api/results/summary?scenario=hospital-reserve-5").status_code == 200


def test_signed_in_without_a_hospital_is_403(make_api_app, api_engine):
    client = make_api_app(api_engine, auth="tokens").test_client()
    for method, path in PROTECTED[:-1]:
        r = getattr(client, method)(path, json={}, headers={"Authorization": "Bearer user_x::"})
        assert r.status_code == 403 and r.get_json()["error"]["code"] == "hospital_required", path
    r = client.get("/api/facilities")
    assert r.status_code == 401 and r.get_json()["error"]["code"] == "missing_token"


def test_the_default_app_starts_without_data_or_a_database(monkeypatch, tmp_path):
    """create_app() with nothing injected: no warm-up in tests, no files touched until needed."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db" / "api.sqlite"))
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.delenv("RESULTS_DIR", raising=False)
    app = create_app()
    client = app.test_client()
    assert client.get("/api/health").get_json()["engine"]["state"] == "idle"
    assert not (tmp_path / "db").exists()
    assert client.get("/api/requests").get_json() == {"requests": []}
    assert (tmp_path / "db" / "api.sqlite").is_file()
