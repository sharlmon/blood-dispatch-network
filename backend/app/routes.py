import json

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from .storage import get_db
from . import workflow

api = Blueprint('api', __name__)


def body():
    try:
        data = request.get_json()
    except (BadRequest, UnsupportedMediaType):
        raise workflow.APIError('Request body must be valid JSON', 400)
    if not isinstance(data, dict):
        raise workflow.APIError('Request body must be a JSON object')
    return data


def pagination():
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
    except ValueError:
        raise workflow.APIError('limit and offset must be integers')
    if not 1 <= limit <= 200 or offset < 0:
        raise workflow.APIError('limit must be 1–200 and offset must be nonnegative')
    return limit, offset


@api.errorhandler(workflow.APIError)
def api_error(error):
    return jsonify(error={'message': error.message}), error.status


@api.get('/health')
def health():
    return jsonify(status='ok', country=current_app.config['SETTINGS']['country'])


@api.get('/ready')
def ready():
    get_db().execute('SELECT 1').fetchone()
    return jsonify(status='ok', inventory_loaded=get_db().execute('SELECT EXISTS(SELECT 1 FROM inventory)').fetchone()[0] == 1)


@api.post('/requests')
def create_request():
    return jsonify(workflow.create(body())), 201


@api.get('/requests')
def list_requests():
    limit, offset = pagination()
    clauses, values = [], []
    for field in ('facility_id', 'status'):
        if field in request.args:
            clauses.append(f'{field}=?')
            values.append(request.args[field])
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    rows = get_db().execute('SELECT * FROM requests' + where + ' ORDER BY created_at DESC,id LIMIT ? OFFSET ?', (*values, limit, offset))
    return jsonify(items=[dict(row) for row in rows], limit=limit, offset=offset)


@api.get('/requests/<identifier>')
def get_request(identifier):
    return jsonify(dict(workflow.request(get_db(), identifier)))


@api.post('/requests/<identifier>/<action>')
def request_action(identifier, action):
    return jsonify(workflow.transition(identifier, action, body()))


@api.get('/facilities')
def facilities():
    limit, offset = pagination()
    rows = get_db().execute('SELECT * FROM facilities ORDER BY id LIMIT ? OFFSET ?', (limit, offset))
    return jsonify(items=[dict(row) for row in rows], limit=limit, offset=offset)


@api.get('/facilities/<identifier>')
def facility(identifier):
    return jsonify(dict(workflow.facility(get_db(), identifier)))


@api.get('/facilities/<identifier>/inventory')
def inventory(identifier):
    db = get_db()
    workflow.facility(db, identifier)
    rows = db.execute('SELECT *, MAX(0,on_hand-reserved-safety_stock) AS available FROM inventory WHERE facility_id=? ORDER BY blood_group,product', (identifier,))
    return jsonify(items=[dict(row) for row in rows])


@api.get('/audit')
def audit():
    limit, offset = pagination()
    identifier = request.args.get('request_id')
    where, values = (' WHERE request_id=?', [identifier]) if identifier else ('', [])
    rows = get_db().execute('SELECT * FROM audit' + where + ' ORDER BY id LIMIT ? OFFSET ?', (*values, limit, offset))
    items = []
    for row in rows:
        item = dict(row)
        item['details'] = json.loads(item['details'])
        items.append(item)
    return jsonify(items=items, limit=limit, offset=offset)
