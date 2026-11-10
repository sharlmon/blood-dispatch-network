import os

import yaml
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

load_dotenv()  # reads backend/.env when present; real environment variables win


def load_settings(path: str | None = None) -> dict:
    path = path or os.environ.get("SETTINGS_FILE", "config/settings.default.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def create_app(settings_path: str | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app, origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","))
    app.config["SETTINGS"] = load_settings(settings_path)
    app.config["DB_PATH"] = os.environ.get("DB_PATH", "../data/blood.sqlite")

    from .clerk_auth import init_clerk
    from .routes import api

    init_clerk(app)

    app.register_blueprint(api, url_prefix="/api")
    return app
