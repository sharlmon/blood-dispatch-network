"""Provider boundary tests: never use a real network or real credentials."""
import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs

import pytest

from app import sms_provider as provider
from app.storage import atomic, get_db
from test_workflow import app, client, create, pick

TOKEN = 'test-callback-token-' + 'x' * 32
REQUESTER = '+254700000001'
SUPPLIER = '+254700000002'


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('A test attempted a real provider call')
    monkeypatch.setattr(provider, 'build_opener', blocked)


@pytest.fixture
def enabled(app):
    app.config.update(SMS_ENABLED=True, SMS_ENVIRONMENT='sandbox',
                      AFRICASTALKING_CALLBACK_TOKEN=TOKEN,
                      AFRICASTALKING_SANDBOX_API_KEY='fake-sandbox',
                      AFRICASTALKING_API_KEY='fake-live', AFRICASTALKING_USERNAME='test-app',
                      AFRICASTALKING_INBOUND_NUMBERS=['12345'],
                      SMS_SENDERS={REQUESTER: {'user_id': 'r', 'org_id': 'requester', 'facility_id': 'HSP-R'},
                                   SUPPLIER: {'user_id': 's', 'org_id': 'supplier', 'facility_id': 'RBTC-A'}})
    return app


def rows(app):
    with app.app_context():
        return [dict(r) for r in get_db().execute('SELECT * FROM sms_outbox ORDER BY created_at,id')]


def inbound(client, **overrides):
    return client.post('/api/sms/africastalking/inbound?token=' + TOKEN,
                       data={'from': REQUESTER, 'to': '12345', 'id': 'in-1', 'text': 'REQUEST A+ 3', **overrides})


def report(client, identifier, status):
    return client.post('/api/sms/africastalking/delivery?token=' + TOKEN, data={'id': identifier, 'status': status})


def test_queue_is_atomic_and_retries_dont_duplicate(enabled, client):
    headers = {'Idempotency-Key': 'one-request'}
    first = client.post('/api/requests', json={'facility_id': 'HSP-R', 'patient_group': 'A+', 'units_needed': 3}, headers=headers)
    assert first.status_code == 201
    assert client.post('/api/requests', json={'facility_id': 'HSP-R', 'patient_group': 'A+', 'units_needed': 3}, headers=headers).json == first.json
    assert len(rows(enabled)) == 1
    assert pick(client, first.json['id']).status_code == 200
    assert len(rows(enabled)) == 3  # requester and supplier receive selection event
    with enabled.app_context():
        with pytest.raises(RuntimeError), atomic() as db:
            provider.enqueue(db, 'rollback', REQUESTER, 'Never send')
            raise RuntimeError()
    assert len(rows(enabled)) == 3


def test_disabled_sms_never_queues_or_sends(app, client):
    app.config['SMS_ENABLED'] = False
    create(client)
    assert rows(app) == []
    with app.app_context():
        assert provider.drain()['disabled']


def test_inbound_scope_reply_and_deduplication(enabled, client):
    first = inbound(client)
    assert first.status_code == 200
    assert inbound(client).json == first.json
    assert len(rows(enabled)) == 1  # one reply, no duplicate event notification to origin
    assert inbound(client, text='REQUEST A+ 2').status_code == 409
    assert inbound(client, id='other', **{'from': '+254700000099'}).status_code == 403
    assert inbound(client, to='unknown').status_code == 403
    assert client.post('/api/sms/africastalking/inbound', data={}).status_code == 401
    denied = inbound(client, id='denied', text=f"CONFIRM {first.json['request']['id']} 1 3")
    assert denied.status_code == 200
    assert denied.json['error'] == 403
    assert len(rows(enabled)) == 2
    assert inbound(client, id='denied', text=f"CONFIRM {first.json['request']['id']} 1 3").json == denied.json
    assert len(rows(enabled)) == 2


def test_invalid_command_reply_does_not_create_request(enabled, client):
    assert inbound(client, text='WRONG').json['error'] == 400
    assert len(client.get('/api/requests').json['items']) == 0
    assert len(rows(enabled)) == 1


def test_worker_acceptance_and_delivery_order(enabled, client, monkeypatch):
    create(client)
    # A delivery callback can arrive before the outbound HTTP response.
    assert report(client, 'AT-test', 'Success').status_code == 200
    monkeypatch.setattr(provider, 'send_message', lambda row: {'status': 'accepted', 'provider_id': 'AT-test', 'provider_status': '100', 'cost': 'KES 0.80'})
    with enabled.app_context():
        assert provider.drain() == {'processed': 1}
        assert provider.drain() == {'processed': 0}
    assert rows(enabled)[0]['status'] == 'delivered'
    for status in ['Buffered', 'Submitted', 'Failed', 'Success']:
        assert report(client, 'AT-test', status).status_code == 200
        assert rows(enabled)[0]['status'] == 'delivered'
    assert client.post('/api/sms/africastalking/delivery?token=wrong', data={'id': 'AT-test', 'status': 'Failed'}).status_code == 401
    assert report(client, 'AT-test', 'invalid').status_code == 400
    assert client.get('/api/requests').json['items'][0]['status'] == 'pending'


@pytest.mark.parametrize('outcome', [{'status': 'failed', 'error_code': 'provider_406'}, {'status': 'unknown', 'error_code': 'timeout'}])
def test_failed_and_ambiguous_sends_not_retried(enabled, client, monkeypatch, outcome):
    create(client)
    calls = []
    def send(row):
        calls.append(row['id'])
        return outcome
    monkeypatch.setattr(provider, 'send_message', send)
    with enabled.app_context():
        provider.drain()
        provider.drain()
    assert len(calls) == 1
    assert rows(enabled)[0]['status'] == outcome['status']
    assert client.get('/api/requests').json['items'][0]['status'] == 'pending'


def test_concurrent_workers_claim_once(enabled, client, monkeypatch):
    create(client)
    calls = []
    def send(row):
        calls.append(row['id'])
        return {'status': 'accepted', 'provider_id': 'AT-concurrent'}
    monkeypatch.setattr(provider, 'send_message', send)
    def work(_):
        with enabled.app_context():
            return provider.drain()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(work, range(2)))
    assert len(calls) == 1


class Response(BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


@pytest.mark.parametrize('environment', ['sandbox', 'live'])
def test_transport_uses_matching_credentials(enabled, monkeypatch, environment):
    enabled.config['SMS_ENVIRONMENT'] = environment
    captured = []
    class Opener:
        def open(self, req, timeout):
            captured.append(req)
            return Response(json.dumps({'SMSMessageData': {'Recipients': [{'number': REQUESTER, 'statusCode': 100, 'messageId': 'AT-transport', 'cost': 'KES 0.80'}]}}).encode())
    monkeypatch.setattr(provider, 'build_opener', lambda *args: Opener())
    with enabled.app_context():
        result = provider.send_message({'environment': environment, 'recipient': REQUESTER, 'body': 'Test'})
    assert result['status'] == 'accepted'  # Never 'delivered' from a send response.
    req = captured[0]
    assert req.get_header('Apikey') == ('fake-sandbox' if environment == 'sandbox' else 'fake-live')
    assert parse_qs(req.data.decode())['username'] == (['sandbox'] if environment == 'sandbox' else ['test-app'])
    assert req.full_url == ('https://api.sandbox.africastalking.com/version1/messaging' if environment == 'sandbox' else 'https://api.africastalking.com/version1/messaging')


@pytest.mark.parametrize('error,expected', [(HTTPError('url', 401, '', {}, None), 'failed'), (HTTPError('url', 500, '', {}, None), 'unknown'), (URLError('secret must not leak'), 'unknown')])
def test_transport_sanitizes_errors(enabled, monkeypatch, error, expected):
    class Opener:
        def open(self, *args, **kwargs):
            raise error
    monkeypatch.setattr(provider, 'build_opener', lambda *args: Opener())
    with enabled.app_context():
        result = provider.send_message({'environment': 'sandbox', 'recipient': REQUESTER, 'body': 'Test'})
    assert result['status'] == expected
    assert 'secret must not leak' not in json.dumps(result)


def test_blacklist_is_recipient_failure_even_when_http_succeeds(enabled, monkeypatch):
    class Opener:
        def open(self, *args, **kwargs):
            return Response(json.dumps({'SMSMessageData': {'Recipients': [{'number': REQUESTER, 'statusCode': 406, 'messageId': 'None'}]}}).encode())
    monkeypatch.setattr(provider, 'build_opener', lambda *args: Opener())
    with enabled.app_context():
        assert provider.send_message({'environment': 'sandbox', 'recipient': REQUESTER, 'body': 'Test'}) == {'status': 'failed', 'provider_status': '406', 'error_code': 'provider_406'}


def test_abandoned_claim_becomes_unknown(enabled, client):
    create(client)
    with enabled.app_context(), atomic() as db:
        db.execute("UPDATE sms_outbox SET status='sending',updated_at='2020-01-01T00:00:00+00:00'")
    with enabled.app_context():
        assert provider.drain()['processed'] == 0
    assert rows(enabled)[0]['status'] == 'unknown'


def test_provider_command_rollback_and_transient_retry(enabled, client, monkeypatch):
    from app import sms
    from app.workflow import APIError
    original = sms.execute_command
    def incomplete(db, text, mapping):
        original(db, text, mapping)
        raise APIError('Transient unavailable', 503)
    monkeypatch.setattr(sms, 'execute_command', incomplete)
    assert inbound(client).status_code == 503
    assert rows(enabled) == []
    assert client.get('/api/requests').json['items'] == []
    monkeypatch.setattr(sms, 'execute_command', original)
    assert inbound(client).status_code == 200
    assert len(rows(enabled)) == 1


def test_retry_cli_only_accepts_definite_failures(enabled, client):
    create(client)
    item = rows(enabled)[0]['id']
    runner = enabled.test_cli_runner()
    with enabled.app_context(), atomic() as db:
        db.execute("UPDATE sms_outbox SET status='unknown'")
    assert runner.invoke(args=['sms-retry', item]).exit_code != 0
    with enabled.app_context(), atomic() as db:
        db.execute("UPDATE sms_outbox SET status='failed',error_code='provider_406'")
    assert runner.invoke(args=['sms-retry', item]).exit_code == 0
    assert rows(enabled)[0]['status'] == 'queued'


def test_delivery_failure_cannot_regress_to_buffered(enabled, client, monkeypatch):
    create(client)
    monkeypatch.setattr(provider, 'send_message', lambda row: {'status': 'accepted', 'provider_id': 'AT-fail'})
    with enabled.app_context():
        provider.drain()
    assert report(client, 'AT-fail', 'Failed').status_code == 200
    assert report(client, 'AT-fail', 'Buffered').status_code == 200
    assert rows(enabled)[0]['status'] == 'delivery_failed'
    assert report(client, 'AT-fail', 'Success').status_code == 200
    assert rows(enabled)[0]['status'] == 'delivered'


@pytest.mark.parametrize('field,value', [('SMS_ENVIRONMENT', 'wrong'), ('AFRICASTALKING_CALLBACK_TOKEN', 'short'), ('SMS_SENDERS', {'0700000001': {}})])
def test_config_rejects_invalid_sms_settings(enabled, field, value):
    config = dict(enabled.config)
    config[field] = value
    with pytest.raises(ValueError):
        provider.validate_config(config)


def test_environment_never_falls_back_to_other_key(enabled):
    config = dict(enabled.config)
    config['AFRICASTALKING_SANDBOX_API_KEY'] = ''
    with pytest.raises(ValueError):
        provider.validate_config(config)


def test_shared_outbound_contact_deduplicates_without_inbound_permission(enabled, client):
    enabled.config['SMS_SENDERS'] = {}
    enabled.config['SMS_FACILITY_CONTACTS'] = {'HSP-R': [REQUESTER], 'RBTC-A': [REQUESTER]}
    identifier = create(client).json['id']
    assert pick(client, identifier).status_code == 200
    queued = rows(enabled)
    assert len(queued) == 2  # one per event, even when both facilities share a phone
    assert {r['recipient'] for r in queued} == {REQUESTER}
    assert inbound(client).status_code == 403


@pytest.mark.parametrize('contacts', [[], {'HSP-R': 'not-a-list'}, {'HSP-R': ['0700000001']}, {'': [REQUESTER]}])
def test_outbound_contact_config_validation(enabled, contacts):
    config = dict(enabled.config)
    config['SMS_FACILITY_CONTACTS'] = contacts
    with pytest.raises(ValueError):
        provider.validate_config(config)


def test_short_commands_and_supplier_messages(enabled, client):
    first = inbound(client, text='request a pos 3')
    identifier = first.json['request']['id']
    reply = first.json['reply']
    option = first.json['request']['ranking']['options'][0]
    assert f"1 {option['name']}" in reply
    assert "yesterday's count, unconfirmed" in reply
    assert "Today's way:" in reply
    assert inbound(client, id='status', text='status').json['request']['id'] == identifier
    assert inbound(client, id='pick', text='1').json['request']['status'] == 'awaiting_confirmation'
    supplier_text = next(r['body'] for r in rows(enabled) if r['recipient'] == SUPPLIER)
    assert '3 A+ red cell units' in supplier_text and 'Reply YES' in supplier_text
    confirmed = inbound(client, id='yes', text='yes', **{'from': SUPPLIER})
    assert confirmed.json['request']['status'] == 'confirmed'
    assert 'Reply SENT' in confirmed.json['reply']
    assert any('confirmed. Most likely' in r['body'] for r in rows(enabled) if r['recipient'] == REQUESTER)
    sent = inbound(client, id='sent', text='sent', **{'from': SUPPLIER})
    assert sent.json['request']['status'] == 'dispatched'
    assert inbound(client, id='sent', text='sent', **{'from': SUPPLIER}).json == sent.json


def test_cancel_help_and_normalization(enabled, client):
    for i, group in enumerate(['o pos', 'o−', 'o-']):
        result = inbound(client, id=f'group-{i}', text=f'request {group} 1')
        assert result.json['request']['blood_group'] == ('O+' if i == 0 else 'O-')
    assert inbound(client, id='cancel', text='cancel').json['request']['status'] == 'cancelled'
    assert inbound(client, id='help', text='???').json['reply'].startswith('HELP:')
    assert inbound(client, id='bad-role', text='YES').json['error'] == 409


@pytest.mark.parametrize('timeout', [False, True])
def test_next_supplier_notice(enabled, client, timeout):
    with enabled.app_context(), atomic() as db:
        db.execute("INSERT INTO facilities VALUES('RBTC-B','Next Centre','centre')")
        db.execute("INSERT INTO inventory VALUES('RBTC-B','A+','red_cells',5,0,1,'2026-03-09T23:59:59+03:00')")
    inbound(client)
    inbound(client, id='pick', text='1')
    if timeout:
        enabled.config['SETTINGS']['demo_clock'] = '2026-03-10T01:11:00+03:00'
        assert enabled.test_cli_runner().invoke(args=['expire-confirmations']).exit_code == 0
    else:
        assert inbound(client, id='no', text='no', **{'from': SUPPLIER}).json['request']['attempt'] == 2
    assert any(' next (' in r['body'] for r in rows(enabled) if r['recipient'] == REQUESTER)


def test_options_render_real_golden_engine_output(frames, eta_model):
    from engine.rank import rank_sources, request_from_dataset
    from app.sms import request_reply
    payload = request_from_dataset(frames, 'REQ-020421')
    ranking = rank_sources(payload, frames=frames, eta_model=eta_model)
    result = dict(id='REQ-1042', blood_group='O+', units=1, status='pending', ranking=ranking)
    reply = request_reply(result)
    for i, option in enumerate(ranking['options'][:3], 1):
        assert f"{i} {option['name']} {option['eta']['p50']:.1f}h" in reply
    assert '~8.9h' in reply
    ranking['advice'] = 'no_full_source'
    assert request_reply(result).startswith('No single site has enough')
    ranking['advice'] = 'too_long'
    assert request_reply(result).startswith('Wait may pass 6h: consider emergency group O or patient transfer.')


def test_golden_short_reply_workflow(enabled, client, frames, eta_model, built_db):
    import sqlite3
    from engine.rank import rank_sources
    enabled.config['SETTINGS']['demo_clock'] = '2026-10-31T00:58:20+03:00'
    enabled.config['RANKING_PROVIDER'] = lambda payload: rank_sources(payload, frames=frames, eta_model=eta_model)
    enabled.config['SMS_SENDERS'][REQUESTER]['facility_id'] = 'HSP-004'
    enabled.config['SMS_SENDERS'][SUPPLIER]['facility_id'] = 'HSP-001'
    with enabled.app_context(), atomic() as db, sqlite3.connect(built_db[0]) as source:
        for identifier, item in frames.facility_info.items():
            db.execute('INSERT OR IGNORE INTO facilities VALUES(?,?,?)', (identifier, item.get('name') or item.get('facility_name') or identifier, 'hospital'))
        for facility, group, units in source.execute("SELECT facility_id,blood_group,units_in_stock_end_of_day FROM daily_stock WHERE date='2026-10-30' AND component='RBC'"):
            db.execute("INSERT INTO inventory VALUES(?,?,'red_cells',?,0,0,'2026-10-30T23:59:59+03:00')", (facility, group, int(units)))
    result = inbound(client, text='request O pos 1')
    assert result.json['request']['ranking']['options'][0]['facility_id'] == 'HSP-001'
    assert 'National Referral' in result.json['reply'] and '~8.9h' in result.json['reply']
    assert inbound(client, id='gold-pick', text='1').json['request']['supplier_id'] == 'HSP-001'
    assert inbound(client, id='gold-yes', text='YES', **{'from': SUPPLIER}).json['request']['status'] == 'confirmed'
    assert inbound(client, id='gold-sent', text='SENT', **{'from': SUPPLIER}).json['request']['status'] == 'dispatched'
