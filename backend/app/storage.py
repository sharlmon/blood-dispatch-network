import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS facilities (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('hospital','centre'))
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
        get_db().executescript(SCHEMA)
