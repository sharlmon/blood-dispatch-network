import os
from pathlib import Path

import click

import yaml
from flask import Flask
from flask_cors import CORS


def load_settings(path: str | None = None) -> dict:
    path = path or os.environ.get("SETTINGS_FILE", str(Path(__file__).resolve().parents[1] / "config/settings.default.yaml"))
    with open(path) as f:
        return yaml.safe_load(f)


def create_app(settings_path: str | None = None, test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app, origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","))
    app.config["SETTINGS"] = load_settings(settings_path)
    app.config["DB_PATH"] = os.environ.get("DB_PATH", str(Path(__file__).resolve().parents[2] / "data" / "blood.sqlite"))

    if test_config:
        app.config.update(test_config)

    from .storage import init_app
    init_app(app)

    @app.cli.command("expire-confirmations")
    def expire_confirmations():
        """Release expired reservations; run periodically from a scheduler."""
        from .workflow import expire
        click.echo(f"Expired {expire()} confirmation(s)")

    from .commands import register
    register(app)

    from .routes import api

    app.register_blueprint(api, url_prefix="/api")
    return app
