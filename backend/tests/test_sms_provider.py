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
