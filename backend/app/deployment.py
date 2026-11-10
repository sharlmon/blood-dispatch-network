"""Configuration validation shared by startup and operational checks."""
from pathlib import Path


def production_errors(app):
    errors = []
    if app.config.get('AUTH_DISABLED'):
        errors.append('AUTH_DISABLED must be off in production')
    if app.extensions.get('clerk_verifier') is None:
        errors.append('Configure a Clerk issuer or publishable key')
    if not app.config['ORG_FACILITY_MAP']:
        errors.append('Configure ORG_FACILITY_MAP for requester and supplier organizations')
    path = app.config['DB_PATH']
    if path == ':memory:' or not Path(path).is_absolute():
        errors.append('Production DB_PATH must be an absolute persistent file path')
    if app.config['SMS_SENDERS'] and len(app.config.get('SMS_WEBHOOK_SECRET') or '') < 32:
        errors.append('Registered SMS senders require SMS_WEBHOOK_SECRET with at least 32 characters')
    if app.debug:
        errors.append('Debug mode must be disabled in production')
    return errors
