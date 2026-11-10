"""Persist response and mutation together; retries never repeat stock changes."""
import hashlib
import json
from functools import wraps

from flask import current_app, g, jsonify, make_response, request

from .storage import atomic
from .workflow import APIError


def idempotent(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        key = request.headers.get('Idempotency-Key')
        if not key or not 1 <= len(key) <= 128 or not key.isascii():
            raise APIError('Idempotency-Key header (1–128 ASCII characters) is required')
        actor = json.dumps([g.auth.user_id, g.auth.org_id, g.auth.org_role, current_app.config['ORG_FACILITY_MAP'].get(g.auth.org_id), bool(current_app.config.get('AUTH_DISABLED'))])
        fingerprint = hashlib.sha256(request.method.encode() + request.path.encode() + request.get_data()).hexdigest()
        with atomic() as db:
            saved = db.execute('SELECT * FROM idempotency WHERE actor=? AND key=?', (actor, key)).fetchone()
            if saved:
                if saved['fingerprint'] != fingerprint:
                    raise APIError('Idempotency key was used for a different request', 409)
                return jsonify(json.loads(saved['response'])), saved['status']
            response = make_response(fn(*args, **kwargs))
            if response.status_code < 400:
                db.execute('INSERT INTO idempotency VALUES(?,?,?,?,?)',
                           (actor, key, fingerprint, json.dumps(response.get_json()), response.status_code))
            return response
    return wrapped
