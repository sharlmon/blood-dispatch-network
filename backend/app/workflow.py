"""Transactional request lifecycle. The deterministic engine supplies suggestions."""
import json
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import current_app, g, has_request_context

from .storage import get_db, atomic

GROUPS = {'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'}
PRODUCTS = {'red_cells', 'whole_blood'}


class APIError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def now():
    frozen = current_app.config['SETTINGS'].get('demo_clock')
    value = datetime.fromisoformat(str(frozen).replace('Z', '+00:00')) if frozen else datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise APIError('demo_clock must include a timezone', 503)
    return value.astimezone(timezone.utc)


def timestamp(raw):
    if not isinstance(raw, str):
        raise APIError('Timestamp must be an ISO string with timezone')
    try:
        value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        raise APIError('Invalid ISO timestamp')
    if value.tzinfo is None:
        raise APIError('Timestamp must include a timezone')
    return value.astimezone(timezone.utc)


def required(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise APIError(f'{key} must be a nonempty string of at most 500 characters')
    return value.strip()


def facility(db, identifier):
    row = db.execute('SELECT * FROM facilities WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise APIError('Facility not found', 404)
    return row


def request(db, identifier):
    row = db.execute('SELECT * FROM requests WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise APIError('Request not found', 404)
    return row


def log(db, identifier, action, details):
    actor = getattr(g, 'auth', None) if has_request_context() else None
    event = {**details, 'actor': actor.public() if actor else {'user_id': 'system'}}
    db.execute('INSERT INTO audit(request_id,action,details,created_at) VALUES(?,?,?,?)',
               (identifier, action, json.dumps(event), now().isoformat()))
    from .sms_provider import queue_workflow_event
    queue_workflow_event(db, identifier, action, details)


def metadata(db, identifier):
    row = db.execute('SELECT * FROM request_metadata WHERE request_id=?', (identifier,)).fetchone()
    if row is None:
        raise APIError('Legacy request lacks engine metadata; cancel and recreate it', 409)
    return {key: json.loads(row[key]) if row[key] else None for key in ('payload', 'ranking', 'selected_option', 'attempted_sources')}


def detail(identifier):
    db = get_db()
    result = dict(request(db, identifier))
    meta = db.execute('SELECT * FROM request_metadata WHERE request_id=?', (identifier,)).fetchone()
    if meta:
        result['ranking'] = json.loads(meta['ranking'])
        result['request'] = json.loads(meta['payload'])
        result['selected_option'] = json.loads(meta['selected_option']) if meta['selected_option'] else None
    result['allocations'] = [dict(row) for row in db.execute('SELECT blood_group,product,units FROM allocations WHERE request_id=?', (identifier,))]
    return result


def normalize(data):
    # Accept the original scaffold's aliases, but store the engine's stable contract.
    allowed = {'facility_id', 'patient_group', 'blood_group', 'units_needed', 'units', 'component', 'product', 'requested_at', 'clinician_limit_h'}
    if set(data) - allowed:
        raise APIError('Unsupported request fields; do not submit patient identifiers')
    for canonical, alias in (('patient_group', 'blood_group'), ('units_needed', 'units')):
        if canonical in data and alias in data and data[canonical] != data[alias]:
            raise APIError(f'{canonical} and {alias} conflict')
    facility_id = required(data, 'facility_id')
    from engine.compat import normalise_group
    try:
        group = normalise_group(data.get('patient_group', data.get('blood_group')))
    except ValueError as exc:
        raise APIError(str(exc)) from exc
    units = data.get('units_needed', data.get('units'))
    if type(units) is not int or not 1 <= units <= 100:
        raise APIError('units_needed must be an integer between 1 and 100')
    if data.get('component', 'RBC') != 'RBC' or data.get('product', 'red_cells') != 'red_cells':
        raise APIError('This engine supports red-cell (RBC) requests only')
    at = timestamp(data['requested_at']) if 'requested_at' in data else now()
    if abs((at - now()).total_seconds()) > 300:
        raise APIError('requested_at must be within five minutes of the operational clock; set demo_clock for historical demos')
    limit = data.get('clinician_limit_h', current_app.config['ENGINE_CONFIG']['clinician_limit_h'])
    if type(limit) not in (int, float) or not math.isfinite(limit) or not 0 < limit <= 72:
        raise APIError('clinician_limit_h must be greater than 0 and at most 72')
    return dict(facility_id=facility_id, patient_group=group, units_needed=units,
                component='RBC', requested_at=at.isoformat(), clinician_limit_h=limit)


def create(data):
    from . import services
    payload = normalize(data)
    services.ensure_available()
    facility(get_db(), payload['facility_id'])
    ranked = services.ranking(payload)
    with atomic() as db:
        identifier, stamp = str(uuid4()), now().isoformat()
        db.execute('INSERT INTO requests(id,facility_id,blood_group,product,units,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                   (identifier, payload['facility_id'], payload['patient_group'], 'red_cells', payload['units_needed'], 'pending', stamp, stamp))
        db.execute('INSERT INTO request_metadata(request_id,payload,ranking) VALUES(?,?,?)', (identifier, json.dumps(payload), json.dumps(ranked)))
        log(db, identifier, 'created', payload)
    return detail(identifier)


def release(db, row):
    allocations = db.execute('SELECT * FROM allocations WHERE request_id=?', (row['id'],)).fetchall()
    if allocations:
        for allocation in allocations:
            db.execute('UPDATE inventory SET reserved=reserved-? WHERE facility_id=? AND blood_group=? AND product=?',
                       (allocation['units'], allocation['facility_id'], allocation['blood_group'], allocation['product']))
        db.execute('DELETE FROM allocations WHERE request_id=?', (row['id'],))
    elif row['supplier_id']:  # Existing first-slice requests reserved only the exact group.
        db.execute('UPDATE inventory SET reserved=reserved-? WHERE facility_id=? AND blood_group=? AND product=?',
                   (row['units'], row['supplier_id'], row['blood_group'], row['product']))


def select(db, row, supplier):
    from engine.compat import acceptable_unit_groups
    meta = metadata(db, row['id'])
    option = next((item for item in meta['ranking']['options'] if item['facility_id'] == supplier), None)
    if not option or supplier in meta['attempted_sources']:
        raise APIError('Select an unattempted supplier from the ranked options', 409)
    if supplier == row['facility_id'] or supplier.startswith('SAT-'):
        raise APIError('Invalid supplying facility', 409)
    facility(db, supplier)
    stock_day = meta['ranking']['request']['as_of_stock_date']
    target_day = (now().astimezone(ZoneInfo(current_app.config['SETTINGS']['timezone'])).date() - timedelta(days=1)).isoformat()
    if stock_day != target_day:
        raise APIError('Ranking snapshot is stale; refresh options or use the phone process', 409)
    needed = row['units']
    for group in acceptable_unit_groups(row['blood_group']):
        # Keep actual components separate. Engine RBC+WB counts never create RBC units.
        item = db.execute("SELECT * FROM inventory WHERE facility_id=? AND blood_group=? AND product='red_cells'", (supplier, group)).fetchone()
        if item is None or item['updated_at'][:10] != stock_day:
            continue
        cap = option['spare_by_group'].get(group, 0)
        count = min(needed, max(0, min(item['on_hand'] - item['safety_stock'], cap) - item['reserved']))
        if count:
            db.execute("UPDATE inventory SET reserved=reserved+? WHERE facility_id=? AND blood_group=? AND product='red_cells'", (count, supplier, group))
            db.execute("INSERT INTO allocations VALUES(?,?,?,'red_cells',?)", (row['id'], supplier, group, count))
            needed -= count
        if needed == 0:
            break
    if needed:
        raise APIError('Insufficient current RBC stock above safety reserves; partial or whole-blood fulfillment requires the phone process', 409)
    deadline = (now() + timedelta(minutes=current_app.config['SETTINGS']['arrival']['confirmation_timeout_minutes'])).isoformat()
    attempted = [*meta['attempted_sources'], supplier]
    db.execute('UPDATE request_metadata SET selected_option=?,attempted_sources=? WHERE request_id=?', (json.dumps(option), json.dumps(attempted), row['id']))
    db.execute("UPDATE requests SET status='awaiting_confirmation',supplier_id=?,attempt=attempt+1,deadline=? WHERE id=?", (supplier, deadline, row['id']))


def advance(db, identifier):
    """Continue the existing request after an unavailable supplier; audit every attempt."""
    from .services import fallback
    if fallback()['enabled']:
        return
    row = request(db, identifier)
    try:
        meta = metadata(db, identifier)
    except APIError:
        return  # Legacy first-slice records need explicit recreation.
    for option in meta['ranking']['options']:
        supplier = option['facility_id']
        if supplier in meta['attempted_sources']:
            continue
        db.execute('SAVEPOINT next_supplier')
        try:
            select(db, row, supplier)
        except APIError as exc:
            db.execute('ROLLBACK TO next_supplier')
            db.execute('RELEASE next_supplier')
            log(db, identifier, 'supplier_skipped', {'supplier_id': supplier, 'reason': exc.message})
            continue
        db.execute('RELEASE next_supplier')
        log(db, identifier, 'next_supplier_selected', {'supplier_id': supplier, 'attempt': row['attempt'] + 1})
        return
    log(db, identifier, 'sources_exhausted', {'phone_process_required': True})


def transition(identifier, action, data):
    from .access import require_facility
    from .services import ensure_available
    if action not in {'pick', 'confirm', 'reject', 'dispatch', 'cancel', 'receive'}:
        raise APIError('Unknown action', 404)
    with atomic() as db:
        row = request(db, identifier)
        status = row['status']
        if has_request_context():
            require_facility(row['supplier_id'] if action in {'confirm', 'reject', 'dispatch'} else row['facility_id'])
        if action in {'pick', 'confirm', 'dispatch'}:
            ensure_available()
        if action == 'pick':
            if status != 'pending':
                raise APIError('Only pending requests can select a supplier', 409)
            select(db, row, required(data, 'supplier_id'))
        elif action in {'confirm', 'reject', 'dispatch'}:
            expected = 'confirmed' if action == 'dispatch' else 'awaiting_confirmation'
            if status != expected:
                raise APIError(f'{action} requires status {expected}', 409)
            if type(data.get('attempt')) is not int or data['attempt'] != row['attempt']:
                raise APIError('A matching integer attempt is required', 409)
            if required(data, 'supplier_id') != row['supplier_id']:
                raise APIError('Supplier does not match current attempt', 409)
            if action != 'dispatch' and now() >= datetime.fromisoformat(row['deadline']):
                raise APIError('Confirmation deadline expired', 409)
            if action == 'confirm':
                if type(data.get('confirmed_units')) is not int or data['confirmed_units'] != row['units']:
                    raise APIError('confirmed_units must equal requested units')
                db.execute("UPDATE requests SET status='confirmed',deadline=NULL WHERE id=?", (identifier,))
            elif action == 'reject':
                required(data, 'reason')
                release(db, row)
                db.execute("UPDATE requests SET status='pending',supplier_id=NULL,deadline=NULL WHERE id=?", (identifier,))
            else:
                allocations = db.execute('SELECT * FROM allocations WHERE request_id=?', (identifier,)).fetchall()
                if not allocations:
                    raise APIError('No stock allocation exists', 409)
                for item in allocations:
                    db.execute('UPDATE inventory SET on_hand=on_hand-?,reserved=reserved-? WHERE facility_id=? AND blood_group=? AND product=?',
                               (item['units'], item['units'], item['facility_id'], item['blood_group'], item['product']))
                db.execute("UPDATE requests SET status='dispatched' WHERE id=?", (identifier,))
        elif action == 'cancel':
            required(data, 'reason')
            if status not in {'pending', 'awaiting_confirmation', 'confirmed'}:
                raise APIError('Request cannot be cancelled in its current status', 409)
            if row['supplier_id']:
                release(db, row)
            db.execute("UPDATE requests SET status='cancelled',deadline=NULL WHERE id=?", (identifier,))
        elif action == 'receive':
            if status != 'dispatched':
                raise APIError('Only dispatched requests can be received', 409)
            if type(data.get('received_units')) is not int or data['received_units'] != row['units']:
                raise APIError('received_units must equal dispatched units; discrepancies require the phone process')
            db.execute("UPDATE requests SET status='received' WHERE id=?", (identifier,))
        if action == 'reject':
            advance(db, identifier)
        db.execute('UPDATE requests SET updated_at=? WHERE id=?', (now().isoformat(), identifier))
        allowed = {'supplier_id', 'attempt', 'confirmed_units', 'received_units', 'reason'}
        log(db, identifier, action, {key: value for key, value in data.items() if key in allowed})
    return detail(identifier)


def expire():
    with atomic() as db:
        rows = db.execute("SELECT * FROM requests WHERE status='awaiting_confirmation' AND deadline<=?", (now().isoformat(),)).fetchall()
        for row in rows:
            release(db, row)
            db.execute("UPDATE requests SET status='pending',supplier_id=NULL,deadline=NULL,updated_at=? WHERE id=?", (now().isoformat(), row['id']))
            log(db, row['id'], 'confirmation_expired', {'attempt': row['attempt'], 'supplier_id': row['supplier_id']})
            advance(db, row['id'])
    return len(rows)
