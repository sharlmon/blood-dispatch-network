"""Shared fixtures.

Tests marked with the ``real_data`` fixture need ``DATA_DIR`` pointing at the
starter-kit CSVs. They build a fresh SQLite file once per test session in a
temp folder, so they never touch the real ``blood.db``.
"""

from __future__ import annotations

import pytest

from engine import config
from engine.load import build_db, load_frames


@pytest.fixture(scope="session")
def data_dir():
    try:
        return config.data_dir()
    except config.ConfigError as exc:
        pytest.skip(f"real-data test skipped: {exc}")


@pytest.fixture(scope="session")
def built_db(data_dir, tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "blood.db"
    counts = build_db(data_dir, db)
    return db, counts


@pytest.fixture(scope="session")
def frames(built_db):
    db, _ = built_db
    return load_frames(db)
