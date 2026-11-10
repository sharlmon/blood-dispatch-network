from flask import Blueprint, current_app, g, jsonify, request

from workflow.store import InvalidEvent, InvalidTransition, RequestNotFound, Store

from . import results
from .clerk_auth import require_auth, require_hospital
from .engine_service import EngineService, EngineUnavailable, InvalidRequest, parse_rank_input, plain

api = Blueprint("api", __name__)

LIST_DEFAULT, LIST_MAX = 20, 100


def error_response(status: int, code: str, message: str):
    """The API's error body: {"error": {"code", "message"}}."""
    resp = jsonify(error={"code": code, "message": message})
    resp.status_code = status
    return resp


@api.errorhandler(InvalidRequest)
@api.errorhandler(InvalidEvent)
def _invalid_request(err):
    return error_response(400, "invalid_request", err.message)


@api.errorhandler(RequestNotFound)
@api.errorhandler(results.ArtifactNotFound)
def _not_found(err):
    return error_response(404, "not_found", err.message)


@api.errorhandler(InvalidTransition)
def _invalid_transition(err):
    return error_response(409, "invalid_transition", err.message)


@api.errorhandler(EngineUnavailable)
def _engine_unavailable(err):
    return error_response(503, "engine_unavailable", err.message)


def _engine() -> EngineService:
    return current_app.extensions["engine"]


def _store() -> Store:
    return current_app.extensions["store"]


def _demo_clock():
    return (current_app.config["SETTINGS"] or {}).get("demo_clock")


def _actor() -> dict:
    return {"user_id": g.auth.user_id, "org_id": g.auth.org_id, "org_role": g.auth.org_role}


def _body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise InvalidRequest("Send a JSON object as the request body (Content-Type: application/json).")
    return body


def _limit() -> int:
    raw = request.args.get("limit", "")
    if not raw:
        return LIST_DEFAULT
    try:
        n = int(raw)
    except ValueError:
        n = 0
    if n < 1:
        raise InvalidRequest(f"limit must be a whole number from 1 to {LIST_MAX}.")
    return min(n, LIST_MAX)


# --------------------------------------------------------------------------- public


@api.get("/health")
def health():
    """Answers at once, even while the engine is still loading."""
    return jsonify(status="ok", country=current_app.config["SETTINGS"]["country"], engine=_engine().status())


@api.get("/results")
def results_index():
    """Committed DS2 artifacts: aggregate, synthetic, no personal fields."""
    root = current_app.config["RESULTS_DIR"]
    return jsonify(files=results.files(root), scenarios=results.scenarios(root))


@api.get("/results/<name>")
def result_file(name):
    root = current_app.config["RESULTS_DIR"]
    return jsonify(plain(results.read_result(root, name, request.args.get("scenario"))))


# --------------------------------------------------------------------------- signed in


@api.get("/me")
@require_auth
def me():
    """Who the server believes is calling, from the verified Clerk session. Used by the UI and tests."""
    return jsonify(g.auth.public())


# Protect workflow endpoints with `@require_hospital` (signed in AND acting for a hospital), or
# `@require_role("org:admin")`. Read the caller from `g.auth` (user_id, org_id, org_role) and put
# it in the audit log entry.


@api.get("/facilities")
@require_hospital
def facilities():
    return jsonify(facilities=_engine().facilities())


@api.post("/rank")
@require_hospital
def rank():
    """Preview a ranking. Nothing is stored or audited."""
    return jsonify(_engine().rank(_body(), demo_clock=_demo_clock()))


@api.post("/requests")
@require_hospital
def create_request():
    """A lab worker submits a request: rank it, then store it with its audit entry."""
    asked = parse_rank_input(_body(), demo_clock=_demo_clock())
    result = _engine().rank(asked)  # a failed ranking stores nothing
    record, audit = _store().create_request(result, component=asked.component, actor=_actor())
    return jsonify(request=record, result=result, audit=audit), 201


@api.get("/requests")
@require_hospital
def list_requests():
    return jsonify(requests=_store().list_requests(g.auth.org_id, limit=_limit()))


@api.get("/requests/<request_id>")
@require_hospital
def get_request(request_id):
    record, result, audit = _store().get_request(request_id, g.auth.org_id)
    return jsonify(request=record, result=result, audit=audit)


@api.post("/requests/<request_id>/events")
@require_hospital
def record_event(request_id):
    """A human decision or workflow step: pick, shelf_confirmed, dispatched, ... No free text.
    A facility_id sent with a site step (store.SITE_STEPS) must be the current selection (409 otherwise)."""
    body = _body()
    record, audit = _store().record_event(request_id, body.get("action"), body.get("facility_id"), actor=_actor())
    return jsonify(request=record, audit=audit)


@api.get("/prealerts")
@require_hospital
def prealerts():
    """Evening pre-alert list from results/prealerts.json. Works without the engine (names null)."""
    try:
        names = _engine().facility_names()
    except EngineUnavailable:
        names = {}
    return jsonify(plain(results.read_prealerts(current_app.config["RESULTS_DIR"], names)))


# TODO (Full-stack 2): POST /sms  inbound SMS webhook (backend/sms parser)
