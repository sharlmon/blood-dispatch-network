from concurrent.futures import ThreadPoolExecutor

import pytest

from app import create_app, load_settings
from flask.testing import FlaskClient
from uuid import uuid4


class RetryClient(FlaskClient):
    def open(self, *args, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("Idempotency-Key", str(uuid4()))
        return super().open(*args, headers=headers, **kwargs)

from app.storage import get_db


@pytest.fixture
def app(tmp_path):
    from test_rank import make_frames, FLAT_ETA
    from engine.rank import rank_sources
    settings = load_settings()
    settings['demo_clock'] = '2026-03-10T01:00:00+03:00'
    frames = make_frames([('RBTC-A', 'A+', 5), ('RBTC-B', 'A+', 5), ('RBTC-A', 'O+', 5)])
    app = create_app(test_config={'TESTING': True, 'AUTH_DISABLED': True, 'SETTINGS': settings,
        'DB_PATH': str(tmp_path / 'test.sqlite'),
        'RANKING_PROVIDER': lambda payload: rank_sources(payload, frames=frames, eta_model=FLAT_ETA)})
    app.test_client_class = RetryClient
    with app.app_context():
        db = get_db()
        db.executemany('INSERT INTO facilities VALUES(?,?,?)', [('HSP-R', 'Hospital', 'hospital'), ('RBTC-A', 'Centre', 'centre')])
        db.execute("INSERT INTO inventory VALUES('RBTC-A','A+','red_cells',5,0,1,'2026-03-09T23:59:59+03:00')")
        db.commit()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def create(client, **overrides):
    data = dict(facility_id='HSP-R', blood_group='A+', product='red_cells', units=3)
    data.update(overrides)
    return client.post('/api/requests', json=data)


def pick(client, identifier):
    return client.post(f'/api/requests/{identifier}/pick', json={'supplier_id': 'RBTC-A'})


def test_full_workflow(client):
    response = create(client)
    assert response.status_code == 201
    identifier = response.json['id']
    assert pick(client, identifier).json['status'] == 'awaiting_confirmation'
    payload = dict(supplier_id='RBTC-A', attempt=1, confirmed_units=3)
    assert client.post(f'/api/requests/{identifier}/confirm', json=payload).json['status'] == 'confirmed'
    assert client.post(f'/api/requests/{identifier}/dispatch', json=payload).json['status'] == 'dispatched'
    assert client.post(f'/api/requests/{identifier}/dispatch', json=payload).status_code == 409
    inventory = client.get('/api/facilities/RBTC-A/inventory').json['items'][0]
    assert (inventory['on_hand'], inventory['reserved']) == (2, 0)
    events = client.get('/api/audit', query_string={'request_id': identifier}).json['items']
    assert [event['action'] for event in events] == ['created', 'pick', 'confirm', 'dispatch']


def test_concurrent_reservations(app, client):
    identifiers = [create(client).json['id'] for _ in range(2)]
    def reserve(identifier):
        with app.test_client() as other:
            return pick(other, identifier).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, identifiers)) == [200, 409]


def test_rejection_releases_stock_and_blocks_old_attempt(client):
    identifier = create(client).json['id']
    pick(client, identifier)
    payload = dict(supplier_id='RBTC-A', attempt=1, reason='Stock unavailable')
    assert client.post(f'/api/requests/{identifier}/reject', json=payload).json['status'] == 'pending'
    # Rejected sources are not retried automatically or manually.
    assert pick(client, identifier).status_code == 409
    assert client.post(f'/api/requests/{identifier}/confirm', json={**payload, 'confirmed_units': 3}).status_code == 409


def test_timeout_and_cancellation(app, client):
    app.config['SETTINGS']['demo_clock'] = '2026-03-10T01:00:00+03:00'
    identifier = create(client).json['id']
    pick(client, identifier)
    app.config['SETTINGS']['demo_clock'] = '2026-03-10T01:11:00+03:00'
    payload = dict(supplier_id='RBTC-A', attempt=1, confirmed_units=3)
    assert client.post(f'/api/requests/{identifier}/confirm', json=payload).status_code == 409
    result = app.test_cli_runner().invoke(args=['expire-confirmations'])
    assert result.exit_code == 0
    assert 'Expired 1' in result.output
    assert pick(client, identifier).status_code == 409
    assert client.post(f'/api/requests/{identifier}/cancel', json={'reason': 'No longer needed'}).json['status'] == 'cancelled'
    assert client.get('/api/facilities/RBTC-A/inventory').json['items'][0]['reserved'] == 0


@pytest.mark.parametrize('changes', [{'units': True}, {'units': 0}, {'blood_group': 'invalid'}, {'product': 'platelets'}, {'facility_id': 'missing'}])
def test_invalid_requests(client, changes):
    assert create(client, **changes).status_code in (400, 404)
    assert client.get('/api/requests').json['items'] == []


def test_invalid_payloads_and_transitions(client):
    assert client.post('/api/requests', json=[]).status_code == 400
    assert client.post('/api/requests', data='{', content_type='application/json').status_code == 400
    assert client.get('/api/requests?limit=bad').status_code == 400
    assert client.get('/api/requests/missing').status_code == 404
    identifier = create(client).json['id']
    assert client.post(f'/api/requests/{identifier}/dispatch', json={}).status_code == 409
    assert client.get('/api/facilities/missing/inventory').status_code == 404


def test_seed_refuses_existing_facilities(app):
    result = app.test_cli_runner().invoke(args=['seed-demo'])
    assert result.exit_code != 0
    assert 'refusing to overwrite' in result.output


def test_seed_empty_database(tmp_path):
    app = create_app(test_config={'TESTING': True, 'AUTH_DISABLED': True, 'DB_PATH': str(tmp_path / 'demo.sqlite')})
    result = app.test_cli_runner().invoke(args=['seed-demo'])
    assert result.exit_code == 0
    client = app.test_client()
    assert len(client.get('/api/facilities').json['items']) == 2
    assert client.get('/api/ready').status_code == 503  # no engine dataset loaded


def test_insufficient_stock_rolls_back(client):
    identifier = create(client, units=5).json['id']
    assert pick(client, identifier).status_code == 409
    assert client.get(f'/api/requests/{identifier}').json['status'] == 'pending'
    assert client.get('/api/facilities/RBTC-A/inventory').json['items'][0]['reserved'] == 0
    assert len(client.get('/api/audit').json['items']) == 1
