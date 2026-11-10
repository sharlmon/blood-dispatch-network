"""Shared fixtures.

Tests marked with the ``real_data`` fixture need ``DATA_DIR`` pointing at the
starter-kit CSVs. They build a fresh SQLite file once per test session in a
temp folder, so they never touch the real ``blood.db``.
"""

from __future__ import annotations

import pytest

from engine import config
from engine.load import build_db, load_frames


@pytest.fixture(autouse=True)
def isolate_sms_configuration(monkeypatch):
    """Private developer SMS settings must never enable external test traffic."""
    monkeypatch.setenv('SMS_ENABLED', '0')
    monkeypatch.setenv('SMS_ENVIRONMENT', 'sandbox')
    monkeypatch.setenv('SMS_SENDERS', '{}')
    monkeypatch.setenv('SMS_FACILITY_CONTACTS', '{}')
    monkeypatch.setenv('AFRICASTALKING_INBOUND_NUMBERS', '[]')
    for key in ('SMS_WEBHOOK_SECRET', 'AFRICASTALKING_CALLBACK_TOKEN',
                'AFRICASTALKING_USERNAME', 'AFRICASTALKING_API_KEY',
                'AFRICASTALKING_SANDBOX_API_KEY', 'AFRICASTALKING_SENDER_ID',
                'AFRICASTALKING_SANDBOX_SENDER_ID'):
        monkeypatch.delenv(key, raising=False)


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


@pytest.fixture(scope="session")
def eta_model(frames, tmp_path_factory):
    """The real arrival model, fitted once, saved and loaded back as production does."""
    from engine import eta

    model, _ = eta.fit(frames, config.load_config("kenya")["eta_train_before"])
    path = tmp_path_factory.mktemp("eta") / "eta_model.json"
    eta.save_json(model, path)
    loaded = eta.load_model(path)
    assert loaded.model_used
    return loaded
