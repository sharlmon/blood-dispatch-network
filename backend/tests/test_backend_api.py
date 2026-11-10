"""Workflow API integration, access boundaries, retry safety and engine adapters."""
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace

import pytest

from app.clerk_auth import AuthContext
from app.storage import get_db
from test_workflow import app, client, create, pick  # shared real-engine fixture


def test_retry_creation_and_conflicting_key(client):
    payload = {'facility_id': 'HSP-R', 'patient_group': 'A+', 'units_needed': 3}
    headers = {'Idempotency-Key': 'same'}
    first = client.post('/api/requests', json=payload, headers=headers)
    second = client.post('/api/requests', json=payload, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json == second.json
    assert len(client.get('/api/requests').json['items']) == 1
    assert client.post('/api/requests', json={**payload, 'units_needed': 2}, headers=headers).status_code == 409
    assert client.post('/api/requests', json=payload, headers={'Idempotency-Key': ''}).status_code == 400


def test_concurrent_create_retry(app):
    def submit(_):
        with app.test_client() as client:
            return client.post('/api/requests', json={'facility_id': 'HSP-R', 'patient_group': 'A+', 'units_needed': 3}, headers={'Idempotency-Key': 'parallel'}).json
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results[0] == results[1]
    assert len(app.test_client().get('/api/requests').json['items']) == 1


def test_dispatch_retry_and_receipt(client):
    identifier = create(client).json['id']
    pick(client, identifier)
    payload = {'supplier_id': 'RBTC-A', 'attempt': 1, 'confirmed_units': 3}
    client.post(f'/api/requests/{identifier}/confirm', json=payload)
    headers = {'Idempotency-Key': 'dispatch'}
    first = client.post(f'/api/requests/{identifier}/dispatch', json=payload, headers=headers)
    second = client.post(f'/api/requests/{identifier}/dispatch', json=payload, headers=headers)
    assert first.json == second.json
    assert client.get('/api/facilities/RBTC-A/inventory').json['items'][0]['on_hand'] == 2
    assert client.post(f'/api/requests/{identifier}/receive', json={'received_units': 2}).status_code == 400
    assert client.post(f'/api/requests/{identifier}/receive', json={'received_units': 3}).json['status'] == 'received'


def configure_identity(app):
    app.config['AUTH_DISABLED'] = False
    app.config['ORG_FACILITY_MAP'] = {'org_requester': 'HSP-R', 'org_supplier': 'RBTC-A', 'org_other': 'HSP-B'}
    identities = {name: AuthContext(user_id=name, session_id='s', org_id='org_' + name, org_role='org:member')
                  for name in ('requester', 'supplier', 'other')}
    identities['operator'] = AuthContext(user_id='operator', session_id='s', org_id='network', org_role='org:network_admin')
    app.extensions['clerk_verifier'] = SimpleNamespace(verify=lambda token: identities[token])


def test_facility_authorization_and_audit_actor(app, client):
    configure_identity(app)
    requester = {'Authorization': 'Bearer requester'}
    supplier = {'Authorization': 'Bearer supplier'}
    other = {'Authorization': 'Bearer other'}
    payload = {'facility_id': 'HSP-R', 'patient_group': 'A+', 'units_needed': 3}
    assert client.post('/api/requests', json=payload).status_code == 401
    assert client.post('/api/requests', json=payload, headers=other).status_code == 403
    identifier = client.post('/api/requests', json=payload, headers=requester).json['id']
    assert client.get(f'/api/requests/{identifier}', headers=other).status_code == 403
    assert client.get('/api/requests', headers=other).json['items'] == []
    assert client.get('/api/facilities/RBTC-A/inventory', headers=requester).status_code == 403
    assert client.post(f'/api/requests/{identifier}/pick', json={'supplier_id': 'RBTC-A'}, headers=supplier).status_code == 403
    assert client.post(f'/api/requests/{identifier}/pick', json={'supplier_id': 'RBTC-A'}, headers=requester).status_code == 200
    confirm = {'supplier_id': 'RBTC-A', 'attempt': 1, 'confirmed_units': 3}
    assert client.post(f'/api/requests/{identifier}/confirm', json=confirm, headers=requester).status_code == 403
    assert client.post(f'/api/requests/{identifier}/confirm', json=confirm, headers=supplier).status_code == 200
    assert client.post(f'/api/requests/{identifier}/cancel', json={'reason': 'Stop'}, headers=supplier).status_code == 403
    assert client.get('/api/audit', headers=requester).status_code == 403
    events = client.get('/api/audit', query_string={'request_id': identifier}, headers=requester).json['items']
    assert events[-1]['details']['actor']['user_id'] == 'supplier'
    assert client.put('/api/fallback', json={'enabled': True, 'reason': 'Maintenance'}, headers=requester).status_code == 403
    assert client.get('/api/results', headers=requester).status_code == 403


def test_auth_fails_closed(app, client):
    app.config['AUTH_DISABLED'] = False
    app.extensions['clerk_verifier'] = None
    assert client.get('/api/requests').status_code == 503
    assert client.get('/api/health').status_code == 200


def add_second_supplier(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO facilities VALUES('RBTC-B','Backup centre','centre')")
        db.execute("INSERT INTO inventory VALUES('RBTC-B','A+','red_cells',5,0,0,'2026-03-09T23:59:59+03:00')")
        db.commit()


def test_expiry_advances_and_stale_attempt_cannot_confirm(app, client):
    add_second_supplier(app)
    identifier = create(client).json['id']
    pick(client, identifier)
    app.config['SETTINGS']['demo_clock'] = '2026-03-10T01:11:00+03:00'
    result = app.test_cli_runner().invoke(args=['expire-confirmations'])
    assert result.exit_code == 0
    row = client.get(f'/api/requests/{identifier}').json
    assert (row['supplier_id'], row['attempt'], row['status']) == ('RBTC-B', 2, 'awaiting_confirmation')
    assert client.get('/api/facilities/RBTC-A/inventory').json['items'][0]['reserved'] == 0
    assert client.post(f'/api/requests/{identifier}/confirm', json={'supplier_id': 'RBTC-A', 'attempt': 1, 'confirmed_units': 3}).status_code == 409


def test_rejection_advances(app, client):
    add_second_supplier(app)
    identifier = create(client).json['id']
    pick(client, identifier)
    result = client.post(f'/api/requests/{identifier}/reject', json={'supplier_id': 'RBTC-A', 'attempt': 1, 'reason': 'Unavailable'})
    assert result.json['supplier_id'] == 'RBTC-B'


def test_compatible_groups_have_separate_allocations(app, client):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO inventory VALUES('RBTC-A','O+','red_cells',3,0,0,'2026-03-09T23:59:59+03:00')")
        db.commit()
    identifier = create(client, units=6).json['id']
    response = pick(client, identifier)
    assert response.status_code == 200
    assert {row['blood_group']: row['units'] for row in response.json['allocations']} == {'A+': 4, 'O+': 2}
    client.post(f'/api/requests/{identifier}/cancel', json={'reason': 'Cancelled'})
    assert all(item['reserved'] == 0 for item in client.get('/api/facilities/RBTC-A/inventory').json['items'])


def test_unknown_group_never_allocates_a_group_stock(client):
    identifier = create(client, blood_group='unknown').json['id']
    response = pick(client, identifier)
    assert response.status_code == 409  # No actual group O inventory imported.
    assert client.get('/api/facilities/RBTC-A/inventory').json['items'][0]['reserved'] == 0


def test_stale_snapshot_and_refresh(app, client):
    identifier = create(client).json['id']
    assert client.get(f'/api/requests/{identifier}/options').json['options']
    assert client.post(f'/api/requests/{identifier}/options/refresh', json={}).status_code == 200
    app.config['SETTINGS']['demo_clock'] = '2026-03-11T01:00:00+03:00'
    assert pick(client, identifier).status_code == 409


def test_fallback_blocks_new_actions_but_allows_cancel(client):
    identifier = create(client).json['id']
    assert client.put('/api/fallback', json={'enabled': True, 'reason': 'Planned maintenance'}).status_code == 200
    assert client.get('/api/status').json['mode'] == 'fallback'
    assert create(client).status_code == 503
    assert pick(client, identifier).status_code == 503
    assert client.post(f'/api/requests/{identifier}/cancel', json={'reason': 'Use phone'}).status_code == 200
    assert client.get('/api/operations/audit').json['items'][0]['action'] == 'fallback_changed'
    assert client.put('/api/fallback', json={'enabled': False, 'reason': 'Restored'}).status_code == 200


def test_missing_engine_is_service_unavailable(app, client, monkeypatch):
    app.config.pop('RANKING_PROVIDER')
    monkeypatch.delenv('DATA_DIR', raising=False)
    monkeypatch.delenv('ENGINE_DB_PATH', raising=False)
    assert create(client).status_code == 503
    assert client.get('/api/requests').json['items'] == []


def test_prealerts_use_existing_service(app, client):
    from engine.prealert import generate_prealerts
    app.config['PREALERT_PROVIDER'] = lambda as_of: generate_prealerts(
        {(date(2026, 3, 9), 'HSP-R', 'RBC', 'O+'): 0}, {'HSP-R': {}}, as_of=as_of)
    response = client.post('/api/prealerts/runs', json={})
    assert response.status_code == 201
    assert response.json['result']['alerts'][0]['facility_id'] == 'HSP-R'
    identifier = response.json['id']
    assert client.get(f'/api/prealerts/runs/{identifier}').json['result'] == response.json['result']
    assert len(client.get('/api/prealerts/runs').json['items']) == 1


def test_result_allowlist_and_framework_errors(app, client, tmp_path):
    app.config['RESULTS_DIR'] = str(tmp_path)
    (tmp_path / 'summary.json').write_text('{"metric":2}')
    (tmp_path / 'arrival_model.json').write_text('{"secret":"samples"}')
    assert client.get('/api/results').json['items'] == [{'id': 'summary'}]
    assert client.get('/api/results/summary').json == {'metric': 2}
    assert client.get('/api/results/arrival_model').status_code == 404
    assert client.get('/api/does-not-exist').json['error']['code'] == 'not_found'
    assert client.post('/api/health', json={}).json['error']['code'] == 'method_not_allowed'


def sms(client, app, payload, signature=None, timestamp=None):
    raw = json.dumps(payload).encode()
    stamp = str(timestamp or int(time.time()))
    sig = signature or hmac.new(app.config['SMS_WEBHOOK_SECRET'].encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    return client.post('/api/sms', data=raw, content_type='application/json', headers={'X-SMS-Timestamp': stamp, 'X-SMS-Signature': sig})


def test_sms_signature_deduplication_and_sender_scope(app, client):
    app.config['SMS_WEBHOOK_SECRET'] = 'test-secret'
    app.config['SMS_SENDERS'] = {'+254700000001': {'user_id': 'sms_user', 'org_id': 'org_requester', 'facility_id': 'HSP-R'}}
    payload = {'message_id': 'm1', 'from': '+254700000001', 'text': 'REQUEST A+ 3'}
    assert sms(client, app, payload, signature='wrong').status_code == 401
    assert sms(client, app, payload, timestamp=int(time.time()) - 600).status_code == 401
    first = sms(client, app, payload)
    assert first.status_code == 201
    assert sms(client, app, payload).json == first.json
    assert sms(client, app, {**payload, 'text': 'REQUEST A+ 2'}).status_code == 409
    identifier = first.json['request']['id']
    assert sms(client, app, {**payload, 'message_id': 'm2', 'text': f'PICK {identifier} RBTC-A'}).status_code == 200
    assert sms(client, app, {**payload, 'message_id': 'm3', 'text': f'CONFIRM {identifier} 1 3'}).status_code == 403
    events = client.get('/api/audit', query_string={'request_id': identifier}).json['items']
    assert '+254700000001' not in json.dumps(events)


def test_sms_not_configured(client):
    assert client.post('/api/sms', json={}).status_code == 503


def test_ingest_does_not_overwrite_consumption(app, monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    result = app.test_cli_runner().invoke(args=['ingest-data'])
    assert result.exit_code != 0
    assert 'refusing to reset consumed stock' in result.output


def test_csv_ingestion_through_rank_and_dispatch(tmp_path, monkeypatch):
    import pandas as pd
    from app import create_app, load_settings
    from engine.load import REQUEST_COLUMNS
    from test_workflow import RetryClient

    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('ENGINE_DB_PATH', str(tmp_path / 'engine.sqlite'))
    pd.DataFrame([
        ('HSP-R', 'Synthetic requester', 'county_hospital', 'RBTC-A', True, '4G'),
        ('RBTC-A', 'Synthetic centre', 'regional_blood_centre', None, True, '4G'),
    ], columns=['facility_id', 'name', 'facility_type', 'supply_centre_id', 'has_blood_fridge_backup_power', 'connectivity']).to_csv(tmp_path / 'facilities.csv', index=False)
    pd.DataFrame([('RBTC-A', 'HSP-R', 10, 0.5)], columns=['from_facility_id', 'to_facility_id', 'road_km', 'typical_travel_hours']).to_csv(tmp_path / 'routes.csv', index=False)
    pd.DataFrame([(day, facility, 'RBC', 'A+', units)
                  for day in ['2026-03-08', '2026-03-09'] for facility, units in [('HSP-R', 0), ('RBTC-A', 10)]],
                 columns=['date', 'facility_id', 'component', 'blood_group', 'units_in_stock_end_of_day']).to_csv(tmp_path / 'daily_stock.csv', index=False)
    pd.DataFrame([('U1', 'RBC', 'RBTC-A', 'A+', '2026-02-20', '2026-03-20', None, 'in_stock')],
                 columns=['unit_id', 'component', 'current_facility_id', 'blood_group', 'collection_date', 'expiry_date', 'status_date', 'status']).to_csv(tmp_path / 'units.csv', index=False)
    pd.DataFrame(columns=REQUEST_COLUMNS).to_csv(tmp_path / 'requests.csv', index=False)
    pd.DataFrame(columns=['transfer_id', 'request_id', 'unit_id', 'from_facility_id', 'to_facility_id', 'transfer_type', 'dispatched_at', 'received_at']).to_csv(tmp_path / 'transfers.csv', index=False)
    settings = load_settings()
    settings['demo_clock'] = '2026-03-10T01:00:00+03:00'
    app = create_app(test_config={'TESTING': True, 'AUTH_DISABLED': True, 'DB_PATH': str(tmp_path / 'workflow.sqlite'), 'SETTINGS': settings})
    app.test_client_class = RetryClient
    imported = app.test_cli_runner().invoke(args=['ingest-data'])
    assert imported.exit_code == 0, imported.output
    client = app.test_client()
    assert client.get('/api/ready').status_code == 200
    assert client.get('/api/facilities?q=Synthetic&kind=centre').json['items'][0]['details']['facility_id'] == 'RBTC-A'
    response = create(client)
    assert response.status_code == 201, response.json
    identifier = response.json['id']
    assert response.json['ranking']['model_used'] is False
    assert pick(client, identifier).status_code == 200
    payload = {'supplier_id': 'RBTC-A', 'attempt': 1, 'confirmed_units': 3}
    assert client.post(f'/api/requests/{identifier}/confirm', json=payload).status_code == 200
    assert client.post(f'/api/requests/{identifier}/dispatch', json=payload).status_code == 200
    repeat = app.test_cli_runner().invoke(args=['ingest-data'])
    assert repeat.exit_code != 0
    assert 'refusing to reset consumed stock' in repeat.output
    assert client.get('/api/facilities/RBTC-A/inventory').json['items'][0]['on_hand'] == 7


def test_prealert_cli_uses_shared_persistence(app, client):
    app.config['PREALERT_PROVIDER'] = lambda as_of: {'alerts': [], 'generated_at': as_of.isoformat()}
    result = app.test_cli_runner().invoke(args=['run-prealerts'])
    assert result.exit_code == 0
    identifier = json.loads(result.output)['id']
    assert client.get(f'/api/prealerts/runs/{identifier}').status_code == 200
    assert client.get('/api/operations/audit').json['items'][0]['action'] == 'prealerts_generated'


def test_prealerts_missing_dataset_is_unavailable(app, client, monkeypatch):
    monkeypatch.delenv('DATA_DIR', raising=False)
    assert client.post('/api/prealerts/runs', json={}).status_code == 503


def test_corrupt_engine_returns_unavailable(app, client, tmp_path, monkeypatch):
    app.config.pop('RANKING_PROVIDER')
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('ENGINE_DB_PATH', str(tmp_path / 'corrupt.sqlite'))
    (tmp_path / 'corrupt.sqlite').write_text('Not a database')
    assert create(client).status_code == 503


def test_ingestion_missing_configuration_is_clear(app, monkeypatch):
    monkeypatch.delenv('DATA_DIR', raising=False)
    monkeypatch.delenv('ENGINE_DB_PATH', raising=False)
    result = app.test_cli_runner().invoke(args=['ingest-data'])
    assert result.exit_code != 0
    assert 'DATA_DIR is not set' in result.output
