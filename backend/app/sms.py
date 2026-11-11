"""Signed gateway and Africa's Talking callback adapters for scoped SMS commands."""
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone

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
    return process_message(data, secret)


def process_message(data, secret, provider=False):
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
            if saved['response'] == 'null':
                raise APIError('Cached SMS response expired; check request status', 409)
            return jsonify(json.loads(saved['response'])), saved['status']
        g.auth = AuthContext(user_id=mapping['user_id'], session_id=None,
                             org_id=mapping['org_id'], org_role='org:member')
        # Local demo bypass must not grant SMS callers operator access.
        g.sms_facility_id = mapping['facility_id']
        g.sms_sender = sender
        db.execute('SAVEPOINT sms_command')
        try:
            result, status = execute_command(db, text, mapping)
        except APIError as error:
            db.execute('ROLLBACK TO sms_command')
            db.execute('RELEASE sms_command')
            if (not provider and not error.message.startswith('Supported commands:')) or error.status >= 500:
                raise
            response = {'message_id': message_id, 'reply': HELP, 'error': error.status}
            db.execute('INSERT INTO idempotency(actor,key,fingerprint,response,status,created_at) VALUES(?,?,?,?,?,?)', (actor, message_id, fingerprint, json.dumps(response), 200, datetime.now(timezone.utc).isoformat()))
            if provider:
                from .sms_provider import enqueue
                enqueue(db, f'inbound:{actor}:{message_id}', sender, response['reply'])
            return jsonify(response), 200
        db.execute('RELEASE sms_command')
        response = {'message_id': message_id, 'request': result, 'reply': (f"{result['id']}: confirmed. Reply SENT when dispatched." if text.strip().upper() == 'YES' else request_reply(result))}
        db.execute('INSERT INTO idempotency(actor,key,fingerprint,response,status,created_at) VALUES(?,?,?,?,?,?)', (actor, message_id, fingerprint, json.dumps(response), status, datetime.now(timezone.utc).isoformat()))
        if provider:
            from .sms_provider import enqueue
            enqueue(db, f'inbound:{actor}:{message_id}', sender, response['reply'], result['id'])
        return jsonify(response), status


def callback_auth():
    # AT callbacks do not use our custom HMAC envelope. The configured callback
    # URL carries a separate random bearer token; protect/redact query logs.
    token = current_app.config['AFRICASTALKING_CALLBACK_TOKEN']
    if not token:
        raise APIError('Africa\'s Talking callbacks are not configured', 503)
    supplied = request.args.get('token', '')
    if not hmac.compare_digest(token.encode(), supplied.encode()):
        raise APIError('Invalid callback credentials', 401)
    return token


def callback_data():
    if request.mimetype == 'application/x-www-form-urlencoded':
        if any(len(request.form.getlist(k)) != 1 for k in request.form):
            raise APIError('Duplicate callback fields')
        return request.form.to_dict()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError('Callback requires form fields or a JSON object')
    return data


@sms_api.post('/sms/africastalking/inbound')
def africastalking_inbound():
    token = callback_auth()
    if not current_app.config['SMS_ENABLED']:
        raise APIError('SMS sending is disabled', 503)
    data = callback_data()
    destination = workflow.required(data, 'to')
    if destination not in current_app.config['AFRICASTALKING_INBOUND_NUMBERS']:
        raise APIError('SMS service number is not registered', 403)
    message = {'from': workflow.required(data, 'from'), 'message_id': workflow.required(data, 'id'),
               'text': workflow.required(data, 'text')}
    # Return 200 on valid provider retries, including REQUEST (normally 201).
    response, _ = process_message(message, current_app.config.get('SMS_WEBHOOK_SECRET') or token, provider=True)
    return response, 200


@sms_api.post('/sms/africastalking/delivery')
def africastalking_delivery():
    callback_auth()
    data = callback_data()
    identifier = workflow.required(data, 'id')
    status = workflow.required(data, 'status')
    from .sms_provider import DELIVERY, apply_delivery, stamp
    if status not in DELIVERY:
        raise APIError('Unsupported delivery status')
    with atomic() as db:
        previous = db.execute('SELECT status FROM sms_delivery_reports WHERE provider_id=?', (identifier,)).fetchone()
        # Keep reports arriving before the outbound HTTP response, too.
        if previous is None:
            db.execute('INSERT INTO sms_delivery_reports VALUES(?,?,?)', (identifier, status, stamp()))
        elif previous['status'] not in {'Success', 'Failed', 'Rejected'} or status == 'Success':
            db.execute('UPDATE sms_delivery_reports SET status=?,updated_at=? WHERE provider_id=?', (status, stamp(), identifier))
        apply_delivery(db, identifier, status)
    return jsonify(received=True), 200


HELP = 'HELP: REQUEST O+ 1; 1/2/3, STATUS, CANCEL; supplier: YES, NO, SENT.'


def arrival(option):
    eta = option['eta']
    return f"{eta['p50']:.1f}h ({eta['p10']:.1f}-{eta['p90']:.1f}h)"


def request_reply(result):
    ranking = result.get('ranking', {})
    option = result.get('selected_option')
    if result['status'] == 'confirmed' and option:
        return f"{option['name']} confirmed. Most likely {arrival(option)}."
    if result['status'] == 'awaiting_confirmation' and option:
        return f"Asking {option['name']} ({option['eta']['p50']:.1f}h)."
    if result['status'] != 'pending':
        return f"{result['id']}: {result['status']}."
    lines = []
    advice = ranking.get('advice')
    if advice and advice != 'no_full_source':
        limit = result.get('request', {}).get('clinician_limit_h', 6)
        lines.append(f'Wait may pass {limit:g}h: consider emergency group O or patient transfer.')
    if advice == 'no_full_source' or (ranking.get('options') and all('partial' in item.get('flags', []) for item in ranking['options'])):
        lines.append('No single site has enough')
    lines.append(f"{result['id']} {result['blood_group']} x{result['units']} (yesterday's count, unconfirmed)")
    options = ranking.get('options', [])[:3]
    lines.extend(f"{i} {item['name']} {arrival(item)}" for i, item in enumerate(options, 1))
    baseline = ranking.get('baseline', {})
    if baseline.get('quote_hours') is not None:
        lines.append(f"Today's way: {baseline['name']} ~{baseline['quote_hours']:.1f}h")
    if options:
        lines.append('Reply ' + ('1, 2 or 3' if len(options) == 3 else ' or '.join(str(i) for i in range(1, len(options) + 1))) + ' to ask that site')
    else:
        lines.append('Call your facility for the phone process.')
    return '\n'.join(lines)


def latest_request(db, mapping, supplier=False, dispatch=False):
    field = 'supplier_id' if supplier else 'facility_id'
    states = "('confirmed')" if dispatch else ("('awaiting_confirmation')" if supplier else "('pending','awaiting_confirmation','confirmed','dispatched')")
    row = db.execute(f"SELECT * FROM requests WHERE {field}=? AND status IN {states} ORDER BY created_at DESC, rowid DESC LIMIT 1", (mapping['facility_id'],)).fetchone()
    if row is None:
        raise APIError('No matching open request', 409)
    return row


def execute_command(db, text, mapping):
    text = text.strip().replace('−', '-')
    text = re.sub(r'\b(AB|A|B|O)\s*(POS(?:ITIVE)?|NEG(?:ATIVE)?)\b', lambda m: m[1].upper() + ('+' if m[2].upper().startswith('POS') else '-'), text, flags=re.IGNORECASE)
    parts = text.split()
    command = parts[0].upper() if parts else ''
    if len(parts) == 1 and command in {'1', '2', '3', 'STATUS', 'CANCEL', 'YES', 'NO', 'SENT'}:
        supplier = command in {'YES', 'NO', 'SENT'}
        row = latest_request(db, mapping, supplier, command == 'SENT')
        identifier = row['id']
        if command == 'STATUS':
            access.can_read(row)
            return workflow.detail(identifier), 200
        if command in {'1', '2', '3'}:
            options = workflow.metadata(db, identifier)['ranking']['options'][:3]
            index = int(command) - 1
            if index >= len(options):
                raise APIError('Option unavailable')
            return workflow.transition(identifier, 'pick', {'supplier_id': options[index]['facility_id']}), 200
        if command == 'CANCEL':
            return workflow.transition(identifier, 'cancel', {'reason': 'Cancelled by SMS requester'}), 200
        action = {'YES': 'confirm', 'NO': 'reject', 'SENT': 'dispatch'}[command]
        return workflow.transition(identifier, action, {'supplier_id': mapping['facility_id'], 'attempt': row['attempt'], 'confirmed_units': row['units'], 'reason': 'Not on shelf'}), 200
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
    elif command == 'CANCEL' and len(parts) == 2:
        result, status = workflow.transition(parts[1], 'cancel', {'reason': 'Cancelled by SMS requester'}), 200
    elif command == 'DISPATCH' and len(parts) == 3:
        try:
            attempt = int(parts[2])
        except ValueError:
            raise APIError('attempt must be an integer')
        result, status = workflow.transition(parts[1], 'dispatch', {'supplier_id': mapping['facility_id'], 'attempt': attempt}), 200
    else:
        raise APIError('Supported commands: REQUEST, STATUS, PICK, CONFIRM, REJECT, DISPATCH')
    return result, status
