import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from flask import current_app

from .storage import get_db

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


def required(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise APIError(f'{key} must be a nonempty string')
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
    db.execute('INSERT INTO audit(request_id,action,details,created_at) VALUES(?,?,?,?)',
               (identifier, action, json.dumps(details), now().isoformat()))


def create(data):
    facility_id = required(data, 'facility_id')
    group = required(data, 'blood_group')
    product = required(data, 'product')
    units = data.get('units')
    if group not in GROUPS:
        raise APIError('blood_group must be a known ABO/Rh group; unknown-group policy is not implemented yet')
    if product not in PRODUCTS:
        raise APIError('product must be red_cells or whole_blood')
    if type(units) is not int or not 1 <= units <= 100:
        raise APIError('units must be an integer between 1 and 100')
    db = get_db()
    with db:
        facility(db, facility_id)
        identifier, stamp = str(uuid4()), now().isoformat()
        db.execute('INSERT INTO requests(id,facility_id,blood_group,product,units,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                   (identifier, facility_id, group, product, units, 'pending', stamp, stamp))
        log(db, identifier, 'created', dict(facility_id=facility_id, blood_group=group, product=product, units=units))
    return dict(request(db, identifier))


def release(db, row):
    db.execute('UPDATE inventory SET reserved=reserved-? WHERE facility_id=? AND blood_group=? AND product=?',
               (row['units'], row['supplier_id'], row['blood_group'], row['product']))


def transition(identifier, action, data):
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        row = request(db, identifier)
        status = row['status']
        if action == 'pick':
            if status != 'pending':
                raise APIError('Only pending requests can select a supplier', 409)
            supplier = required(data, 'supplier_id')
            site = facility(db, supplier)
            if supplier == row['facility_id'] or site['kind'] != 'centre' or supplier.startswith('SAT-'):
                raise APIError('Initial workflow supports external centres only', 409)
            result = db.execute('UPDATE inventory SET reserved=reserved+? WHERE facility_id=? AND blood_group=? AND product=? AND on_hand-reserved-safety_stock>=?',
                                (row['units'], supplier, row['blood_group'], row['product'], row['units']))
            if result.rowcount != 1:
                raise APIError('Insufficient unreserved stock', 409)
            minutes = current_app.config['SETTINGS']['arrival']['confirmation_timeout_minutes']
            deadline = (now() + timedelta(minutes=minutes)).isoformat()
            db.execute("UPDATE requests SET status='awaiting_confirmation',supplier_id=?,attempt=attempt+1,deadline=? WHERE id=?", (supplier, deadline, identifier))
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
                db.execute('UPDATE inventory SET on_hand=on_hand-?,reserved=reserved-? WHERE facility_id=? AND blood_group=? AND product=?',
                           (row['units'], row['units'], row['supplier_id'], row['blood_group'], row['product']))
                db.execute("UPDATE requests SET status='dispatched' WHERE id=?", (identifier,))
        elif action == 'cancel':
            required(data, 'reason')
            if status not in {'pending', 'awaiting_confirmation', 'confirmed'}:
                raise APIError('Request cannot be cancelled in its current status', 409)
            if row['supplier_id']:
                release(db, row)
            db.execute("UPDATE requests SET status='cancelled',deadline=NULL WHERE id=?", (identifier,))
        else:
            raise APIError('Unknown action', 404)
        db.execute('UPDATE requests SET updated_at=? WHERE id=?', (now().isoformat(), identifier))
        log(db, identifier, action, data)
    return dict(request(db, identifier))


def expire():
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        rows = db.execute("SELECT * FROM requests WHERE status='awaiting_confirmation' AND deadline<=?", (now().isoformat(),)).fetchall()
        for row in rows:
            release(db, row)
            db.execute("UPDATE requests SET status='pending',supplier_id=NULL,deadline=NULL,updated_at=? WHERE id=?", (now().isoformat(), row['id']))
            log(db, row['id'], 'confirmation_expired', {'attempt': row['attempt']})
    return len(rows)
