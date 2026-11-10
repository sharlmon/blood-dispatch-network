import os
import threading
from pathlib import Path

import yaml
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

load_dotenv()  # reads backend/.env when present; real environment variables win

BACKEND_DIR = Path(__file__).resolve().parents[1]

_ERROR_CODES = {400: "invalid_request", 404: "not_found", 405: "method_not_allowed", 500: "internal_error"}
_ERROR_MESSAGES = {
    404: "Nothing here. Check the address.",
    405: "This address does not accept that method.",
    500: "Something went wrong on the server. Try again, or use the phone process.",
}


def backend_path(raw: str | Path) -> Path:
    """Relative paths resolve from backend/, the documented working directory."""
    path = Path(raw).expanduser()
    return path if path.is_absolute() else BACKEND_DIR / path


def load_settings(path: str | None = None) -> dict:
    path = path or backend_path(os.environ.get("SETTINGS_FILE", "config/settings.default.yaml"))
    with open(path) as f:
        return yaml.safe_load(f)


def _register_error_handlers(app: Flask) -> None:
    """404, 405 and 500 under /api answer with the API's error body, like every other error."""

    @app.errorhandler(HTTPException)
    def _http_error(err: HTTPException):
        if not (request.path == "/api" or request.path.startswith("/api/")):
            return err
        status = err.code or 500
        code = _ERROR_CODES.get(status) or (err.name or "error").lower().replace(" ", "_")
        resp = jsonify(error={"code": code, "message": _ERROR_MESSAGES.get(status) or err.description})
        resp.status_code = status
        for name, value in err.get_headers():
            if name.lower() == "allow":
                resp.headers[name] = value
        return resp


def _start_warm_up(engine) -> None:
    """Load the engine in the background so the first click does not wait for the data (~15 s)."""
    if os.environ.get("ENGINE_WARMUP", "1").strip().lower() in ("0", "false", "no", "off"):
        return
    if engine.status()["state"] != "idle":  # an injected engine that is already ready
        return
    threading.Thread(target=engine.warm_up, name="engine-warm-up", daemon=True).start()


def create_app(settings_path: str | None = None, *, engine=None, store=None) -> Flask:
    """``engine`` (an EngineService) and ``store`` (a workflow Store) can be injected for tests."""
    from workflow.store import Store

    from . import results
    from .clerk_auth import init_clerk
    from .engine_service import EngineService
    from .routes import api

    app = Flask(__name__)
    app.json.sort_keys = False  # keep the engine's key order (spec section 9) in responses
    CORS(app, origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","))
    app.config["SETTINGS"] = load_settings(settings_path)
    app.config["DB_PATH"] = os.environ.get("DB_PATH", "../data/blood.sqlite")
    app.config["RESULTS_DIR"] = results.results_dir()

    init_clerk(app)
    app.extensions["engine"] = engine if engine is not None else EngineService()
    app.extensions["store"] = store if store is not None else Store(backend_path(app.config["DB_PATH"]))
    _register_error_handlers(app)

    app.register_blueprint(api, url_prefix="/api")
    _start_warm_up(app.extensions["engine"])
    return app
