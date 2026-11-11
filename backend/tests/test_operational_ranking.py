"""Live rankings and reservations must agree without changing historical replay."""
from pathlib import Path

import pytest

from app.storage import atomic, get_db
from test_workflow import app, client, create, pick
from test_rank import make_frames, FLAT_ETA


@pytest.fixture
def operational(app, monkeypatch):
    from engine import config, eta, load
    frames = make_frames(
        [('RBTC-A', 'A+', 100), ('RBTC-A', 'O+', 100), ('RBTC-B', 'A+', 100),
         ('HSP-B', 'A+', 100)],
        usual_rows=[('HSP-B', 'A+', 2)],
        unit_rows=[('WB', 'HSP-B', 'A+', '2026-02-01', '2026-03-15', None)] * 10,
    )
    app.config.pop('RANKING_PROVIDER')
    monkeypatch.setattr(config, 'db_path', lambda: Path('/unused-engine.sqlite'))
    monkeypatch.setattr(config, 'eta_model_path', lambda: Path('/unused-model.json'))
    monkeypatch.setattr(load, 'load_frames', lambda _: frames)
    monkeypatch.setattr(eta, 'load_model', lambda _: FLAT_ETA)
    return frames


def test_only_reservable_rbc_appears_and_cached_frames_stay_unchanged(app, client, operational):
    from engine.rank import rank_sources
    from app import services
    with app.app_context(), atomic() as db:
        db.execute("INSERT INTO facilities VALUES('RBTC-B','Whole-blood only','centre')")
        db.execute("INSERT INTO inventory VALUES('RBTC-B','A+','whole_blood',100,0,0,'2026-03-09T23:59:59+03:00')")
    response = create(client)
    assert response.status_code == 201
    ranking = response.json['ranking']
    assert [(o['facility_id'], o['spare']) for o in ranking['options']] == [('RBTC-A', 4)]
    assert 'less recorded use and reservations' in ranking['stock_note']
    assert pick(client, response.json['id']).status_code == 200
    with app.app_context():
        view = services.operational_frames()
    assert view is not operational
    assert operational.stock.units('2026-03-09', 'RBTC-A', 'A+') == 100
    historical = rank_sources(response.json['request'], frames=operational, eta_model=FLAT_ETA)
    assert next(o for o in historical['options'] if o['facility_id'] == 'RBTC-A')['spare'] == 200


def test_existing_reservations_are_counted_once(app, client, operational):
    with app.app_context(), atomic() as db:
        db.execute("UPDATE inventory SET on_hand=10,safety_stock=2")
    first = create(client).json
    assert pick(client, first['id']).status_code == 200  # reserve three of eight
    second = create(client, units=5)
    assert second.json['ranking']['options'][0]['spare'] == 5
    assert pick(client, second.json['id']).status_code == 200
    with app.app_context():
        row = get_db().execute('SELECT * FROM inventory').fetchone()
        assert row['reserved'] == 8
        assert row['on_hand'] - row['reserved'] == row['safety_stock']


def test_dispatch_consumption_removes_false_full_sources(app, client, operational):
    first = create(client).json
    assert pick(client, first['id']).status_code == 200
    payload = {'supplier_id': 'RBTC-A', 'attempt': 1, 'confirmed_units': 3}
    assert client.post(f"/api/requests/{first['id']}/confirm", json=payload).status_code == 200
    assert client.post(f"/api/requests/{first['id']}/dispatch", json=payload).status_code == 200
    second = create(client, units=2).json
    option = second['ranking']['options'][0]
    assert option['spare'] == 1 and 'partial' in option['flags']
    assert second['ranking']['advice'] == 'no_full_source'
    assert pick(client, second['id']).status_code == 409


def test_full_source_beyond_historical_top_choices_is_ranked(app, client, operational):
    with app.app_context(), atomic() as db:
        db.execute("INSERT INTO facilities VALUES('RBTC-B','Centre B','centre')")
        db.execute("INSERT INTO inventory VALUES('RBTC-B','A+','red_cells',8,0,1,'2026-03-09T23:59:59+03:00')")
    response = create(client, units=5).json
    assert [(o['facility_id'], o['spare']) for o in response['ranking']['options']] == [('RBTC-B', 7)]
    assert response['ranking']['baseline']['facility_id'] == 'RBTC-B'
    assert client.post(f"/api/requests/{response['id']}/pick", json={'supplier_id': 'RBTC-B'}).status_code == 200


def test_hospital_reserves_and_rbc_expiry_counts_are_preserved(app, client, operational):
    with app.app_context(), atomic() as db:
        db.execute("INSERT INTO facilities VALUES('HSP-B','Hospital B','hospital')")
        db.execute("INSERT INTO inventory VALUES('HSP-B','A+','red_cells',10,1,6,'2026-03-09T23:59:59+03:00')")
    response = create(client).json
    option = next(o for o in response['ranking']['options'] if o['facility_id'] == 'HSP-B')
    assert option['spare'] == 3
    assert option['near_expiry'] == 0  # WB unit records never become RBC expiry claims
    assert client.post(f"/api/requests/{response['id']}/pick", json={'supplier_id': 'HSP-B'}).status_code == 200
    with app.app_context():
        row = get_db().execute("SELECT * FROM inventory WHERE facility_id='HSP-B'").fetchone()
        assert row['on_hand'] - row['reserved'] == 6


@pytest.mark.parametrize('day', ['2026-03-08', '2026-03-10'])
def test_wrong_day_inventory_never_falls_back_to_dataset(app, client, operational, day):
    with app.app_context(), atomic() as db:
        db.execute('UPDATE inventory SET updated_at=?', (day + 'T23:59:59+03:00',))
    response = create(client).json
    assert response['ranking']['options'] == []
    assert response['ranking']['baseline']['facility_id'] is None


def test_stock_change_after_ranking_is_still_checked(app, client, operational):
    response = create(client).json
    with app.app_context(), atomic() as db:
        db.execute('UPDATE inventory SET on_hand=2')
    assert pick(client, response['id']).status_code == 409
    with app.app_context():
        assert get_db().execute('SELECT reserved FROM inventory').fetchone()[0] == 0


def test_existing_pending_request_can_refresh_its_saved_options(app, client, operational):
    response = create(client).json
    assert response['ranking']['options'][0]['spare'] == 4
    with app.app_context(), atomic() as db:
        db.execute('UPDATE inventory SET on_hand=2')
    refreshed = client.post(f"/api/requests/{response['id']}/options/refresh", json={})
    assert refreshed.status_code == 200
    assert refreshed.json['options'][0]['spare'] == 1
    assert 'partial' in refreshed.json['options'][0]['flags']
    detail = client.get(f"/api/requests/{response['id']}").json
    assert detail['ranking'] == refreshed.json
    audit = client.get('/api/audit', query_string={'request_id': response['id']}).json['items']
    assert audit[-1]['action'] == 'options_refreshed'
