"""Shared fixtures.

Tests marked with the ``real_data`` fixture need ``DATA_DIR`` pointing at the
starter-kit CSVs. They build a fresh SQLite file once per test session in a
temp folder, so they never touch the real ``blood.db``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from engine import config
from engine.load import build_db, load_frames

# Tests never start the API's background engine warm-up (read by app.create_app).
os.environ["ENGINE_WARMUP"] = "0"


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


# --------------------------------------------------------------------------- API (Flask)
# A tiny in-memory engine and a temp SQLite store: API tests need no DATA_DIR and no network.

API_SETTINGS = Path(__file__).resolve().parents[1] / "config" / "settings.default.yaml"
API_DAY_BEFORE = "2026-03-09"  # stock day for requests on 2026-03-10
API_FACILITIES = [
    # id, name, type, supply centre, backup power, connectivity, county, lat, lon
    ("RBTC-A", "Centre A", "regional_blood_centre", None, True, "4G", "Nairobi", -1.29, 36.82),
    ("RBTC-B", "Centre B", "regional_blood_centre", None, True, "4G", "Nakuru", -0.30, 36.07),
    ("HSP-R", "Requesting Hospital", "county_referral", "RBTC-A", True, "4G", "Kiambu", -1.17, 36.83),
    ("HSP-B", "Lending Hospital", "county_referral", "RBTC-A", True, "4G", "Nairobi", -1.30, 36.80),
    ("HSP-C", "Remote Hospital", "county_hospital", "RBTC-A", False, "2G", "Garissa", -0.45, 39.65),
    ("SAT-S", "Satellite", "satellite_blood_centre", "RBTC-A", True, "3G", None, None, None),
]
API_ROUTES = [("RBTC-A", 2.0, 100), ("RBTC-B", 4.0, 200), ("HSP-B", 1.0, 40), ("HSP-C", 0.5, 20),
              ("SAT-S", 0.2, 5)]  # (from, map hours to HSP-R, road km to HSP-R)
API_STOCK = [("RBTC-A", "O+", 5), ("RBTC-A", "O-", 2), ("RBTC-B", "O+", 5), ("HSP-B", "O+", 9),
             ("HSP-C", "A+", 3)]  # (facility, group, units) at the close of API_DAY_BEFORE


@pytest.fixture
def api_frames():
    """Two centres, three hospitals and a satellite. HSP-R is the requester."""
    import pandas as pd

    from engine.load import frames_from_tables

    facilities = pd.DataFrame(API_FACILITIES, columns=[
        "facility_id", "name", "facility_type", "supply_centre_id", "has_blood_fridge_backup_power",
        "connectivity", "county", "lat", "lon"])
    routes = pd.DataFrame([(a, "HSP-R", km, h) for a, h, km in API_ROUTES],
                          columns=["from_facility_id", "to_facility_id", "road_km", "typical_travel_hours"])
    red_stock = pd.DataFrame([(API_DAY_BEFORE, f, g, n) for f, g, n in API_STOCK],
                             columns=["date", "facility_id", "blood_group", "units"])
    usual = pd.DataFrame([], columns=["facility_id", "blood_group", "usual_level"])
    units = pd.DataFrame([], columns=["component", "current_facility_id", "blood_group",
                                      "collection_date", "expiry_date", "status_date"])
    return frames_from_tables(facilities, routes, units, red_stock, usual)


@pytest.fixture
def api_eta():
    """Flat arrival model: wait 2 h, road ratio 1, so p10 = p50 = p90 = 2 h + map time."""
    from engine import eta

    return eta.EtaModel.from_dict({"wait_h": [2.0], "ratio": [1.0]})


@pytest.fixture
def api_engine(api_frames, api_eta):
    """An EngineService that is ready at once, with no disk access."""
    from app.engine_service import EngineService

    return EngineService(config=config.load_config("kenya"), frames=api_frames, eta_model=api_eta)


class _TokenSessions:
    """Stands in for Clerk: the bearer token "user:org:role" is the verified session."""

    def verify(self, token):
        from app.clerk_auth import AuthContext

        user, _, rest = token.partition(":")
        org, _, role = rest.partition(":")
        return AuthContext(user_id=user, session_id=None, org_id=org or None, org_role=role or None)


@pytest.fixture
def make_api_app(monkeypatch, tmp_path):
    """Build the Flask app around an injected engine, with a fresh store in tmp_path.

    auth: "disabled" (AUTH_DISABLED=1: user_demo in org_demo), "tokens" (bearer
    "user:org:role"), or "unconfigured" (no Clerk and no AUTH_DISABLED).
    """
    from app import create_app
    from workflow.store import Store

    for var in ("DEMO_CLOCK", "RESULTS_DIR", "CORS_ORIGINS", "ENGINE_COUNTRY"):
        monkeypatch.delenv(var, raising=False)

    def make(engine, *, auth="disabled", settings_path=API_SETTINGS, store=None):
        for var in ("AUTH_DISABLED", "CLERK_ISSUER", "CLERK_PUBLISHABLE_KEY"):
            monkeypatch.delenv(var, raising=False)
        if auth == "disabled":
            monkeypatch.setenv("AUTH_DISABLED", "1")
        elif auth == "tokens":
            monkeypatch.setenv("CLERK_ISSUER", "https://example-app-12.clerk.accounts.dev")
        app = create_app(str(settings_path), engine=engine, store=store or Store(tmp_path / "api.sqlite"))
        if auth == "tokens":
            app.extensions["clerk_verifier"] = _TokenSessions()
        return app

    return make


@pytest.fixture
def api_app(make_api_app, api_engine):
    return make_api_app(api_engine)


@pytest.fixture
def api_client(api_app):
    return api_app.test_client()
