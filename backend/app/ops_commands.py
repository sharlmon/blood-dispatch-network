"""Local-only operational commands. No credentials or external messages are printed."""
import json
import signal
import sqlite3
import threading
from pathlib import Path
from uuid import uuid4

import click
from flask import current_app

from .operations import copy_database, maintenance_tick, prune_responses


def register(app):
    @app.cli.command('sms-worker')
    @click.option('--once', is_flag=True)
    @click.option('--interval', type=click.IntRange(1, 60), default=10)
    def sms_worker(once, interval):
        """Send committed queued SMS; never automatically retry failures or unknown sends."""
        from .sms_provider import drain
        stopped = threading.Event()
        previous = {}
        if not once:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, lambda *args: stopped.set())
        try:
            while not stopped.is_set():
                click.echo(json.dumps(drain()))
                if once:
                    break
                stopped.wait(interval)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    @app.cli.command('sms-status')
    def sms_status():
        """Show queue health without phone numbers, message bodies or credentials."""
        from .storage import get_db
        rows = get_db().execute('SELECT environment,status,COUNT(*) AS count FROM sms_outbox GROUP BY environment,status')
        click.echo(json.dumps([dict(row) for row in rows]))

    @app.cli.command('sms-retry')
    @click.argument('identifier')
    def sms_retry(identifier):
        """Requeue a definite send rejection after fixing its cause; refuses uncertain sends."""
        from .storage import atomic
        from .sms_provider import stamp
        with atomic() as db:
            changed = db.execute("UPDATE sms_outbox SET status='queued',error_code=NULL,updated_at=? WHERE id=? AND status='failed' AND environment=?",
                                 (stamp(), identifier, current_app.config['SMS_ENVIRONMENT'])).rowcount
            if not changed:
                raise click.ClickException('Only definite send rejections in the selected environment can be requeued')
        click.echo(json.dumps({'requeued': identifier}))

    @app.cli.command('maintenance')
    @click.option('--once', is_flag=True, help='Run a single scheduler pass and exit.')
    @click.option('--interval', type=click.IntRange(1, 60), default=30, show_default=True)
    def maintenance(once, interval):
        """Expire confirmations, generate evening pre-alerts and compact retry responses."""
        stopped = threading.Event()
        previous = {}
        if not once:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, lambda *args: stopped.set())
        try:
            while not stopped.is_set():
                result = maintenance_tick()
                click.echo(json.dumps(result))
                if once:
                    if 'failed' in result.values():
                        raise click.ClickException('One or more maintenance jobs failed; inspect backend logs')
                    break
                stopped.wait(interval)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    @app.cli.command('prune-idempotency')
    @click.option('--older-than-days', type=click.IntRange(1), default=30, show_default=True)
    def prune(older_than_days):
        """Remove old response payloads but retain retry-key tombstones."""
        click.echo(json.dumps({'compacted_responses': prune_responses(older_than_days)}))

    @app.cli.command('backup-db')
    @click.option('--output', type=click.Path(path_type=Path))
    @click.option('--directory', type=click.Path(path_type=Path), help='Generate a unique backup filename in this folder.')
    def backup(output, directory):
        """Create a consistent, verified SQLite backup; refuses existing destinations."""
        if (output is None) == (directory is None):
            raise click.UsageError('Specify exactly one of --output or --directory')
        if directory is not None:
            from .operations import wall_now
            output = directory / ('workflow-' + wall_now().strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8] + '.sqlite')
        try:
            path = copy_database(current_app.config['DB_PATH'], output)
        except (ValueError, OSError, sqlite3.Error) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(json.dumps({'backup': path}))

    @app.cli.command('restore-db')
    @click.argument('backup', type=click.Path(exists=True, path_type=Path))
    @click.option('--output', type=click.Path(path_type=Path), required=True)
    def restore(backup, output):
        """Restore into a NEW database file; never overwrite the running database."""
        try:
            path = copy_database(backup, output)
        except (ValueError, OSError, sqlite3.Error) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(json.dumps({'restored_database': path}))

    @app.cli.command('check-config')
    def check():
        """Report deployment prerequisites without printing secrets or mappings."""
        from .deployment import production_errors
        from .services import engine_ready
        errors = production_errors(current_app)
        data_ready = engine_ready()
        result = {'production_configuration_ok': not errors, 'errors': errors,
                  'engine_ready': data_ready, 'facility_mapping_count': len(current_app.config['ORG_FACILITY_MAP']),
                  'sms_configured': bool(current_app.config['SMS_WEBHOOK_SECRET'] and current_app.config['SMS_SENDERS']),
                  'sms_outbound_enabled': current_app.config['SMS_ENABLED'],
                  'sms_environment': current_app.config['SMS_ENVIRONMENT'],
                  'sms_callbacks_configured': bool(current_app.config['AFRICASTALKING_CALLBACK_TOKEN']),
                  'sms_sender_count': len(current_app.config['SMS_SENDERS']),
                  'sms_contact_facility_count': len(current_app.config['SMS_FACILITY_CONTACTS'])}
        click.echo(json.dumps(result))
        if errors or not data_ready:
            raise click.ClickException('Deployment prerequisites are incomplete')
