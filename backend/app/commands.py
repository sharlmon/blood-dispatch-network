import click

from .storage import get_db
from .workflow import now


def register(app):
    @app.cli.command('seed-demo')
    def seed_demo():
        """Insert clearly labelled synthetic facilities and inventory into an empty DB."""
        db = get_db()
        with db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT EXISTS(SELECT 1 FROM facilities)').fetchone()[0]:
                raise click.ClickException('Database already has facilities; refusing to overwrite data.')
            db.executemany('INSERT INTO facilities VALUES(?,?,?)', [
                ('DEMO-H1', 'Synthetic Demo Hospital', 'hospital'),
                ('DEMO-C1', 'Synthetic Demo Centre', 'centre'),
            ])
            db.execute('INSERT INTO inventory VALUES(?,?,?,?,?,?,?)',
                       ('DEMO-C1', 'A+', 'red_cells', 10, 0, 2, now().isoformat()))
        click.echo('Inserted synthetic DEMO-H1 and DEMO-C1; no real facility data used.')


def register_ingest(app):
    @app.cli.command('ingest-data')
    def ingest_data():
        """Validate/build the engine DB and synchronize yesterday's stock."""
        import json
        import sqlite3
        from datetime import timedelta
        from pathlib import Path
        from zoneinfo import ZoneInfo
        from flask import current_app
        from engine.config import data_dir, db_path, ConfigError
        from engine.load import build_db, load_frames
        from .storage import atomic
        from .workflow import now

        try:
            engine_path = db_path()
        except ConfigError as exc:
            raise click.ClickException(str(exc)) from exc
        if engine_path.resolve() == Path(current_app.config['DB_PATH']).resolve():
            raise click.ClickException('ENGINE_DB_PATH and DB_PATH must be different files.')
        day = (now().astimezone(ZoneInfo(current_app.config['SETTINGS']['timezone'])).date() - timedelta(days=1)).isoformat()
        db = get_db()
        def check():
            if db.execute('SELECT EXISTS(SELECT 1 FROM inventory WHERE reserved>0)').fetchone()[0]:
                raise click.ClickException('Resolve active reservations before importing a snapshot.')
            latest = db.execute('SELECT MAX(updated_at) FROM inventory').fetchone()[0]
            if latest and latest[:10] >= day:
                raise click.ClickException('Snapshot already imported or newer inventory exists; refusing to reset consumed stock.')
        check()
        try:
            counts = build_db(data_dir(), engine_path)
            frames = load_frames(engine_path)
            with sqlite3.connect(engine_path) as source:
                source.row_factory = sqlite3.Row
                stocks = source.execute("SELECT facility_id,blood_group,component,units_in_stock_end_of_day FROM daily_stock WHERE date=? AND component IN ('RBC','WB')", (day,)).fetchall()
            if not stocks:
                raise click.ClickException(f'No previous-day stock for {day}; set demo_clock for historical data.')
            cfg = current_app.config['ENGINE_CONFIG']
            with atomic(db):
                check()
                for identifier, item in frames.facility_info.items():
                    kind = 'centre' if item['facility_type'] == 'regional_blood_centre' else 'hospital'
                    db.execute('INSERT INTO facilities VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,kind=excluded.kind',
                               (identifier, item.get('name') or item.get('facility_name') or identifier, kind))
                    db.execute('INSERT INTO facility_metadata VALUES(?,?) ON CONFLICT(facility_id) DO UPDATE SET payload=excluded.payload', (identifier, json.dumps(item)))
                db.execute('UPDATE inventory SET on_hand=0,reserved=0')
                for item in stocks:
                    identifier, group = item['facility_id'], item['blood_group']
                    is_centre = frames.facility_info[identifier]['facility_type'] == 'regional_blood_centre'
                    reserve = 0 if is_centre else max(cfg['min_keep'], frames.usual_level.get((identifier, group), 0), cfg['o_neg_reserve'] if group == 'O-' else 0)
                    product = 'red_cells' if item['component'] == 'RBC' else 'whole_blood'
                    raw_units = item['units_in_stock_end_of_day']
                    units = int(raw_units)
                    if raw_units != units:
                        raise click.ClickException('Stock counts must be nonnegative whole units.')
                    db.execute('INSERT INTO inventory VALUES(?,?,?,?,0,?,?) ON CONFLICT(facility_id,blood_group,product) DO UPDATE SET on_hand=excluded.on_hand,reserved=0,safety_stock=excluded.safety_stock,updated_at=excluded.updated_at',
                               (identifier, group, product, units, reserve, day + 'T23:59:59+03:00'))
                db.execute('INSERT INTO operational_audit(action,actor,payload,created_at) VALUES(?,?,?,?)',
                           ('inventory_imported', '{"user_id":"system"}', json.dumps({'stock_as_of': day, 'rows': len(stocks)}), now().isoformat()))
            click.echo(json.dumps({'engine_counts': counts, 'stock_as_of': day, 'inventory_rows': len(stocks)}))
        except (ValueError, OSError, RuntimeError, KeyError, TypeError, sqlite3.Error) as exc:
            raise click.ClickException(str(exc)) from exc


def register_prealerts(app):
    @app.cli.command('run-prealerts')
    @click.option('--as-of', default=None, help='ISO timestamp with timezone; defaults to the operational clock.')
    def run_prealerts(as_of):
        """Generate/persist the same assessment as the operator endpoint."""
        import json
        from .services import save_prealert
        from .workflow import APIError, timestamp
        try:
            result = save_prealert(timestamp(as_of) if as_of else now())
        except APIError as exc:
            raise click.ClickException(exc.message) from exc
        click.echo(json.dumps(result))
