"""Requests, their status changes and the audit log, through the API (no DATA_DIR needed)."""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

import pytest

import workflow.store as store_module
from app import BACKEND_DIR, create_app
from app.engine_service import EngineService
from workflow.store import SITE_STEPS, TRANSITIONS, InvalidTransition, Store

REQUEST = {"facility_id": "HSP-R", "patient_group": "O+", "units_needed": 2, "requested_at": "2026-03-10T01:00:00"}
RECORD_KEYS = ["id", "created_at", "facility_id", "facility_name", "patient_group", "units_needed", "component",
               "limit_h", "requested_at", "status", "selected_facility_id", "selected_name"]
AUDIT_KEYS = ["id", "request_id", "at", "action", "actor", "detail"]
DEMO_ACTOR = {"user_id": "user_demo", "org_id": "org_demo", "org_role": "org:admin"}

# How to bring a new request to each status: (action, facility_id) steps.
STEPS = {
    "open": [],
    "awaiting_shelf": [("pick", "HSP-B")],
    "confirmed": [("pick", "HSP-B"), ("shelf_confirmed", None)],
    "dispatched": [("pick", "HSP-B"), ("shelf_confirmed", None), ("dispatched", None)],
    "arrived": [("pick", "HSP-B"), ("shelf_confirmed", None), ("dispatched", None), ("arrived", None)],
    "escalated": [("emergency_group_o", None)],
    "cancelled": [("cancel", None)],
}
# The contract's table: (action, from status) -> status afterwards. Anything missing is a 409.
ALLOWED = {
    **{("pick", s): "awaiting_shelf" for s in ("open", "escalated", "awaiting_shelf")},
    ("shelf_confirmed", "awaiting_shelf"): "confirmed",
    ("dispatched", "confirmed"): "dispatched",
    ("arrived", "dispatched"): "arrived",
    ("not_on_shelf", "awaiting_shelf"): "open",
    ("confirm_timeout", "awaiting_shelf"): "open",
    **{(a, s): ("escalated" if s == "open" else s)
       for a in ("emergency_group_o", "transfer_patient")
       for s in ("open", "escalated", "awaiting_shelf", "confirmed", "dispatched")},
    **{("cancel", s): "cancelled" for s in ("open", "escalated", "awaiting_shelf", "confirmed")},
}


def create(client, headers=None, **change) -> dict:
    r = client.post("/api/requests", json={**REQUEST, **change}, headers=headers)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def event(client, request_id, action, facility_id=None, headers=None, **extra):
    body = {"action": action, **extra}
    if facility_id is not None:
        body["facility_id"] = facility_id
    return client.post(f"/api/requests/{request_id}/events", json=body, headers=headers)


def request_in(client, status) -> str:
    request_id = create(client)["request"]["id"]
    for action, facility in STEPS[status]:
        r = event(client, request_id, action, facility)
        assert r.status_code == 200, r.get_json()
    assert client.get(f"/api/requests/{request_id}").get_json()["request"]["status"] == status
    return request_id


def as_user(user, org, role="org:member"):
    return {"Authorization": f"Bearer {user}:{org}:{role}"}


# --------------------------------------------------------------------------- create, list, get


def test_create_ranks_stores_and_audits(api_client):
    body = create(api_client)
    assert list(body) == ["request", "result", "audit"]
    record = body["request"]
    assert list(record) == RECORD_KEYS
    assert re.fullmatch(r"BDN-[0-9A-F]{8}", record["id"])
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+03:00", record["created_at"])
    assert {k: record[k] for k in RECORD_KEYS[2:]} == {
        "facility_id": "HSP-R", "facility_name": "Requesting Hospital", "patient_group": "O+", "units_needed": 2,
        "component": "RBC", "limit_h": 6.0, "requested_at": "2026-03-10T01:00:00", "status": "open",
        "selected_facility_id": None, "selected_name": None,
    }
    # The stored result is exactly what the stateless preview gives.
    assert body["result"] == api_client.post("/api/rank", json=REQUEST).get_json()

    [entry] = body["audit"]
    assert list(entry) == AUDIT_KEYS
    assert (entry["request_id"], entry["action"], entry["actor"]) == (record["id"], "request_created", DEMO_ACTOR)
    assert entry["at"].endswith("+03:00")
    assert entry["detail"] == {
        "patient_group": "O+", "units_needed": 2, "component": "RBC", "limit_h": 6.0,
        "requested_at": "2026-03-10T01:00:00", "as_of_stock_date": "2026-03-09", "mode": "model",
        "advice": None, "model_used": True, "option_facility_ids": ["HSP-B", "RBTC-A", "RBTC-B"],
        "baseline_facility_id": "RBTC-A",
    }


def test_create_keeps_the_normalised_group_and_the_limit_used(api_client):
    record = create(api_client, patient_group="ab\u2212", units_needed=1, limit_h=2.5)["request"]
    assert (record["patient_group"], record["limit_h"]) == ("AB-", 2.5)
    record = create(api_client, patient_group="UNKNOWN")["request"]
    assert record["patient_group"] == "unknown"


def test_list_is_newest_first_and_limited(api_client):
    made = [create(api_client)["request"]["id"] for _ in range(4)]
    listed = api_client.get("/api/requests").get_json()["requests"]
    assert [r["id"] for r in listed] == made[::-1]
    assert all(list(r) == RECORD_KEYS for r in listed)
    assert [r["id"] for r in api_client.get("/api/requests?limit=2").get_json()["requests"]] == made[:1:-1]
    assert len(api_client.get("/api/requests?limit=500").get_json()["requests"]) == 4  # capped at 100


@pytest.mark.parametrize("limit", ["0", "-3", "abc", "2.5"])
def test_list_limit_must_be_a_positive_whole_number(api_client, limit):
    r = api_client.get(f"/api/requests?limit={limit}")
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "invalid_request"


def test_get_returns_record_result_and_trail(api_client):
    made = create(api_client)
    request_id = made["request"]["id"]
    event(api_client, request_id, "pick", "HSP-B")
    body = api_client.get(f"/api/requests/{request_id}").get_json()
    assert list(body) == ["request", "result", "audit"]
    assert body["request"]["status"] == "awaiting_shelf"
    assert body["result"] == made["result"]
    assert [e["action"] for e in body["audit"]] == ["request_created", "pick"]
    assert [e["id"] for e in body["audit"]] == sorted(e["id"] for e in body["audit"])


def test_unknown_request_is_404(api_client):
    for r in (api_client.get("/api/requests/BDN-00000000"),
              event(api_client, "BDN-00000000", "cancel"),
              api_client.get("/api/requests/..%2F..%2Fetc")):
        assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found"


def test_other_organisations_cannot_see_or_change_a_request(make_api_app, api_engine):
    client = make_api_app(api_engine, auth="tokens").test_client()
    alice, bob = as_user("user_alice", "org_lakeview"), as_user("user_bob", "org_hillcrest", "org:admin")
    request_id = create(client, headers=alice)["request"]["id"]

    assert client.get("/api/requests", headers=bob).get_json() == {"requests": []}
    assert client.get(f"/api/requests/{request_id}", headers=bob).status_code == 404
    for action, facility in [("pick", "HSP-B"), ("cancel", None)]:
        r = event(client, request_id, action, facility, headers=bob)
        assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found"

    r = event(client, request_id, "pick", "HSP-B", headers=alice)
    assert r.status_code == 200
    assert r.get_json()["audit"][-1]["actor"] == {"user_id": "user_alice", "org_id": "org_lakeview",
                                                  "org_role": "org:member"}
    assert [x["id"] for x in client.get("/api/requests", headers=alice).get_json()["requests"]] == [request_id]
    assert client.get("/api/requests", headers=as_user("user_carol", "")).status_code == 403  # no hospital


# --------------------------------------------------------------------------- transitions


def test_the_transition_table_matches_the_contract():
    assert set(TRANSITIONS) == {a for a, _ in ALLOWED}
    for action, (allowed_from, _) in TRANSITIONS.items():
        assert set(allowed_from) == {s for a, s in ALLOWED if a == action}


@pytest.mark.parametrize("status", list(STEPS))
@pytest.mark.parametrize("action", list(TRANSITIONS))
def test_every_action_from_every_status(api_client, action, status):
    request_id = request_in(api_client, status)
    before = api_client.get(f"/api/requests/{request_id}").get_json()
    r = event(api_client, request_id, action, "RBTC-A" if action == "pick" else None)
    after = api_client.get(f"/api/requests/{request_id}").get_json()
    if (action, status) in ALLOWED:
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert list(body) == ["request", "audit"]
        assert body["request"]["status"] == ALLOWED[action, status]
        assert body["audit"] == after["audit"]
        last = body["audit"][-1]
        assert last["action"] == action and last["actor"] == DEMO_ACTOR
        assert (last["detail"]["from_status"], last["detail"]["to_status"]) == (status, ALLOWED[action, status])
    else:
        assert r.status_code == 409
        assert r.get_json()["error"]["code"] == "invalid_transition"
        assert after == before  # nothing changed, nothing audited


def test_the_happy_path_records_every_step(api_client):
    request_id = create(api_client)["request"]["id"]
    r = event(api_client, request_id, "pick", "HSP-B")
    record = r.get_json()["request"]
    assert (record["status"], record["selected_facility_id"], record["selected_name"]) == (
        "awaiting_shelf", "HSP-B", "Lending Hospital")
    assert r.get_json()["audit"][-1]["detail"] == {
        "from_status": "open", "to_status": "awaiting_shelf", "facility_id": "HSP-B",
        "facility_name": "Lending Hospital", "previous_facility_id": None, "option_rank": 1, "is_baseline": False}
    for action, status in [("shelf_confirmed", "confirmed"), ("dispatched", "dispatched"), ("arrived", "arrived")]:
        r = event(api_client, request_id, action)
        assert r.get_json()["request"]["status"] == status
        assert r.get_json()["request"]["selected_facility_id"] == "HSP-B"
        assert r.get_json()["audit"][-1]["detail"]["facility_id"] == "HSP-B"
    actions = [e["action"] for e in r.get_json()["audit"]]
    assert actions == ["request_created", "pick", "shelf_confirmed", "dispatched", "arrived"]


@pytest.mark.parametrize("action", ["not_on_shelf", "confirm_timeout"])
def test_no_stock_or_no_answer_goes_back_to_the_list(api_client, action):
    request_id = request_in(api_client, "awaiting_shelf")
    r = event(api_client, request_id, action)
    record, last = r.get_json()["request"], r.get_json()["audit"][-1]
    assert (record["status"], record["selected_facility_id"], record["selected_name"]) == ("open", None, None)
    assert last["detail"]["previous_facility_id"] == "HSP-B"
    assert last["detail"]["waited_minutes"] >= 0
    # Then the next option.
    r = event(api_client, request_id, "pick", "RBTC-A")
    assert r.get_json()["request"]["selected_facility_id"] == "RBTC-A"
    assert r.get_json()["audit"][-1]["detail"]["option_rank"] == 2


def test_changing_the_pick_while_waiting_is_recorded(api_client):
    request_id = request_in(api_client, "awaiting_shelf")
    r = event(api_client, request_id, "pick", "RBTC-B")
    assert r.get_json()["request"]["selected_facility_id"] == "RBTC-B"
    assert r.get_json()["audit"][-1]["detail"]["previous_facility_id"] == "HSP-B"


def test_escalation_rules(api_client):
    request_id = create(api_client)["request"]["id"]
    assert event(api_client, request_id, "emergency_group_o").get_json()["request"]["status"] == "escalated"
    assert event(api_client, request_id, "transfer_patient").get_json()["request"]["status"] == "escalated"
    assert event(api_client, request_id, "pick", "HSP-B").get_json()["request"]["status"] == "awaiting_shelf"
    r = event(api_client, request_id, "transfer_patient")  # audited, status unchanged
    assert r.get_json()["request"]["status"] == "awaiting_shelf"
    assert r.get_json()["request"]["selected_facility_id"] == "HSP-B"
    assert [e["action"] for e in r.get_json()["audit"]][-4:] == [
        "emergency_group_o", "transfer_patient", "pick", "transfer_patient"]


def test_cancel_keeps_the_selection_on_record(api_client):
    request_id = request_in(api_client, "confirmed")
    r = event(api_client, request_id, "cancel")
    assert r.get_json()["request"]["status"] == "cancelled"
    assert r.get_json()["audit"][-1]["detail"] == {"from_status": "confirmed", "to_status": "cancelled",
                                                   "facility_id": "HSP-B"}


# --------------------------------------------------------------------------- event checks


@pytest.mark.parametrize("facility", [None, "", 7, ["HSP-B"], "HSP-C", "SAT-S", "HSP-R", "HSP-404"])
def test_a_pick_must_name_an_offered_site(api_client, facility):
    request_id = create(api_client)["request"]["id"]
    body = {"action": "pick"} if facility is None else {"action": "pick", "facility_id": facility}
    r = api_client.post(f"/api/requests/{request_id}/events", json=body)
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "invalid_request"
    assert api_client.get(f"/api/requests/{request_id}").get_json()["request"]["status"] == "open"


def test_todays_rule_can_be_picked_even_when_it_is_not_listed(api_client):
    made = create(api_client, top_n=1)
    assert made["audit"][0]["detail"]["option_facility_ids"] == ["HSP-B"]
    r = event(api_client, made["request"]["id"], "pick", "RBTC-A")
    assert r.status_code == 200
    assert r.get_json()["request"]["selected_name"] == "Centre A"
    detail = r.get_json()["audit"][-1]["detail"]
    assert (detail["option_rank"], detail["is_baseline"]) == (None, True)


@pytest.mark.parametrize("action", sorted(SITE_STEPS))
def test_a_site_step_that_names_a_site_must_name_the_selected_one(api_client, action):
    """A screen that missed a re-pick cannot book a step against a site that is no longer selected."""
    [status] = [s for a, s in ALLOWED if a == action]
    request_id = request_in(api_client, status)  # HSP-B picked
    if status == "awaiting_shelf":  # a colleague re-picks while another screen still shows HSP-B
        assert event(api_client, request_id, "pick", "RBTC-A").status_code == 200
        selected, name, stale = "RBTC-A", "Centre A", "HSP-B"
    else:
        selected, name, stale = "HSP-B", "Lending Hospital", "RBTC-A"
    before = api_client.get(f"/api/requests/{request_id}").get_json()

    for wrong in (stale, "NOT-A-SITE"):
        r = event(api_client, request_id, action, wrong)
        assert r.status_code == 409, r.get_json()
        error = r.get_json()["error"]
        assert error["code"] == "invalid_transition" and name in error["message"] and wrong in error["message"]
    for bad in (7, "", "  ", ["HSP-B"]):
        r = event(api_client, request_id, action, bad)
        assert r.status_code == 400 and r.get_json()["error"]["code"] == "invalid_request"
    assert api_client.get(f"/api/requests/{request_id}").get_json() == before  # nothing changed, nothing audited

    r = event(api_client, request_id, action, f" {selected} ")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["request"]["status"] == ALLOWED[action, status]
    detail = r.get_json()["audit"][-1]["detail"]
    back_to_the_list = action in ("not_on_shelf", "confirm_timeout")
    assert detail["previous_facility_id" if back_to_the_list else "facility_id"] == selected


@pytest.mark.parametrize("body", [{"action": "teleport"}, {"action": None}, {}, {"action": ["pick"]},
                                  {"action": "PICK", "facility_id": "HSP-B"}])
def test_unknown_actions_are_400(api_client, body):
    request_id = create(api_client)["request"]["id"]
    r = api_client.post(f"/api/requests/{request_id}/events", json=body)
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "invalid_request"


def test_event_body_must_be_a_json_object(api_client):
    request_id = create(api_client)["request"]["id"]
    for kwargs in ({"json": ["pick"]}, {"data": "pick", "content_type": "text/plain"}, {}):
        r = api_client.post(f"/api/requests/{request_id}/events", **kwargs)
        assert r.status_code == 400


# --------------------------------------------------------------------------- data minimisation


def stored_bytes(path: Path) -> bytes:
    """Every byte SQLite keeps for this database, including any journal files."""
    return b"".join(p.read_bytes() for p in path.parent.glob(path.name + "*"))


def test_extra_fields_are_never_stored(api_app, tmp_path):
    client = api_app.test_client()
    db = api_app.extensions["store"].path
    extra = {"patient_name": "Wanjiku ZQXJ", "clinical_indication": "PPH ZQXJ", "patient_id": "MRN-ZQXJ",
             "note": "free text ZQXJ"}
    made = create(client, **extra)
    request_id = made["request"]["id"]
    assert "ZQXJ" not in str(made)
    assert event(client, request_id, "pick", "HSP-B", note="call back ZQXJ", patient_name="ZQXJ").status_code == 200
    assert event(client, request_id, "not_on_shelf", comment="free text ZQXJ").status_code == 200

    assert db.is_file()
    assert b"ZQXJ" not in stored_bytes(db)
    for path in (f"/api/requests/{request_id}", "/api/requests"):
        assert "ZQXJ" not in client.get(path).get_data(as_text=True)
    with sqlite3.connect(db) as conn:
        columns = {table: [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
                   for table in ("requests", "audit")}
    assert columns["requests"] == ["id", "org_id", "user_id", "created_at", "facility_id", "facility_name",
                                   "patient_group", "units_needed", "component", "limit_h", "requested_at",
                                   "status", "selected_facility_id", "selected_name", "result_json"]
    assert columns["audit"] == ["id", "request_id", "at", "action", "user_id", "org_id", "org_role",
                                "detail_json"]


def test_a_failed_ranking_stores_nothing(api_app, make_api_app, monkeypatch, tmp_path):
    client = api_app.test_client()
    for change in ({"facility_id": "HSP-404"}, {"units_needed": 0}, {"component": "PLT"},
                   {"requested_at": "2026-03-08T23:59:00"}):  # before the first stock count
        assert client.post("/api/requests", json={**REQUEST, **change}).status_code == 400

    empty = tmp_path / "no-data"
    empty.mkdir()
    monkeypatch.setenv("DATA_DIR", str(empty))
    monkeypatch.delenv("ENGINE_DB_PATH", raising=False)
    down = make_api_app(EngineService(), store=api_app.extensions["store"]).test_client()
    r = down.post("/api/requests", json=REQUEST)
    assert r.status_code == 503 and r.get_json()["error"]["code"] == "engine_unavailable"

    assert client.get("/api/requests").get_json() == {"requests": []}
    db = api_app.extensions["store"].path
    if db.exists():
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM requests").fetchone() == (0,)
            assert conn.execute("SELECT COUNT(*) FROM audit").fetchone() == (0,)


# --------------------------------------------------------------------------- store details


def test_request_ids_retry_on_collision(api_client, monkeypatch):
    drawn = iter(["BDN-0000000A", "BDN-0000000A", "BDN-0000000A", "BDN-0000000B"])
    monkeypatch.setattr(store_module, "new_request_id", lambda: next(drawn))
    assert create(api_client)["request"]["id"] == "BDN-0000000A"
    assert create(api_client)["request"]["id"] == "BDN-0000000B"


def test_the_store_file_is_created_on_first_use(tmp_path):
    db = tmp_path / "nested" / "folder" / "api.sqlite"
    store = Store(db)
    assert not db.exists()
    assert store.list_requests("org_x") == []
    assert db.is_file()


def test_a_relative_db_path_resolves_from_backend(monkeypatch, tmp_path, api_engine):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DB_PATH", "../data/blood.sqlite")
    app = create_app(str(BACKEND_DIR / "config" / "settings.default.yaml"), engine=api_engine)
    assert app.config["DB_PATH"] == "../data/blood.sqlite"
    assert app.extensions["store"].path == BACKEND_DIR / "../data/blood.sqlite"
    monkeypatch.setenv("DB_PATH", str(tmp_path / "abs.sqlite"))
    app = create_app(str(BACKEND_DIR / "config" / "settings.default.yaml"), engine=api_engine)
    assert app.extensions["store"].path == tmp_path / "abs.sqlite"


def test_concurrent_events_apply_one_at_a_time(api_client, api_app):
    request_id = request_in(api_client, "awaiting_shelf")
    store = api_app.extensions["store"]
    outcomes, barrier = [], threading.Barrier(8)

    def confirm():
        barrier.wait()
        try:
            store.record_event(request_id, "shelf_confirmed", actor=DEMO_ACTOR)
            outcomes.append("ok")
        except InvalidTransition:
            outcomes.append("409")

    threads = [threading.Thread(target=confirm) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    assert sorted(outcomes) == ["409"] * 7 + ["ok"]
    audit = api_client.get(f"/api/requests/{request_id}").get_json()["audit"]
    assert [e["action"] for e in audit].count("shelf_confirmed") == 1
