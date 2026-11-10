import os
import json
import sqlite3
from pathlib import Path

import click

import yaml
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

load_dotenv()  # reads backend/.env when present; real environment variables win


def load_settings(path: str | None = None) -> dict:
    path = path or os.environ.get("SETTINGS_FILE", str(Path(__file__).resolve().parents[1] / "config/settings.default.yaml"))
    with open(path) as f:
        return yaml.safe_load(f)


def create_app(settings_path: str | None = None, test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app, origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","))
    app.config["SETTINGS"] = load_settings(settings_path)
    app.config["DB_PATH"] = os.environ.get("DB_PATH", str(Path(__file__).resolve().parents[2] / "data" / "blood.sqlite"))

    from engine.config import load_config
    app.config.update(
        ENGINE_CONFIG=load_config(path=os.environ.get('ENGINE_SETTINGS_FILE')),
        ORG_FACILITY_MAP=json.loads(os.environ.get('ORG_FACILITY_MAP', '{}')),
        SMS_SENDERS=json.loads(os.environ.get('SMS_SENDERS', '{}')),
        SMS_WEBHOOK_SECRET=os.environ.get('SMS_WEBHOOK_SECRET'),
        RESULTS_DIR=str(Path(__file__).resolve().parents[2] / 'results'),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    mappings = app.config['ORG_FACILITY_MAP']
    if not isinstance(mappings, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in mappings.items()):
        raise ValueError('ORG_FACILITY_MAP must map organization IDs to facility IDs')
    senders = app.config['SMS_SENDERS']
    if not isinstance(senders, dict) or any(
        not isinstance(value, dict) or any(not isinstance(value.get(key), str) or not value[key] for key in ('user_id', 'org_id', 'facility_id'))
        for value in senders.values()
    ):
        raise ValueError('SMS_SENDERS must map sender numbers to user_id, org_id and facility_id')
    app.config['ENGINE_CONFIG']['sharing_allowed'] = (app.config['ENGINE_CONFIG']['sharing_allowed'] and app.config['SETTINGS']['lending']['enabled'])

    from .storage import init_app
    init_app(app)

    @app.cli.command("expire-confirmations")
    def expire_confirmations():
        """Release expired reservations; run periodically from a scheduler."""
        from .workflow import expire
        click.echo(f"Expired {expire()} confirmation(s)")

    from .commands import register, register_ingest, register_prealerts
    register(app)
    register_ingest(app)
    register_prealerts(app)

    from .clerk_auth import init_clerk
    from .routes import api

    init_clerk(app)
    # Test/local configuration is applied after environment-derived auth defaults.
    if test_config and 'AUTH_DISABLED' in test_config:
        app.config['AUTH_DISABLED'] = test_config['AUTH_DISABLED']

    from werkzeug.exceptions import HTTPException
    @app.errorhandler(HTTPException)
    def http_error(error):
        from flask import jsonify
        return jsonify(error={'code': error.name.lower().replace(' ', '_'), 'message': error.description}), error.code

    from .workflow import APIError
    @app.errorhandler(APIError)
    def workflow_error(error):
        from flask import jsonify
        return jsonify(error={'code': f'http_{error.status}', 'message': error.message}), error.status

    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        from flask import jsonify
        app.logger.exception('Database operation failed')
        return jsonify(error={'code': 'database_unavailable', 'message': 'Database unavailable; use the phone process'}), 503

    app.register_blueprint(api, url_prefix="/api")
    from .sms import sms_api
    app.register_blueprint(sms_api, url_prefix='/api')
    if not app.testing:
        from .services import warm_engine
        with app.app_context():
            warm_engine()
    return app
