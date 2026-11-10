from flask import Blueprint, current_app, g, jsonify

from .clerk_auth import require_auth

api = Blueprint("api", __name__)


@api.get("/health")
def health():
    return jsonify(status="ok", country=current_app.config["SETTINGS"]["country"])


@api.get("/me")
@require_auth
def me():
    """Who the server believes is calling, from the verified Clerk session. Used by the UI and tests."""
    return jsonify(g.auth.public())


# Protect workflow endpoints with `@require_hospital` (signed in AND acting for a hospital), or
# `@require_role("org:admin")`. Read the caller from `g.auth` (user_id, org_id, org_role) and put
# it in the audit log entry.
# TODO (Full-stack 1): workflow endpoints
#   POST /requests            create request -> ranked options (calls engine)
#   POST /requests/<id>/pick  lab worker picks an option
#   POST /requests/<id>/confirm  supplier confirms units on shelf
#   GET  /audit               audit log
# TODO (Full-stack 2): POST /sms  inbound SMS webhook (backend/sms parser)
