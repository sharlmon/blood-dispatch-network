"""Organization-to-facility authorization; mappings are configured server-side."""
from flask import current_app, g

from .workflow import APIError


def is_operator():
    if getattr(g, 'sms_facility_id', None):
        return False
    return current_app.config.get('AUTH_DISABLED', False) or (
        getattr(g, 'auth', None) is not None and g.auth.org_role == 'org:network_admin'
    )


def caller_facility():
    if getattr(g, 'sms_facility_id', None):
        return g.sms_facility_id
    ctx = getattr(g, 'auth', None)
    facility_id = current_app.config['ORG_FACILITY_MAP'].get(ctx.org_id) if ctx else None
    if not facility_id:
        raise APIError('Organization has no configured facility mapping', 403)
    return facility_id


def require_facility(identifier):
    if not is_operator() and caller_facility() != identifier:
        raise APIError('This action belongs to another facility', 403)


def require_operator():
    if not is_operator():
        raise APIError('Network operator role required', 403)


def can_read(row):
    if not is_operator() and caller_facility() not in {row['facility_id'], row['supplier_id']}:
        raise APIError('Request belongs to another facility', 403)
