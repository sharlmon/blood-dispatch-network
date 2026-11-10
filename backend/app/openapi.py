"""OpenAPI contract for the backend's concrete HTTP operations."""
GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-', 'unknown']


def ref(name):
    return {'$ref': '#/components/schemas/' + name}


def obj(properties, required=(), **extra):
    return {'type': 'object', 'properties': properties, **({'required': list(required)} if required else {}), **extra}


def param(name, location='query', schema=None, **extra):
    return {'name': name, 'in': location, 'required': location == 'path', 'schema': schema or {'type': 'string'}, **extra}


TEXT = {'type': 'string'}
TIME = {'type': 'string', 'format': 'date-time'}
UNITS = {'type': 'integer', 'minimum': 1, 'maximum': 100}
PAGING = [param('limit', schema={'type': 'integer', 'minimum': 1, 'maximum': 200, 'default': 50}), param('offset', schema={'type': 'integer', 'minimum': 0, 'default': 0})]
KEY = param('Idempotency-Key', 'header', {'type': 'string', 'minLength': 1, 'maxLength': 128}, required=True, description='Unique mutation key. Retry with the same key and exact body; use a new key for a new action.')


def build_spec():
    schemas = {
        'Error': obj({'error': obj({'code': TEXT, 'message': TEXT}, ('code', 'message'))}, ('error',)),
        'Identity': obj({'user_id': TEXT, 'session_id': {'type': 'string', 'nullable': True}, 'org_id': {'type': 'string', 'nullable': True}, 'org_role': {'type': 'string', 'nullable': True}, 'org_slug': {'type': 'string', 'nullable': True}}),
        'CreateRequest': obj({
            'facility_id': {**TEXT, 'example': 'HSP-004'},
            'patient_group': {'type': 'string', 'enum': GROUPS, 'example': 'O+'},
            'units_needed': {**UNITS, 'example': 2},
            'component': {'type': 'string', 'enum': ['RBC'], 'default': 'RBC'},
            'requested_at': {**TIME, 'description': 'Optional; within five minutes of the operational clock. Use demo_clock for historical data.'},
            'clinician_limit_h': {'type': 'number', 'minimum': 0, 'exclusiveMinimum': True, 'maximum': 72, 'default': 6},
            'blood_group': {'type': 'string', 'enum': GROUPS, 'deprecated': True, 'description': 'Legacy alias for patient_group; one of these is required.'},
            'units': {**UNITS, 'deprecated': True, 'description': 'Legacy alias for units_needed; one of these is required.'},
            'product': {'type': 'string', 'enum': ['red_cells'], 'deprecated': True},
        }, ('facility_id',), additionalProperties=False,
            allOf=[{'anyOf': [{'required': ['patient_group']}, {'required': ['blood_group']}]},
                   {'anyOf': [{'required': ['units_needed']}, {'required': ['units']}]}]),
        'Allocation': obj({'blood_group': TEXT, 'product': {'type': 'string', 'enum': ['red_cells']}, 'units': UNITS}),
        'ETA': obj({key: {'type': 'number', 'minimum': 0, 'description': 'Hours from request time'} for key in ('p10', 'p50', 'p90', 'wait_p50', 'road_p50')}),
        'SourceOption': obj({
            'rank': {'type': 'integer'}, 'facility_id': TEXT, 'name': TEXT, 'facility_type': TEXT,
            'is_hospital': {'type': 'boolean'}, 'spare': {'type': 'integer'}, 'stock_seen': {'type': 'integer'},
            'near_expiry': {'type': 'integer'}, 'has_backup_power': {'type': 'boolean'}, 'connectivity': TEXT,
            'travel_hours_map': {'type': 'number'}, 'eta': ref('ETA'), 'flags': {'type': 'array', 'items': TEXT},
            'reason': TEXT, 'spare_by_group': {'type': 'object', 'additionalProperties': {'type': 'integer'}},
        }),
        'Ranking': obj({
            'request': obj({'facility_id': TEXT, 'patient_group': TEXT, 'units_needed': UNITS, 'requested_at': TIME, 'as_of_stock_date': {'type': 'string', 'format': 'date'}}),
            'mode': {'type': 'string', 'enum': ['model', 'baseline']}, 'model_used': {'type': 'boolean'},
            'sharing_allowed': {'type': 'boolean'}, 'compatibility_note': TEXT, 'stock_note': TEXT,
            'advice': {'type': 'string', 'nullable': True}, 'options': {'type': 'array', 'items': ref('SourceOption')},
            'baseline': obj({'facility_id': {'type': 'string', 'nullable': True}, 'name': {'type': 'string', 'nullable': True}, 'quote_hours': {'type': 'number', 'nullable': True}, 'rule': TEXT}),
        }),
        'RequestSummary': obj({
            'id': {'type': 'string', 'format': 'uuid'}, 'facility_id': TEXT, 'blood_group': TEXT,
            'product': TEXT, 'units': UNITS,
            'status': {'type': 'string', 'enum': ['pending', 'awaiting_confirmation', 'confirmed', 'dispatched', 'received', 'cancelled']},
            'supplier_id': {'type': 'string', 'nullable': True}, 'attempt': {'type': 'integer'},
            'deadline': {**TIME, 'nullable': True}, 'created_at': TIME, 'updated_at': TIME,
        }),
        'Request': {'allOf': [ref('RequestSummary'), obj({'request': {'type': 'object'}, 'ranking': ref('Ranking'), 'selected_option': {'allOf': [ref('SourceOption')], 'nullable': True}, 'allocations': {'type': 'array', 'items': ref('Allocation')}})]},
        'Facility': obj({'id': TEXT, 'name': TEXT, 'kind': {'type': 'string', 'enum': ['hospital', 'centre']}, 'details': {'type': 'object', 'description': 'Imported engine facility metadata, including location when supplied.'}}),
        'Inventory': obj({'facility_id': TEXT, 'blood_group': TEXT, 'product': TEXT, 'on_hand': {'type': 'integer'}, 'reserved': {'type': 'integer'}, 'safety_stock': {'type': 'integer'}, 'available': {'type': 'integer'}, 'updated_at': TIME}),
        'AuditEvent': obj({'id': {'type': 'integer'}, 'request_id': TEXT, 'action': TEXT, 'details': {'type': 'object'}, 'created_at': TIME}),
        'OperationalEvent': obj({'id': {'type': 'integer'}, 'action': TEXT, 'actor': ref('Identity'), 'payload': {'type': 'object'}, 'created_at': TIME}),
        'Fallback': obj({'enabled': {'type': 'boolean'}, 'reason': {'type': 'string', 'nullable': True}, 'updated_at': {**TIME, 'nullable': True}}),
        'PrealertRun': obj({'id': TEXT, 'created_at': TIME, 'result': {'type': 'object', 'description': 'Existing pre-alert service output: alerts, missing_snapshot, assumptions, generated_at and stock_as_of.'}}),
        'SMS': obj({'message_id': {**TEXT, 'example': 'gateway-message-001'}, 'from': {**TEXT, 'example': '+254700000001'}, 'text': {**TEXT, 'example': 'REQUEST O+ 2'}}, ('message_id', 'from', 'text')),
    }
    paths = {}

    def operation(path, method, summary, tag, response=None, body=None, parameters=(), public=False, description='', status=200):
        errors = {str(code): {'description': label, 'content': {'application/json': {'schema': ref('Error')}}}
                  for code, label in [(400, 'Invalid input'), (401, 'Missing or invalid credentials'), (403, 'Access denied'), (404, 'Resource not found'), (409, 'State, stock or retry conflict'), (413, 'Body exceeds 64 KiB'), (503, 'Dependency unavailable; use the phone process')]}
        entry = {'operationId': method + '_' + path.strip('/').replace('/', '_').replace('{', '').replace('}', ''),
                 'summary': summary, 'tags': [tag], 'description': description,
                 'responses': {str(status): {'description': 'Success', 'content': {'application/json': {'schema': response or {'type': 'object'}}}}, **errors}}
        if public:
            entry['security'] = []
        parameters = list(parameters)
        if '{id}' in path:
            parameters.insert(0, param('id', 'path', description='Resource identifier returned by the API.'))
        if method in {'post', 'put'} and not path.startswith('/api/sms'):
            parameters.append(KEY)
        if parameters:
            entry['parameters'] = parameters
        if body is not None:
            entry['requestBody'] = {'required': True, 'content': {'application/json': {'schema': body}}}
        paths.setdefault(path, {})[method] = entry

    def listing(item, paged=True):
        fields = {'items': {'type': 'array', 'items': item}}
        if paged:
            fields.update(limit={'type': 'integer'}, offset={'type': 'integer'})
        return obj(fields)

    operation('/api/health', 'get', 'Process health', 'Operations', public=True, response=obj({'status': TEXT, 'country': TEXT}))
    operation('/api/ready', 'get', 'Check backend readiness', 'Operations', public=True, response=obj({'status': TEXT, 'inventory_loaded': {'type': 'boolean'}, 'engine_data_loaded': {'type': 'boolean'}}), description='Returns 503 until the engine tables and exact previous-day stock snapshot are available. A 503 readiness response uses this same readiness object, rather than the general error envelope.')
    paths['/api/ready']['get']['responses']['503'] = {'description': 'Not ready', 'content': {'application/json': {'schema': obj({'status': TEXT, 'inventory_loaded': {'type': 'boolean'}, 'engine_data_loaded': {'type': 'boolean'}})}}}
    operation('/api/me', 'get', 'Verified Clerk identity', 'Authentication', ref('Identity'))
    operation('/api/config', 'get', 'Safe operational configuration', 'Operations', description='Signed-in user. Does not expose secrets or allow settings changes.')
    operation('/api/status', 'get', 'Fallback and stock freshness status', 'Operations', description='Signed-in user. Reports manual fallback, engine readiness and inventory snapshot age.')
    operation('/api/fallback', 'put', 'Set manual fallback', 'Operations', ref('Fallback'), obj({'enabled': {'type': 'boolean'}, 'reason': {'type': 'string', 'minLength': 1, 'example': 'Maintenance'}}, ('enabled', 'reason')), description='Requires org:network_admin. Reason required when both enabling and clearing fallback.')
    operation('/api/operations/audit', 'get', 'Operational audit history', 'Audit', listing(ref('OperationalEvent')), parameters=PAGING, description='Requires org:network_admin.')
    operation('/api/facilities', 'get', 'Search facilities', 'Facilities', listing(ref('Facility')), parameters=PAGING + [param('q'), param('kind', schema={'type': 'string', 'enum': ['hospital', 'centre']})])
    operation('/api/facilities/{id}', 'get', 'Facility details', 'Facilities', ref('Facility'))
    operation('/api/facilities/{id}/inventory', 'get', 'Exact stock and reservations', 'Facilities', listing(ref('Inventory'), False), description='Own facility or network operator only. Engine RBC+WB counts never create actual RBC units.')
    operation('/api/requests', 'post', 'Create request and rank sources', 'Requests', ref('Request'), ref('CreateRequest'), status=201, description='Requester facility or network operator. Persists deterministic ranking, baseline and advice. No patient identifiers. Actual RBC fulfillment only; partial/whole-blood fulfillment requires the phone process.')
    operation('/api/rank', 'post', 'Preview ranking without storing', 'Requests', ref('Ranking'), ref('CreateRequest'), description='Requester facility or network operator. Same input as creating a request; returns the engine ranking and the canonical request but stores nothing and reserves no stock. Used for shareable result links.')
    operation('/api/requests', 'get', 'List visible requests', 'Requests', listing(ref('RequestSummary')), parameters=PAGING + [param('facility_id'), param('status'), param('created_after', schema=TIME), param('created_before', schema=TIME)])
    operation('/api/requests/{id}', 'get', 'Request status and allocations', 'Requests', ref('Request'), description='Requester, current supplier or network operator.')
    operation('/api/requests/{id}/options', 'get', 'Saved ranked source options', 'Requests', ref('Ranking'))
    operation('/api/requests/{id}/options/refresh', 'post', 'Refresh pending request options', 'Requests', ref('Ranking'), description='Requester/operator; only pending requests. Retains attempted-source history. No body required.')
    supplier_attempt = {'supplier_id': {**TEXT, 'example': 'RBTC-ELD'}, 'attempt': {'type': 'integer', 'minimum': 1, 'example': 1}}
    actions = {
        'pick': ('Select supplier and reserve stock', obj({'supplier_id': supplier_attempt['supplier_id']}, ('supplier_id',)), 'Requester/operator. Supplier must be ranked and unattempted, with current actual stock above safety reserves.'),
        'confirm': ('Confirm physical shelf stock', obj({**supplier_attempt, 'confirmed_units': {**UNITS, 'example': 2}}, ('supplier_id', 'attempt', 'confirmed_units')), 'Current supplier/operator. Full requested quantity and current attempt required before the deadline.'),
        'reject': ('Reject and try next source', obj({**supplier_attempt, 'reason': {**TEXT, 'example': 'Unavailable on shelf'}}, ('supplier_id', 'attempt', 'reason')), 'Current supplier/operator. Releases reservations and tries the next eligible ranked supplier.'),
        'dispatch': ('Dispatch confirmed units', obj(supplier_attempt, ('supplier_id', 'attempt')), 'Current supplier/operator. Requires confirmed state; consumes exact reserved stock.'),
        'cancel': ('Cancel before dispatch', obj({'reason': {**TEXT, 'example': 'Using phone process'}}, ('reason',)), 'Requester/operator. Releases reservations.'),
        'receive': ('Record receipt', obj({'received_units': {**UNITS, 'example': 2}}, ('received_units',)), 'Requester/operator. Quantity must match dispatch; discrepancies require the phone process.'),
    }
    for action, (summary, body_schema, description) in actions.items():
        operation('/api/requests/{id}/' + action, 'post', summary, 'Workflow', ref('Request'), body_schema, description=description)
    operation('/api/audit', 'get', 'Request audit history', 'Audit', listing(ref('AuditEvent')), parameters=PAGING + [param('request_id'), param('action')], description='Request participants must supply request_id. Network operators may read all events.')
    operation('/api/prealerts/runs', 'post', 'Generate a stock pre-alert assessment', 'Pre-alerts', ref('PrealertRun'), obj({'as_of': TIME}), status=201, description='Network operator. Send {} for operational clock; does not order replenishment.')
    operation('/api/prealerts/runs', 'get', 'List pre-alert runs', 'Pre-alerts', listing(obj({'id': TEXT, 'created_at': TIME})), parameters=PAGING, description='Network operator only.')
    operation('/api/prealerts/runs/{id}', 'get', 'Pre-alert assessment results', 'Pre-alerts', ref('PrealertRun'), description='Network operator only.')
    operation('/api/results', 'get', 'List derived replay/evaluation results', 'Results', listing(obj({'id': TEXT}), False), description='Network operator. Replay generation remains an offline CLI.')
    operation('/api/results/{id}', 'get', 'Read an allowlisted result artifact', 'Results', description='Network operator. IDs may contain an experiment prefix, e.g. hospital-reserve-5/replay_summary. Model internals and arbitrary files are not exposed.')
    operation('/api/sms', 'post', 'Signed inbound SMS commands', 'SMS', obj({'message_id': TEXT, 'request': ref('Request'), 'reply': TEXT}), ref('SMS'), public=True, status=201,
              parameters=[param('X-SMS-Timestamp', 'header', required=True, description='Unix seconds, within five minutes of real wall time.'), param('X-SMS-Signature', 'header', required=True, description='Hex HMAC-SHA256(secret, timestamp + "." + exact raw body).')],
              description='Registered sender and signed gateway envelope required. REQUEST <group> <units>, STATUS <id>, PICK <id> <supplier>, CONFIRM <id> <attempt> <units>, REJECT <id> <attempt> <reason>, DISPATCH <id> <attempt>. REQUEST returns 201; other commands return 200. This generic gateway sends the returned reply itself; Africa’s Talking uses its separate adapter.')
    paths['/api/sms']['post']['responses']['200'] = paths['/api/sms']['post']['responses']['201']
    for suffix, summary, schema in [
        ('inbound', 'Africa’s Talking inbound commands and queued replies', obj({'id': TEXT, 'from': TEXT, 'to': TEXT, 'text': TEXT}, ('id', 'from', 'to', 'text'))),
        ('delivery', 'Africa’s Talking delivery reports', obj({'id': TEXT, 'status': {'type': 'string', 'enum': ['Success', 'Failed', 'Rejected', 'Submitted', 'Buffered']}}, ('id', 'status'))),
    ]:
        path = '/api/sms/africastalking/' + suffix
        operation(path, 'post', summary, 'SMS', body=schema, public=True,
                  parameters=[param('token', 'query', required=True, description='Separate callback bearer secret; use HTTPS and redact query strings in proxy logs.')],
                  description='Provider callback, not a Clerk route. Accepts form encoding or JSON. Configure the exact callback URL with its token in the provider dashboard. Inbound requires an allowlisted service number and registered sender; duplicate message IDs do not repeat workflow actions or replies. Delivery reports never change a blood request.')
        paths[path]['post']['requestBody']['content']['application/x-www-form-urlencoded'] = {'schema': schema}
    return {
        'openapi': '3.0.3',
        'info': {'title': 'Blood Dispatch Network API', 'version': '1.0.0', 'description': 'Backend API for synthetic-data evaluation. Use Authorize for your Clerk Bearer token and supply a unique Idempotency-Key on mutations. A trained person crossmatches and releases every unit. Authentication, dataset and SMS configuration remain environment requirements.'},
        'servers': [{'url': '/', 'description': 'Current server'}],
        'security': [{'ClerkBearer': []}],
        'tags': [{'name': tag} for tag in ['Authentication', 'Operations', 'Facilities', 'Requests', 'Workflow', 'Audit', 'Pre-alerts', 'Results', 'SMS']],
        'paths': paths,
        'components': {'securitySchemes': {'ClerkBearer': {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT', 'description': 'Verified Clerk session token. Use the token only, without the Bearer prefix.'}}, 'schemas': schemas},
    }
