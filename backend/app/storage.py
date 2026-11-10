import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS facilities (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('hospital','centre'))
);
CREATE TABLE IF NOT EXISTS facility_metadata (
 facility_id TEXT PRIMARY KEY REFERENCES facilities(id), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory (
 facility_id TEXT NOT NULL REFERENCES facilities(id), blood_group TEXT NOT NULL,
 product TEXT NOT NULL, on_hand INTEGER NOT NULL CHECK(on_hand >= 0),
 reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0 AND reserved <= on_hand),
 safety_stock INTEGER NOT NULL DEFAULT 0 CHECK(safety_stock >= 0),
 updated_at TEXT NOT NULL, PRIMARY KEY(facility_id,blood_group,product)
);
CREATE TABLE IF NOT EXISTS requests (
 id TEXT PRIMARY KEY, facility_id TEXT NOT NULL REFERENCES facilities(id),
 blood_group TEXT NOT NULL, product TEXT NOT NULL, units INTEGER NOT NULL CHECK(units > 0),
 status TEXT NOT NULL, supplier_id TEXT REFERENCES facilities(id),
 attempt INTEGER NOT NULL DEFAULT 0, deadline TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS request_metadata (
 request_id TEXT PRIMARY KEY REFERENCES requests(id), payload TEXT NOT NULL,
 ranking TEXT NOT NULL, selected_option TEXT, attempted_sources TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS allocations (
 request_id TEXT NOT NULL REFERENCES requests(id), facility_id TEXT NOT NULL,
 blood_group TEXT NOT NULL, product TEXT NOT NULL, units INTEGER NOT NULL CHECK(units > 0),
 PRIMARY KEY(request_id,blood_group,product)
);
CREATE TABLE IF NOT EXISTS idempotency (
 actor TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL,
 response TEXT NOT NULL, status INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(actor,key)
);
CREATE TABLE IF NOT EXISTS schema_migrations (
 version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scheduled_jobs (
 name TEXT PRIMARY KEY, completed_key TEXT, lease_token TEXT, lease_until TEXT,
 last_error TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
 key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operational_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, actor TEXT NOT NULL,
 payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prealert_runs (
 id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL REFERENCES requests(id),
 action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


def get_db():
    if 'db' not in g:
        path = current_app.config['DB_PATH']
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(path, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def init_app(app):
    @app.teardown_appcontext
    def close_db(error=None):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    with app.app_context():
        db = get_db()
        if app.config['DB_PATH'] != ':memory:':
            db.execute('PRAGMA journal_mode=WAL')
        try:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
            columns = {row['name'] for row in db.execute('PRAGMA table_info(idempotency)')}
            if 'created_at' not in columns:
                db.execute('ALTER TABLE idempotency ADD COLUMN created_at TEXT')
            stamp = datetime.now(timezone.utc).isoformat()
            db.execute('UPDATE idempotency SET created_at=? WHERE created_at IS NULL', (stamp,))
            db.execute('CREATE INDEX IF NOT EXISTS idx_idempotency_created ON idempotency(created_at)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_requests_facility ON requests(facility_id,status,created_at)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_requests_supplier ON requests(supplier_id,status)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_confirmation_deadline ON requests(status,deadline)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_audit_request ON audit(request_id,id)')
            db.execute('INSERT OR IGNORE INTO schema_migrations VALUES(1,?)', (stamp,))
            db.commit()
        except Exception:
            db.rollback()
            raise


@contextmanager
def atomic(db=None):
    db = db or get_db()
    nested = db.in_transaction
    if not nested:
        db.execute('BEGIN IMMEDIATE')
    try:
        yield db
        if not nested:
            db.commit()
    except Exception:
        if not nested:
            db.rollback()
        raise
