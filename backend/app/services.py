"""Adapters for the existing deterministic engine and operational services."""
import json
import sqlite3
from pathlib import Path

from pandas.errors import DatabaseError as FrameDatabaseError

from flask import current_app

from .storage import get_db, atomic
from .workflow import APIError, now


def ranking(payload):
    adapter = current_app.config.get('RANKING_PROVIDER')
    if adapter:
        return adapter(payload)
    try:
        from engine.config import ConfigError
        from engine.rank import rank_sources
        return rank_sources(payload, config={**current_app.config['ENGINE_CONFIG'], 'clinician_limit_h': payload['clinician_limit_h']})
    except ValueError as exc:
        raise APIError(str(exc)) from exc
    except (ConfigError, FileNotFoundError, OSError, sqlite3.Error, FrameDatabaseError, KeyError) as exc:
        current_app.logger.warning('Ranking unavailable: %s', exc)
        raise APIError('Ranking data unavailable; use the phone process', 503) from exc


def fallback():
    row = get_db().execute("SELECT value FROM operations WHERE key='fallback'").fetchone()
    return json.loads(row['value']) if row else {'enabled': False, 'reason': None, 'updated_at': None}


def ensure_available():
    if fallback()['enabled']:
        raise APIError('Manual fallback enabled; use the phone process', 503)


def set_fallback(enabled, reason):
    with atomic() as db:
        value = dict(enabled=enabled, reason=reason, updated_at=now().isoformat())
        db.execute("INSERT INTO operations VALUES('fallback',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(value),))
    return value


def prealerts(as_of):
    adapter = current_app.config.get('PREALERT_PROVIDER')
    if adapter:
        return adapter(as_of)
    try:
        from engine.dataset import Dataset, DatasetError
        from engine.config import data_dir, ConfigError
        from engine.prealert import generate_prealerts
        dataset = Dataset.load(data_dir())
        return generate_prealerts(dataset.stock, dataset.facilities, as_of=as_of, settings=current_app.config['SETTINGS'])
    except (ConfigError, DatasetError, FileNotFoundError, OSError, sqlite3.Error, FrameDatabaseError, KeyError, ValueError) as exc:
        current_app.logger.warning('Pre-alert data unavailable: %s', exc)
        raise APIError('Pre-alert dataset unavailable', 503) from exc


def result_files():
    root = Path(current_app.config['RESULTS_DIR']).resolve()
    # Only derived public outputs; never expose arbitrary JSON, raw rows or model internals.
    names = {'summary.json', 'replay_summary.json', 'arrival_validation.json',
             'prealert_evaluation.json', 'data_quality.json', 'prealerts.json'}
    return {p.relative_to(root).as_posix().removesuffix('.json'): p
            for p in root.rglob('*.json') if p.name in names and p.resolve().is_relative_to(root)}


def save_prealert(as_of):
    from uuid import uuid4
    from flask import g, has_request_context
    result = prealerts(as_of)
    identifier, stamp = str(uuid4()), now().isoformat()
    with atomic() as db:
        db.execute('INSERT INTO prealert_runs VALUES(?,?,?)', (identifier, stamp, json.dumps(result)))
        actor = g.auth.public() if has_request_context() and getattr(g, 'auth', None) else {'user_id': 'system'}
        db.execute('INSERT INTO operational_audit(action,actor,payload,created_at) VALUES(?,?,?,?)',
                   ('prealerts_generated', json.dumps(actor), json.dumps({'run_id': identifier}), stamp))
    return {'id': identifier, 'created_at': stamp, 'result': result}


def warm_engine():
    """Load the existing engine cache before requests acquire the workflow write lock."""
    try:
        from engine.config import db_path, data_dir, eta_model_path, ConfigError
        from engine.load import load_frames
        from engine.eta import load_model
        data_dir()
        load_frames(db_path())
        load_model(eta_model_path())
    except (ConfigError, OSError, sqlite3.Error, FrameDatabaseError, KeyError, ValueError) as exc:
        current_app.logger.warning('Engine startup warmup unavailable: %s', exc)


def snapshot_day():
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    return (now().astimezone(ZoneInfo(current_app.config['SETTINGS']['timezone'])).date() - timedelta(days=1)).isoformat()


def engine_ready():
    """Read-only probe: an existing but corrupt/stale engine file is not ready."""
    from engine.config import db_path, ConfigError
    try:
        path = db_path().resolve()
        if not path.is_file():
            return False
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            for table in ('facilities', 'routes', 'units', 'transfers', 'requests', 'usual_level'):
                db.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone()
            return db.execute('SELECT EXISTS(SELECT 1 FROM red_stock WHERE date=?)', (snapshot_day(),)).fetchone()[0] == 1
    except (ConfigError, OSError, sqlite3.Error):
        return False
