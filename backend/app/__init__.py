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
        APP_ENV=os.environ.get('APP_ENV', 'development'),
        IDEMPOTENCY_RETENTION_DAYS=int(os.environ.get('IDEMPOTENCY_RETENTION_DAYS', '30')),
        ENGINE_CONFIG=load_config(path=os.environ.get('ENGINE_SETTINGS_FILE')),
        ORG_FACILITY_MAP=json.loads(os.environ.get('ORG_FACILITY_MAP', '{}')),
        SMS_SENDERS=json.loads(os.environ.get('SMS_SENDERS', '{}')),
        SMS_FACILITY_CONTACTS=json.loads(os.environ.get('SMS_FACILITY_CONTACTS', '{}')),
        SMS_WEBHOOK_SECRET=os.environ.get('SMS_WEBHOOK_SECRET'),
        SMS_ENABLED=os.environ.get('SMS_ENABLED') == '1',
        SMS_ENVIRONMENT=os.environ.get('SMS_ENVIRONMENT', 'sandbox'),
        AFRICASTALKING_USERNAME=os.environ.get('AFRICASTALKING_USERNAME', ''),
        AFRICASTALKING_API_KEY=os.environ.get('AFRICASTALKING_API_KEY', ''),
        AFRICASTALKING_SANDBOX_API_KEY=os.environ.get('AFRICASTALKING_SANDBOX_API_KEY', ''),
        AFRICASTALKING_SENDER_ID=os.environ.get('AFRICASTALKING_SENDER_ID', ''),
        AFRICASTALKING_SANDBOX_SENDER_ID=os.environ.get('AFRICASTALKING_SANDBOX_SENDER_ID', ''),
        AFRICASTALKING_CALLBACK_TOKEN=os.environ.get('AFRICASTALKING_CALLBACK_TOKEN', ''),
        AFRICASTALKING_INBOUND_NUMBERS=json.loads(os.environ.get('AFRICASTALKING_INBOUND_NUMBERS', '[]')),
        RESULTS_DIR=os.environ.get('RESULTS_DIR', str(Path(__file__).resolve().parents[2] / 'results')),
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
    if app.config['IDEMPOTENCY_RETENTION_DAYS'] < 1:
        raise ValueError('IDEMPOTENCY_RETENTION_DAYS must be at least 1')
    from .sms_provider import validate_config
    validate_config(app.config)
    hour = app.config['SETTINGS'].get('prealert', {}).get('run_hour', 18)
    if type(hour) is not int or not 0 <= hour <= 23:
        raise ValueError('prealert.run_hour must be an integer from 0 to 23')
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

    from .deployment import production_errors
    if app.config['APP_ENV'] == 'production':
        errors = production_errors(app)
        if errors:
            raise ValueError('; '.join(errors))

    from .observability import init_logging
    init_logging(app)
    from .ops_commands import register as register_operations
    register_operations(app)
    from .validation import register as register_validation
    register_validation(app)

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
    from .docs import docs
    app.register_blueprint(docs, url_prefix='/api')
    if not app.testing:
        from .services import warm_engine
        with app.app_context():
            warm_engine()
    return app
