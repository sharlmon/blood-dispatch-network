import json

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from .clerk_auth import require_auth, require_hospital
from .storage import get_db
from . import workflow, access, services
from .idempotency import idempotent

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
    return jsonify(error={'code': f'http_{error.status}', 'message': error.message}), error.status


@api.get('/health')
def health():
    return jsonify(status='ok', country=current_app.config['SETTINGS']['country'])


@api.get('/ready')
def ready():
    db = get_db()
    db.execute('SELECT 1').fetchone()
    engine_loaded = services.engine_ready()
    expected = services.snapshot_day()
    loaded = db.execute('SELECT EXISTS(SELECT 1 FROM inventory WHERE substr(updated_at,1,10)=?)', (expected,)).fetchone()[0] == 1
    ok = loaded and engine_loaded and not services.fallback()['enabled']
    return jsonify(status='ok' if ok else 'not_ready', inventory_loaded=loaded, engine_data_loaded=engine_loaded), 200 if ok else 503


@api.post('/requests')
@require_hospital
@idempotent
def create_request():
    data = body()
    access.require_facility(workflow.required(data, 'facility_id'))
    return jsonify(workflow.create(data)), 201


@api.get('/requests')
@require_hospital
def list_requests():
    limit, offset = pagination()
    clauses, values = [], []
    if not access.is_operator():
        identifier = access.caller_facility()
        clauses.append('(facility_id=? OR supplier_id=?)')
        values.extend([identifier, identifier])
    for field in ('facility_id', 'status'):
        if field in request.args:
            clauses.append(f'{field}=?')
            values.append(request.args[field])
    for key, comparator in (('created_after', '>='), ('created_before', '<=')):
        if key in request.args:
            clauses.append(f'created_at{comparator}?')
            values.append(workflow.timestamp(request.args[key]).isoformat())
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    rows = get_db().execute('SELECT * FROM requests' + where + ' ORDER BY created_at DESC,id LIMIT ? OFFSET ?', (*values, limit, offset))
    return jsonify(items=[dict(row) for row in rows], limit=limit, offset=offset)


@api.get('/requests/<identifier>')
@require_hospital
def get_request(identifier):
    access.can_read(workflow.request(get_db(), identifier))
    return jsonify(workflow.detail(identifier))


@api.post('/requests/<identifier>/<action>')
@require_hospital
@idempotent
def request_action(identifier, action):
    return jsonify(workflow.transition(identifier, action, body()))


@api.get('/facilities')
@require_hospital
def facilities():
    limit, offset = pagination()
    clauses, values = [], []
    if 'kind' in request.args:
        if request.args['kind'] not in {'hospital', 'centre'}:
            raise workflow.APIError('kind must be hospital or centre')
        clauses.append('kind=?')
        values.append(request.args['kind'])
    if request.args.get('q'):
        clauses.append('(name LIKE ? OR id LIKE ?)')
        values.extend(['%' + request.args['q'] + '%'] * 2)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    rows = get_db().execute('SELECT * FROM facilities' + where + ' ORDER BY id LIMIT ? OFFSET ?', (*values, limit, offset))
    return jsonify(items=[facility_detail(row) for row in rows], limit=limit, offset=offset)


def facility_detail(row):
    item = dict(row)
    meta = get_db().execute('SELECT payload FROM facility_metadata WHERE facility_id=?', (row['id'],)).fetchone()
    if meta:
        item['details'] = json.loads(meta['payload'])
    return item


@api.get('/facilities/<identifier>')
@require_hospital
def facility(identifier):
    return jsonify(facility_detail(workflow.facility(get_db(), identifier)))


@api.get('/facilities/<identifier>/inventory')
@require_hospital
def inventory(identifier):
    db = get_db()
    workflow.facility(db, identifier)
    access.require_facility(identifier)
    rows = db.execute('SELECT *, MAX(0,on_hand-reserved-safety_stock) AS available FROM inventory WHERE facility_id=? ORDER BY blood_group,product', (identifier,))
    return jsonify(items=[dict(row) for row in rows])


@api.get('/audit')
@require_hospital
def audit():
    limit, offset = pagination()
    identifier = request.args.get('request_id')
    if identifier:
        access.can_read(workflow.request(get_db(), identifier))
    elif not access.is_operator():
        raise workflow.APIError('request_id is required for facility audit access', 403)
    where, values = (' WHERE request_id=?', [identifier]) if identifier else ('', [])
    if 'action' in request.args:
        where += (' AND ' if where else ' WHERE ') + 'action=?'
        values.append(request.args['action'])
    rows = get_db().execute('SELECT * FROM audit' + where + ' ORDER BY id LIMIT ? OFFSET ?', (*values, limit, offset))
    items = []
    for row in rows:
        item = dict(row)
        item['details'] = json.loads(item['details'])
        items.append(item)
    return jsonify(items=items, limit=limit, offset=offset)


@api.get("/me")
@require_auth
def me():
    return jsonify(g.auth.public())


@api.get('/requests/<identifier>/options')
@require_hospital
def options(identifier):
    row = workflow.request(get_db(), identifier)
    access.can_read(row)
    return jsonify(workflow.metadata(get_db(), identifier)['ranking'])


@api.post('/requests/<identifier>/options/refresh')
@require_hospital
@idempotent
def refresh_options(identifier):
    db = get_db()
    row = workflow.request(db, identifier)
    access.require_facility(row['facility_id'])
    if row['status'] != 'pending':
        raise workflow.APIError('Options can only be refreshed for pending requests', 409)
    services.ensure_available()
    payload = workflow.metadata(db, identifier)['payload']
    payload['requested_at'] = workflow.now().isoformat()
    ranked = services.ranking(payload)
    db.execute('UPDATE request_metadata SET payload=?,ranking=? WHERE request_id=?', (json.dumps(payload), json.dumps(ranked), identifier))
    workflow.log(db, identifier, 'options_refreshed', {})
    return jsonify(ranked)


@api.get('/status')
@require_auth
def status():
    state = services.fallback()
    oldest = get_db().execute('SELECT MIN(updated_at) FROM inventory').fetchone()[0]
    engine_ready = services.engine_ready()
    expected = services.snapshot_day()
    fresh = get_db().execute('SELECT EXISTS(SELECT 1 FROM inventory WHERE substr(updated_at,1,10)=?)', (expected,)).fetchone()[0] == 1
    operational = not state['enabled'] and engine_ready and fresh
    return jsonify(mode='normal' if operational else 'fallback', manual_fallback=state,
                   engine_data_loaded=engine_ready, oldest_inventory_snapshot=oldest,
                   phone_process_required=not operational)


@api.put('/fallback')
@require_hospital
@idempotent
def update_fallback():
    access.require_operator()
    data = body()
    if type(data.get('enabled')) is not bool:
        raise workflow.APIError('enabled must be a boolean')
    value = services.set_fallback(data['enabled'], workflow.required(data, 'reason'))
    # Operational changes have a separate history; request audit rows require a request FK.
    get_db().execute('INSERT INTO operational_audit(action,actor,payload,created_at) VALUES(?,?,?,?)',
                     ('fallback_changed', json.dumps(g.auth.public()), json.dumps(value), workflow.now().isoformat()))
    return jsonify(value)


@api.get('/config')
@require_auth
def config():
    settings = current_app.config['SETTINGS']
    return jsonify(country=settings['country'], timezone=settings['timezone'],
                   patient_groups=sorted(workflow.GROUPS) + ['unknown'], components=['RBC'],
                   confirmation_timeout_minutes=settings['arrival']['confirmation_timeout_minutes'],
                   sharing_allowed=current_app.config['ENGINE_CONFIG']['sharing_allowed'],
                   unknown_group_policy=settings['unknown_group_policy'],
                   demo_clock=settings.get('demo_clock'), human_approval_required=True)


@api.post('/prealerts/runs')
@require_hospital
@idempotent
def create_prealert():
    access.require_operator()
    data = body()
    as_of = workflow.timestamp(data['as_of']) if 'as_of' in data else workflow.now()
    return jsonify(services.save_prealert(as_of)), 201


@api.get('/prealerts/runs')
@require_hospital
def list_prealerts():
    access.require_operator()
    limit, offset = pagination()
    rows = get_db().execute('SELECT id,created_at FROM prealert_runs ORDER BY created_at DESC,id LIMIT ? OFFSET ?', (limit, offset))
    return jsonify(items=[dict(row) for row in rows], limit=limit, offset=offset)


@api.get('/prealerts/runs/<identifier>')
@require_hospital
def get_prealert(identifier):
    access.require_operator()
    row = get_db().execute('SELECT * FROM prealert_runs WHERE id=?', (identifier,)).fetchone()
    if not row:
        raise workflow.APIError('Pre-alert run not found', 404)
    return jsonify(id=row['id'], created_at=row['created_at'], result=json.loads(row['payload']))


@api.get('/results')
@require_hospital
def list_results():
    access.require_operator()
    return jsonify(items=[{'id': key} for key in sorted(services.result_files())])


@api.get('/results/<path:identifier>')
@require_hospital
def get_result(identifier):
    access.require_operator()
    path = services.result_files().get(identifier)
    if path is None:
        raise workflow.APIError('Result not found', 404)
    try:
        return jsonify(json.loads(path.read_text()))
    except (OSError, ValueError):
        raise workflow.APIError('Result is unreadable', 503)


@api.get('/operations/audit')
@require_hospital
def operational_audit():
    access.require_operator()
    limit, offset = pagination()
    rows = get_db().execute('SELECT * FROM operational_audit ORDER BY id DESC LIMIT ? OFFSET ?', (limit, offset))
    items = []
    for row in rows:
        item = dict(row)
        item['actor'] = json.loads(item['actor'])
        item['payload'] = json.loads(item['payload'])
        items.append(item)
    return jsonify(items=items, limit=limit, offset=offset)
