"""Africa's Talking transport and transactional SMS outbox. Never retry uncertain sends."""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4

from flask import current_app, g

from .storage import atomic

PHONE = re.compile(r'\+[1-9]\d{6,14}')
EVENTS = {'created', 'pick', 'confirm', 'reject', 'dispatch', 'cancel', 'receive',
          'confirmation_expired', 'next_supplier_selected', 'sources_exhausted'}
DELIVERY = {'Success': 'delivered', 'Failed': 'delivery_failed', 'Rejected': 'delivery_failed',
            'Submitted': 'submitted', 'Buffered': 'buffered'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def validate_config(config):
    if config['SMS_ENVIRONMENT'] not in {'live', 'sandbox'}:
        raise ValueError('SMS_ENVIRONMENT must be live or sandbox')
    numbers = config['AFRICASTALKING_INBOUND_NUMBERS']
    if not isinstance(numbers, list) or any(not isinstance(n, str) or not n.strip() for n in numbers):
        raise ValueError('AFRICASTALKING_INBOUND_NUMBERS must be a list of service numbers')
    if any(not isinstance(n, str) or not PHONE.fullmatch(n) for n in config['SMS_SENDERS']):
        raise ValueError('SMS_SENDERS keys must be E.164 phone numbers')
    if config['SMS_ENABLED']:
        sandbox = config['SMS_ENVIRONMENT'] == 'sandbox'
        if not config['AFRICASTALKING_SANDBOX_API_KEY' if sandbox else 'AFRICASTALKING_API_KEY']:
            raise ValueError('Enabled SMS requires an API key for the selected environment')
        if not sandbox and (not config['AFRICASTALKING_USERNAME'] or config['AFRICASTALKING_USERNAME'] == 'sandbox'):
            raise ValueError('Live SMS requires a live application username')
    token = config['AFRICASTALKING_CALLBACK_TOKEN']
    if token and len(token) < 32:
        raise ValueError('AFRICASTALKING_CALLBACK_TOKEN must contain at least 32 characters')


def enqueue(db, key, recipient, body, request_id=None):
    if not current_app.config['SMS_ENABLED']:
        return
    if not PHONE.fullmatch(recipient):
        raise ValueError('SMS recipient must be E.164')
    timestamp = stamp()
    db.execute('INSERT OR IGNORE INTO sms_outbox(id,event_key,request_id,recipient,body,environment,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
               (str(uuid4()), key, request_id, recipient, body, current_app.config['SMS_ENVIRONMENT'], timestamp, timestamp))


def queue_workflow_event(db, identifier, action, details):
    if not current_app.config['SMS_ENABLED'] or action not in EVENTS:
        return
    row = db.execute('SELECT * FROM requests WHERE id=?', (identifier,)).fetchone()
    event_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    facilities = {row['facility_id'], row['supplier_id'], details.get('supplier_id')}
    # No patient details, blood group or clinical instructions in notifications.
    body = f"Blood Dispatch: {identifier}; {action}; status {row['status']}; attempt {row['attempt']}. Check app or call facility."
    for number, mapping in current_app.config['SMS_SENDERS'].items():
        if mapping['facility_id'] in facilities and number != getattr(g, 'sms_sender', None):
            enqueue(db, f'audit:{event_id}:{number}', number, body, identifier)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward API credentials to a redirected host.


def send_message(row):
    config = current_app.config
    sandbox = row['environment'] == 'sandbox'
    username = 'sandbox' if sandbox else config['AFRICASTALKING_USERNAME']
    key = config['AFRICASTALKING_SANDBOX_API_KEY' if sandbox else 'AFRICASTALKING_API_KEY']
    sender = config['AFRICASTALKING_SANDBOX_SENDER_ID' if sandbox else 'AFRICASTALKING_SENDER_ID']
    payload = {'username': username, 'to': row['recipient'], 'message': row['body'], 'bulkSMSMode': 1}
    if sender:
        payload['from'] = sender
    host = 'api.sandbox.africastalking.com' if sandbox else 'api.africastalking.com'
    req = Request(f'https://{host}/version1/messaging', data=urlencode(payload).encode(),
                  headers={'apiKey': key, 'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    try:
        with build_opener(NoRedirect()).open(req, timeout=20) as response:
            data = json.loads(response.read(65536))
        recipients = data['SMSMessageData']['Recipients']
        if len(recipients) != 1 or recipients[0]['number'] != row['recipient']:
            raise ValueError('Unexpected recipient response')
        result = recipients[0]
        code = int(result['statusCode'])
        provider_id = result.get('messageId')
        if code in {100, 101, 102}:
            if not isinstance(provider_id, str) or provider_id in {'', 'None'}:
                raise ValueError('Missing provider ID')
            return {'status': 'accepted', 'provider_id': provider_id, 'provider_status': str(code), 'cost': str(result.get('cost', ''))[:80]}
        # Explicit recipient rejection: safe to diagnose, but never auto retry.
        return {'status': 'failed', 'provider_status': str(code), 'error_code': f'provider_{code}'}
    except HTTPError as exc:
        # Server errors may follow acceptance; only 4xx is a definite rejection.
        return {'status': 'failed' if 400 <= exc.code < 500 else 'unknown', 'error_code': f'http_{exc.code}'}
    except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return {'status': 'unknown', 'error_code': 'transport_or_invalid_response'}


def apply_delivery(db, provider_id, status):
    target = DELIVERY[status]
    # Delayed/duplicate reports cannot regress a final outcome. Delivered wins.
    db.execute("UPDATE sms_outbox SET status=?,updated_at=? WHERE provider_id=? AND (status NOT IN ('delivered','delivery_failed') OR ?='delivered')",
               (target, stamp(), provider_id, target))


def drain(limit=20):
    if not current_app.config['SMS_ENABLED']:
        return {'disabled': True, 'processed': 0}
    processed = 0
    for _ in range(limit):
        with atomic() as db:
            # A crash after claiming may have happened after provider acceptance.
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
            db.execute("UPDATE sms_outbox SET status='unknown',error_code='worker_interrupted',updated_at=? WHERE status='sending' AND updated_at<?", (stamp(), cutoff))
            row = db.execute("SELECT * FROM sms_outbox WHERE status='queued' AND environment=? ORDER BY created_at,id LIMIT 1", (current_app.config['SMS_ENVIRONMENT'],)).fetchone()
            if row is None:
                break
            db.execute("UPDATE sms_outbox SET status='sending',updated_at=? WHERE id=?", (stamp(), row['id']))
        # Network happens after the claim commits, outside the workflow transaction.
        result = send_message(dict(row))
        with atomic() as db:
            fields = ','.join(f'{key}=?' for key in result)
            db.execute(f'UPDATE sms_outbox SET {fields},updated_at=? WHERE id=?', (*result.values(), stamp(), row['id']))
            if result.get('provider_id'):
                report = db.execute('SELECT status FROM sms_delivery_reports WHERE provider_id=?', (result['provider_id'],)).fetchone()
                if report:
                    apply_delivery(db, result['provider_id'], report['status'])
        processed += 1
    return {'processed': processed}
