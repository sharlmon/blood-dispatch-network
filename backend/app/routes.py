from flask import Blueprint, current_app, jsonify

api = Blueprint("api", __name__)


@api.get("/health")
def health():
    return jsonify(status="ok", country=current_app.config["SETTINGS"]["country"])


# TODO (Full-stack 1): workflow endpoints
#   POST /requests            create request -> ranked options (calls engine)
#   POST /requests/<id>/pick  lab worker picks an option
#   POST /requests/<id>/confirm  supplier confirms units on shelf
#   GET  /audit               audit log
# TODO (Full-stack 2): POST /sms  inbound SMS webhook (backend/sms parser)
