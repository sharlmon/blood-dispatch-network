"""Request diagnostics without tokens, payloads, phone numbers or query strings."""
import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from flask import g, request


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(),
                           'level': record.levelname, 'logger': record.name, 'message': record.getMessage()})


def init_logging(app):
    if app.config['APP_ENV'] == 'production':
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        app.logger.handlers = [handler]
        app.logger.setLevel(logging.INFO)
        app.logger.propagate = False

    @app.before_request
    def start_request():
        g.request_id = str(uuid4())
        g.started_at = time.monotonic()

    @app.after_request
    def finish_request(response):
        response.headers['X-Request-ID'] = g.request_id
        app.logger.info(json.dumps({'event': 'http_request', 'request_id': g.request_id,
                                    'method': request.method,
                                    'route': request.url_rule.rule if request.url_rule else 'unmatched',
                                    'status': response.status_code,
                                    'duration_ms': round((time.monotonic() - g.started_at) * 1000, 2)}))
        return response
