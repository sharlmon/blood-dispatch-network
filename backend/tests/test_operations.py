import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import create_app
from app import operations
from app.clerk_auth import ClerkVerifier
from app.storage import get_db
from dataset_fixture import write_dataset
from test_clerk_auth import ISSUER, ORIGIN, keys, token
from test_workflow import app, client, create, pick


def test_response_retention_never_replays_a_mutation(app, client):
    payload = {'facility_id': 'HSP-R', 'patient_group': 'A+', 'units_needed': 3}
    headers = {'Idempotency-Key': 'retained'}
    result = client.post('/api/requests', json=payload, headers=headers)
    assert result.status_code == 201
    with app.app_context():
        db = get_db()
        db.execute('UPDATE idempotency SET created_at=?', ((operations.wall_now() - timedelta(days=31)).isoformat(),))
        db.commit()
    compacted = app.test_cli_runner().invoke(args=['prune-idempotency'])
    assert compacted.exit_code == 0
    assert json.loads(compacted.output)['compacted_responses'] == 1
    retry = client.post('/api/requests', json=payload, headers=headers)
    assert retry.status_code == 409
    assert 'expired' in retry.json['error']['message']
    assert len(client.get('/api/requests').json['items']) == 1


def test_legacy_schema_migration_preserves_retry_keys(tmp_path):
    path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE idempotency(actor TEXT,key TEXT,fingerprint TEXT,response TEXT,status INTEGER,PRIMARY KEY(actor,key))')
        db.execute("INSERT INTO idempotency VALUES('actor','key','fingerprint','{}',201)")
    for _ in range(2):
        app = create_app(test_config={'TESTING': True, 'DB_PATH': str(path)})
        with app.app_context():
            db = get_db()
            record = db.execute('SELECT * FROM idempotency').fetchone()
            assert record['key'] == 'key'
            assert datetime.fromisoformat(record['created_at']).tzinfo is not None
            assert db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0] == 1
            assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'


def test_backup_restore_is_consistent_and_never_overwrites(app, client, tmp_path):
    identifier = create(client).json['id']
    pick(client, identifier)
    backup = tmp_path / 'backups' / 'snapshot.sqlite'
    runner = app.test_cli_runner()
    result = runner.invoke(args=['backup-db', '--output', str(backup)])
    assert result.exit_code == 0, result.output
    assert backup.stat().st_mode & 0o777 == 0o600
    assert runner.invoke(args=['backup-db', '--output', str(backup)]).exit_code != 0
    restored = tmp_path / 'restored.sqlite'
    assert runner.invoke(args=['restore-db', str(backup), '--output', str(restored)]).exit_code == 0
    with sqlite3.connect(restored) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT status FROM requests WHERE id=?', (identifier,)).fetchone()[0] == 'awaiting_confirmation'
        assert db.execute('SELECT reserved FROM inventory').fetchone()[0] == 3
    assert runner.invoke(args=['restore-db', str(backup), '--output', app.config['DB_PATH']]).exit_code != 0


def test_backup_rejects_corrupt_or_unrelated_database(tmp_path):
    source = tmp_path / 'bad.sqlite'
    source.write_text('invalid')
    with pytest.raises(sqlite3.Error):
        operations.copy_database(source, tmp_path / 'copy.sqlite')
    assert not (tmp_path / 'copy.sqlite').exists()
    assert list(tmp_path.glob('.database-backup-*')) == []
    source = tmp_path / 'other.sqlite'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE unrelated(x)')
    with pytest.raises(ValueError, match='workflow database'):
        operations.copy_database(source, tmp_path / 'copy.sqlite')


def test_maintenance_is_durable_and_deduplicates_prealerts(app, client):
    identifier = create(client).json['id']
    pick(client, identifier)
    app.config['SETTINGS']['demo_clock'] = '2026-03-10T18:00:00+03:00'
    app.config['PREALERT_PROVIDER'] = lambda as_of: {'alerts': [], 'generated_at': as_of.isoformat()}
    runner = app.test_cli_runner()
    first = runner.invoke(args=['maintenance', '--once'])
    assert first.exit_code == 0, first.output
    second = runner.invoke(args=['maintenance', '--once'])
    assert second.exit_code == 0
    assert set(json.loads(second.output).values()) == {'skipped'}
    assert len(client.get('/api/prealerts/runs').json['items']) == 1
    events = client.get('/api/audit', query_string={'request_id': identifier}).json['items']
    assert len([event for event in events if event['action'] == 'confirmation_expired']) == 1
    with app.app_context():
        assert get_db().execute("SELECT completed_key FROM scheduled_jobs WHERE name='prealerts'").fetchone()[0] == '2026-03-10'


def test_failed_maintenance_retries_without_checkpoint_or_secret(app, client, monkeypatch):
    from app.workflow import APIError
    app.config['SETTINGS']['demo_clock'] = '2026-03-10T18:00:00+03:00'
    def fail(as_of):
        raise APIError('private-secret', 503)
    app.config['PREALERT_PROVIDER'] = fail
    first = app.test_cli_runner().invoke(args=['maintenance', '--once'])
    assert first.exit_code != 0
    with app.app_context():
        row = get_db().execute("SELECT * FROM scheduled_jobs WHERE name='prealerts'").fetchone()
        assert row['completed_key'] is None
        assert row['last_error'] == 'APIError'
    assert client.get('/api/prealerts/runs').json['items'] == []
    stamp = operations.wall_now() + timedelta(minutes=2)
    monkeypatch.setattr(operations, 'wall_now', lambda: stamp)
    app.config['PREALERT_PROVIDER'] = lambda as_of: {'alerts': []}
    retry = app.test_cli_runner().invoke(args=['maintenance', '--once'])
    assert retry.exit_code == 0
    assert len(client.get('/api/prealerts/runs').json['items']) == 1


def test_production_startup_refuses_demo_auth(tmp_path):
    with pytest.raises(ValueError, match='AUTH_DISABLED must be off'):
        create_app(test_config={'TESTING': True, 'APP_ENV': 'production', 'AUTH_DISABLED': True, 'DB_PATH': str(tmp_path / 'prod.sqlite')})


def test_real_signed_tokens_enforce_full_workflow(app, client, keys):
    app.config['AUTH_DISABLED'] = False
    app.config['ORG_FACILITY_MAP'] = {'org_requester': 'HSP-R', 'org_supplier': 'RBTC-A'}
    verifier = ClerkVerifier(ISSUER, authorized_parties=[ORIGIN])
    verifier.jwks.get_signing_key_from_jwt = lambda encoded: SimpleNamespace(key=keys[0].public_key())
    app.extensions['clerk_verifier'] = verifier
    requester = {'Authorization': 'Bearer ' + token(keys[0], sub='lab', org_id='org_requester', org_role='org:member')}
    supplier = {'Authorization': 'Bearer ' + token(keys[0], sub='supplier', org_id='org_supplier', org_role='org:member')}
    forged = {'Authorization': 'Bearer ' + token(keys[1], sub='attacker', org_id='org_supplier')}
    identifier = client.post('/api/requests', json={'facility_id': 'HSP-R', 'patient_group': 'A+', 'units_needed': 3}, headers=requester).json['id']
    assert client.post(f'/api/requests/{identifier}/pick', json={'supplier_id': 'RBTC-A'}, headers=requester).status_code == 200
    payload = {'supplier_id': 'RBTC-A', 'attempt': 1, 'confirmed_units': 3}
    assert client.post(f'/api/requests/{identifier}/confirm', json=payload, headers=forged).status_code == 401
    assert client.post(f'/api/requests/{identifier}/confirm', json=payload, headers=requester).status_code == 403
    assert client.post(f'/api/requests/{identifier}/confirm', json=payload, headers=supplier).status_code == 200
    assert client.post(f'/api/requests/{identifier}/dispatch', json=payload, headers=supplier).status_code == 200
    assert client.post(f'/api/requests/{identifier}/receive', json={'received_units': 3}, headers=requester).json['status'] == 'received'


def test_request_logging_redacts_credentials_and_payload(app, client, caplog):
    with caplog.at_level(logging.INFO, logger='app'):
        response = client.get('/api/health?secret=private-value', headers={'Authorization': 'Bearer private-token'})
    assert response.headers['X-Request-ID']
    messages = '\n'.join(record.getMessage() for record in caplog.records)
    assert 'http_request' in messages
    assert 'private-value' not in messages and 'private-token' not in messages
    assert '/api/health' in messages


def test_isolated_dataset_validation_preserves_operational_database(app, client, tmp_path):
    identifier = create(client).json['id']
    dataset = write_dataset(tmp_path / 'synthetic')
    report = tmp_path / 'report.json'
    result = app.test_cli_runner().invoke(args=['verify-workflow', '--data-dir', str(dataset), '--group', 'A+', '--report', str(report)])
    assert result.exit_code == 0, result.output
    data = json.loads(report.read_text())
    assert data['status'] == 'passed'
    assert len(data['scenarios']) == 3
    assert all(value == 'passed' for value in data['scenarios'].values())
    assert client.get(f'/api/requests/{identifier}').json['status'] == 'pending'
    assert len(client.get('/api/requests').json['items']) == 1


def test_named_backups_are_unique(app, tmp_path):
    args = ['backup-db', '--directory', str(tmp_path / 'backups')]
    first = app.test_cli_runner().invoke(args=args)
    second = app.test_cli_runner().invoke(args=args)
    assert first.exit_code == second.exit_code == 0
    assert json.loads(first.output)['backup'] != json.loads(second.output)['backup']
    assert len(list((tmp_path / 'backups').glob('*.sqlite'))) == 2


def test_two_maintenance_workers_generate_one_prealert(app):
    from concurrent.futures import ThreadPoolExecutor
    app.config['SETTINGS']['demo_clock'] = '2026-03-10T18:00:00+03:00'
    app.config['PREALERT_PROVIDER'] = lambda as_of: {'alerts': []}
    def run(_):
        with app.app_context():
            return operations.maintenance_tick()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert [value['prealerts'] for value in results].count('completed') == 1
    with app.app_context():
        assert get_db().execute('SELECT COUNT(*) FROM prealert_runs').fetchone()[0] == 1


def test_abandoned_maintenance_claim_recovers(app, monkeypatch):
    app.config['SETTINGS']['demo_clock'] = '2026-03-10T18:00:00+03:00'
    app.config['PREALERT_PROVIDER'] = lambda as_of: {'alerts': []}
    stamp = operations.wall_now()
    with app.app_context():
        assert operations._claim('prealerts', '2026-03-10', stamp)
        assert operations.maintenance_tick()['prealerts'] == 'skipped'
        monkeypatch.setattr(operations, 'wall_now', lambda: stamp + timedelta(minutes=16))
        assert operations.maintenance_tick()['prealerts'] == 'completed'
        assert get_db().execute('SELECT COUNT(*) FROM prealert_runs').fetchone()[0] == 1


def test_sms_retry_tombstone_preserves_deduplication(app, client):
    from test_backend_api import sms
    app.config['SMS_WEBHOOK_SECRET'] = 'test-secret'
    app.config['SMS_SENDERS'] = {'+254700000001': {'user_id': 'sms-user', 'org_id': 'org_requester', 'facility_id': 'HSP-R'}}
    payload = {'message_id': 'old-sms', 'from': '+254700000001', 'text': 'REQUEST A+ 3'}
    assert sms(client, app, payload).status_code == 201
    with app.app_context():
        db = get_db()
        db.execute('UPDATE idempotency SET created_at=?', ((operations.wall_now() - timedelta(days=31)).isoformat(),))
        db.commit()
        assert operations.prune_responses(30) == 1
    assert sms(client, app, payload).status_code == 409
    assert len(client.get('/api/requests').json['items']) == 1


def test_demo_seed_never_counts_as_previous_closing_snapshot(tmp_path, monkeypatch):
    from app import load_settings, services
    settings = load_settings()
    settings['demo_clock'] = '2026-11-01T01:00:00+03:00'  # Still 31 October in UTC.
    app = create_app(test_config={'TESTING': True, 'AUTH_DISABLED': True, 'SETTINGS': settings, 'DB_PATH': str(tmp_path / 'seed.sqlite')})
    monkeypatch.setattr(services, 'engine_ready', lambda: True)
    assert app.test_cli_runner().invoke(args=['seed-demo']).exit_code == 0
    response = app.test_client().get('/api/ready')
    assert response.status_code == 503
    assert response.json['inventory_loaded'] is False
