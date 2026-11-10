import re

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(test_config={'TESTING': True, 'DB_PATH': str(tmp_path / 'docs.sqlite'), 'AUTH_DISABLED': False})


def test_swagger_and_local_assets_are_public(app):
    client = app.test_client()
    page = client.get('/api/docs')
    assert page.status_code == 200
    assert b'/api/openapi.json' in page.data
    assert b'validatorUrl: null' in page.data
    for path in re.findall(rb'(?:src|href)="([^"]+)"', page.data):
        assert path.startswith(b'/api/docs/assets/')
        assert client.get(path.decode()).status_code == 200
    assert client.get('/api/docs/').status_code == 200
    assert client.get('/api/requests').status_code == 503  # Docs never disable auth.


def test_spec_documents_every_concrete_api_operation(app):
    spec = app.test_client().get('/api/openapi.json').json
    assert spec['openapi'] == '3.0.3'
    expected = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith(('api_docs.', 'static')):
            continue
        path = re.sub(r'<(?:path:)?identifier>', '{id}', rule.rule)
        for method in rule.methods - {'HEAD', 'OPTIONS'}:
            if '<action>' in path:
                expected.update((path.replace('<action>', action), method.lower())
                                for action in ('pick', 'confirm', 'reject', 'dispatch', 'cancel', 'receive'))
            else:
                expected.add((path, method.lower()))
    documented = {(path, method) for path, operations in spec['paths'].items() for method in operations}
    assert documented == expected
    assert len(documented) == 28
    ids = [operation['operationId'] for operations in spec['paths'].values() for operation in operations.values()]
    assert len(ids) == len(set(ids))
    for path, method in documented:
        operation = spec['paths'][path][method]
        if method in {'post', 'put'} and path != '/api/sms':
            assert any(param['name'] == 'Idempotency-Key' and param['required'] for param in operation['parameters'])
        if '{id}' in path:
            assert any(param['name'] == 'id' and param['in'] == 'path' and param['required'] for param in operation['parameters'])
        assert operation.get('security') == [] if path in {'/api/health', '/api/ready', '/api/sms'} else 'security' not in operation
