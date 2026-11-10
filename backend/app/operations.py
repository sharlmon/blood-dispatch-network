"""Backend maintenance primitives; never send external messages or alter clinical rules."""
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import current_app

from .storage import atomic, get_db
from .workflow import now


def wall_now():
    return datetime.now(timezone.utc)


def prune_responses(days):
    """Compact old cached payloads; retain key/fingerprint tombstones to prevent repeats."""
    if type(days) is not int or days < 1:
        raise ValueError('Retention days must be an integer of at least 1')
    cutoff = (wall_now() - timedelta(days=days)).isoformat()
    with atomic() as db:
        changed = db.execute("UPDATE idempotency SET response='null' WHERE created_at<? AND response!='null'", (cutoff,)).rowcount
        if changed:
            audit_operation(db, 'idempotency_pruned', {'response_count': changed, 'retention_days': days})
    return changed


def audit_operation(db, action, payload):
    db.execute('INSERT INTO operational_audit(action,actor,payload,created_at) VALUES(?,?,?,?)',
               (action, '{"user_id":"system"}', json.dumps(payload), now().isoformat()))


def copy_database(source, destination):
    """SQLite online backup, verified and atomically published without overwriting files."""
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if not source.is_file():
        raise ValueError('Source database does not exist')
    if destination.exists() or destination.is_symlink():
        raise ValueError('Destination already exists; refusing to overwrite it')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.database-backup-', suffix='.sqlite', dir=destination.parent)
    os.close(fd)  # mkstemp creates a private (0600) file.
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as origin, closing(sqlite3.connect(temporary)) as target:
            if origin.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Source database failed integrity check')
            origin.backup(target)
            target.commit()
            target.execute('PRAGMA journal_mode=DELETE')
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Copied database failed integrity check')
            if target.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise ValueError('Copied database has foreign-key violations')
            if not target.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone():
                raise ValueError('Source is not a workflow database')
        # Same-directory hard link is atomic and fails if another process creates the destination.
        os.link(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(destination)


def _claim(name, key, stamp):
    token = str(uuid4())
    with atomic() as db:
        db.execute('INSERT OR IGNORE INTO scheduled_jobs(name,updated_at) VALUES(?,?)', (name, stamp.isoformat()))
        row = db.execute('SELECT * FROM scheduled_jobs WHERE name=?', (name,)).fetchone()
        if row['completed_key'] == key or (row['lease_until'] and row['lease_until'] > stamp.isoformat()):
            return None
        db.execute('UPDATE scheduled_jobs SET lease_token=?,lease_until=?,updated_at=? WHERE name=?',
                   (token, (stamp + timedelta(minutes=15)).isoformat(), stamp.isoformat(), name))
    return token


def _run_job(name, key, stamp, action):
    token = _claim(name, key, stamp)
    if token is None:
        return 'skipped'
    try:
        # The action and success checkpoint commit together. An abandoned lease can be retried.
        with atomic() as db:
            row = db.execute('SELECT lease_token FROM scheduled_jobs WHERE name=?', (name,)).fetchone()
            if row['lease_token'] != token:
                return 'skipped'
            action()
            db.execute('UPDATE scheduled_jobs SET completed_key=?,lease_token=NULL,lease_until=NULL,last_error=NULL,updated_at=? WHERE name=? AND lease_token=?',
                       (key, wall_now().isoformat(), name, token))
        return 'completed'
    except Exception as exc:
        current_app.logger.error('maintenance_failed job=%s error_type=%s', name, type(exc).__name__)
        with atomic() as db:
            # Store the error class only; exceptions may contain data paths or credentials.
            db.execute('UPDATE scheduled_jobs SET lease_token=NULL,lease_until=?,last_error=?,updated_at=? WHERE name=? AND lease_token=?',
                       ((wall_now() + timedelta(minutes=1)).isoformat(), type(exc).__name__, wall_now().isoformat(), name, token))
        return 'failed'


def maintenance_tick():
    """One scheduler pass. Safe to invoke every minute and from multiple processes."""
    from .services import save_prealert
    from .workflow import expire
    stamp = wall_now()
    result = {'expiry': _run_job('expiry', stamp.strftime('%Y-%m-%dT%H:%M'), stamp, expire)}
    local = now().astimezone(ZoneInfo(current_app.config['SETTINGS']['timezone']))
    prealert = current_app.config['SETTINGS'].get('prealert', {})
    hour = prealert.get('run_hour', 18)
    if local.hour >= hour:
        result['prealerts'] = _run_job('prealerts', local.date().isoformat(), stamp, lambda: save_prealert(now()))
    result['retention'] = _run_job('retention', stamp.date().isoformat(), stamp,
                                    lambda: prune_responses(current_app.config['IDEMPOTENCY_RETENTION_DAYS']))
    return result
