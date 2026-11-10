"""Provider-neutral signed inbound SMS envelope; no outbound provider is assumed."""
import hashlib
import hmac
import json
import re
import time

from flask import Blueprint, current_app, g, jsonify, request

from .clerk_auth import AuthContext
from .storage import atomic
from .workflow import APIError
from . import workflow, access

sms_api = Blueprint('sms', __name__)


@sms_api.post('/sms')
def inbound():
    secret = current_app.config.get('SMS_WEBHOOK_SECRET')
    if not secret:
        raise APIError('SMS gateway is not configured', 503)
    raw = request.get_data()
    stamp = request.headers.get('X-SMS-Timestamp', '')
    signature = request.headers.get('X-SMS-Signature', '')
    try:
        timestamp = int(stamp)
    except ValueError:
        raise APIError('Invalid webhook timestamp', 401)
    expected = hmac.new(secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    if abs(time.time() - timestamp) > 300 or not hmac.compare_digest(expected, signature):
        raise APIError('Invalid webhook signature or expired timestamp', 401)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError('Webhook body must be a JSON object')
    sender = workflow.required(data, 'from')
    mapping = current_app.config['SMS_SENDERS'].get(sender)
    if not mapping or not re.fullmatch(r'\+[1-9]\d{6,14}', sender):
        raise APIError('SMS sender is not registered', 403)
    message_id = workflow.required(data, 'message_id')
    text = workflow.required(data, 'text')
    # Never log sender phone numbers, raw SMS text, or gateway payloads.
    actor = 'sms:' + hmac.new(secret.encode(), json.dumps([sender, mapping['user_id'], mapping['org_id'], mapping['facility_id']]).encode(), hashlib.sha256).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    with atomic() as db:
        saved = db.execute('SELECT * FROM idempotency WHERE actor=? AND key=?', (actor, message_id)).fetchone()
        if saved:
            if saved['fingerprint'] != fingerprint:
                raise APIError('Gateway message_id reused for a different message', 409)
            return jsonify(json.loads(saved['response'])), saved['status']
        g.auth = AuthContext(user_id=mapping['user_id'], session_id=None,
                             org_id=mapping['org_id'], org_role='org:member')
        # Local demo bypass must not grant SMS callers operator access.
        g.sms_facility_id = mapping['facility_id']
        parts = text.split()
        command = parts[0].upper()
        if command == 'REQUEST' and len(parts) == 3:
            try:
                units = int(parts[2])
            except ValueError:
                raise APIError('REQUEST format: REQUEST <blood-group|unknown> <units>')
            result = workflow.create({'facility_id': mapping['facility_id'], 'patient_group': parts[1], 'units_needed': units, 'component': 'RBC'})
            status = 201
        elif command == 'STATUS' and len(parts) == 2:
            row = workflow.request(db, parts[1])
            access.can_read(row)
            result, status = workflow.detail(parts[1]), 200
        elif command == 'PICK' and len(parts) == 3:
            result, status = workflow.transition(parts[1], 'pick', {'supplier_id': parts[2]}), 200
        elif command in {'CONFIRM', 'REJECT'} and len(parts) >= 4:
            try:
                payload = {'supplier_id': mapping['facility_id'], 'attempt': int(parts[2])}
                if command == 'CONFIRM' and len(parts) == 4:
                    payload['confirmed_units'] = int(parts[3])
                elif command == 'REJECT':
                    payload['reason'] = ' '.join(parts[3:])
                else:
                    raise ValueError()
            except ValueError:
                raise APIError('Use CONFIRM <request-id> <attempt> <units>, REJECT <request-id> <attempt> <reason>, or DISPATCH <request-id> <attempt>')
            result, status = workflow.transition(parts[1], command.lower(), payload), 200
        elif command == 'DISPATCH' and len(parts) == 3:
            try:
                attempt = int(parts[2])
            except ValueError:
                raise APIError('attempt must be an integer')
            result, status = workflow.transition(parts[1], 'dispatch', {'supplier_id': mapping['facility_id'], 'attempt': attempt}), 200
        else:
            raise APIError('Supported commands: REQUEST, STATUS, PICK, CONFIRM, REJECT, DISPATCH')
        response = {'message_id': message_id, 'request': result, 'reply': f"Request {result['id']}: {result['status']}. A trained lab worker must crossmatch and release every unit."}
        db.execute('INSERT INTO idempotency VALUES(?,?,?,?,?)', (actor, message_id, fingerprint, json.dumps(response), status))
        return jsonify(response), status
