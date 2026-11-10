"""Isolated acceptance checks over a configured synthetic CSV dataset.

Uses temporary engine/workflow databases and an explicit local auth bypass. It does
not touch operational stock, call Clerk, send SMS, or claim live-identity validation.
"""
import copy
import csv
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import click

from .operations import copy_database


@contextmanager
def engine_environment(directory, database):
    previous = {key: os.environ.get(key) for key in ('DATA_DIR', 'ENGINE_DB_PATH')}
    os.environ.update(DATA_DIR=str(directory), ENGINE_DB_PATH=str(database))
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class VerificationError(ValueError):
    pass


def run_validation(directory, settings, facility_id=None, group='O+', units=1, as_of=None):
    from . import create_app
    directory = Path(directory).resolve()
    if as_of is None:
        with (directory / 'daily_stock.csv').open(newline='', encoding='utf-8-sig') as source:
            last = max(date.fromisoformat(row['date']) for row in csv.DictReader(source))
        as_of = datetime.combine(last + timedelta(days=1), time(1), ZoneInfo(settings['timezone']))
    if facility_id is None:
        with (directory / 'facilities.csv').open(newline='', encoding='utf-8-sig') as source:
            hospitals = sorted(row['facility_id'] for row in csv.DictReader(source) if row['facility_id'].startswith('HSP-'))
        if not hospitals:
            raise VerificationError('No hospital found in facilities.csv')
        facility_id = hospitals[0]
    settings = copy.deepcopy(settings)
    settings['demo_clock'] = as_of.isoformat()
    report = {'status': 'passed', 'clock': as_of.isoformat(), 'scenarios': {},
              'auth_mode': 'isolated local bypass; live Clerk accounts are NOT verified',
              'sms_delivery': 'not attempted'}
    with tempfile.TemporaryDirectory(prefix='blood-backend-validation-') as temporary:
        root = Path(temporary)
        with engine_environment(directory, root / 'engine.sqlite'):
            def new_app(path):
                return create_app(test_config={'TESTING': True, 'APP_ENV': 'development', 'AUTH_DISABLED': True,
                                               'DB_PATH': str(path), 'SETTINGS': copy.deepcopy(settings)})
            baseline = root / 'baseline.sqlite'
            app = new_app(baseline)
            with app.app_context():
                imported = app.test_cli_runner().invoke(args=['ingest-data'])
            if imported.exit_code:
                raise VerificationError('Dataset ingestion failed: ' + imported.output.strip())
            for scenario in ('dispatch_and_receive', 'supplier_rejection', 'confirmation_timeout'):
                database = root / (scenario + '.sqlite')
                copy_database(baseline, database)
                app = new_app(database)
                client = app.test_client()

                def call(path, payload, expected=200, key=None):
                    response = client.post('/api/' + path, json=payload, headers={'Idempotency-Key': key or str(uuid4())})
                    if response.status_code != expected:
                        message = response.get_json().get('error', {}).get('message', 'Unexpected response')
                        raise VerificationError(f'{scenario}: {path} returned {response.status_code}: {message}')
                    return response.get_json()

                created = call('requests', {'facility_id': facility_id, 'patient_group': group, 'units_needed': units}, 201)
                identifier = created['id']
                selected = None
                for option in created['ranking']['options']:
                    response = client.post(f'/api/requests/{identifier}/pick', json={'supplier_id': option['facility_id']}, headers={'Idempotency-Key': str(uuid4())})
                    if response.status_code == 200:
                        selected = response.get_json()
                        break
                if selected is None:
                    raise VerificationError(f'{scenario}: no ranked source has enough actual RBC stock; choose another facility/group/quantity')
                payload = {'supplier_id': selected['supplier_id'], 'attempt': selected['attempt']}
                path = f'requests/{identifier}'
                if scenario == 'dispatch_and_receive':
                    before = client.get(f"/api/facilities/{selected['supplier_id']}/inventory").get_json()['items']
                    call(path + '/confirm', {**payload, 'confirmed_units': units})
                    key = str(uuid4())
                    dispatched = call(path + '/dispatch', payload, key=key)
                    if dispatched['status'] != 'dispatched':
                        raise VerificationError('Dispatch did not enter dispatched state')
                    after = client.get(f"/api/facilities/{selected['supplier_id']}/inventory").get_json()['items']
                    allocation = {(item['blood_group'], item['product']): item['units'] for item in selected['allocations']}
                    starting = {(item['blood_group'], item['product']): item['on_hand'] for item in before}
                    for item in after:
                        stock_key = (item['blood_group'], item['product'])
                        if item['on_hand'] != starting[stock_key] - allocation.get(stock_key, 0):
                            raise VerificationError('Dispatch consumed an unexpected quantity')
                    call(path + '/dispatch', payload, key=key)
                    if client.get(f"/api/facilities/{selected['supplier_id']}/inventory").get_json()['items'] != after:
                        raise VerificationError('Dispatch retry changed inventory')
                    if call(path + '/receive', {'received_units': units})['status'] != 'received':
                        raise VerificationError('Receipt did not close the request')
                else:
                    if scenario == 'supplier_rejection':
                        updated = call(path + '/reject', {**payload, 'reason': 'Isolated backend verification'})
                    else:
                        minutes = settings['arrival']['confirmation_timeout_minutes'] + 1
                        app.config['SETTINGS']['demo_clock'] = (as_of + timedelta(minutes=minutes)).isoformat()
                        with app.app_context():
                            expired = app.test_cli_runner().invoke(args=['expire-confirmations'])
                        if expired.exit_code:
                            raise VerificationError('Confirmation expiry command failed')
                        updated = client.get('/api/' + path).get_json()
                    if updated['status'] != 'awaiting_confirmation' or updated['supplier_id'] == selected['supplier_id'] or updated['attempt'] != selected['attempt'] + 1:
                        raise VerificationError(f'{scenario}: no eligible backup source was selected; choose a dataset scenario with at least two full RBC suppliers')
                    call(path + '/confirm', {**payload, 'confirmed_units': units}, 409)
                    old_stock = client.get(f"/api/facilities/{selected['supplier_id']}/inventory").get_json()['items']
                    if any(item['reserved'] for item in old_stock):
                        raise VerificationError('Previous supplier reservation was not released')
                report['scenarios'][scenario] = 'passed'
    return report


def register(app):
    @app.cli.command('verify-workflow')
    @click.option('--data-dir', type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
    @click.option('--report', type=click.Path(path_type=Path), required=True)
    @click.option('--facility-id', default=None)
    @click.option('--group', default='O+', show_default=True)
    @click.option('--units', type=click.IntRange(1, 100), default=1, show_default=True)
    def verify(data_dir, report, facility_id, group, units):
        """Verify dispatch/receipt, rejection recovery and timeout recovery in temporary DBs."""
        if report.exists():
            raise click.ClickException('Report already exists; choose a new report path')
        try:
            from flask import current_app
            result = run_validation(data_dir, current_app.config['SETTINGS'], facility_id, group, units)
        except (ValueError, OSError, KeyError) as exc:
            raise click.ClickException(str(exc)) from exc
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('x', encoding='utf-8') as output:
            json.dump(result, output, indent=2)
        click.echo(json.dumps({'status': result['status'], 'report': str(report)}))
