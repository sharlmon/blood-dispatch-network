"""Step 1: CSV -> SQLite, usual_level, stock lookup, config."""

from __future__ import annotations

import sqlite3
import time

import pandas as pd
import pytest

from engine import config
from engine.load import (
    BLOOD_GROUPS,
    CSV_TABLES,
    DataError,
    REQUEST_COLUMNS,
    StockLookup,
    build_db,
    read_csvs,
    red_stock_frame,
    usual_level_frame,
    validate,
)

# --------------------------------------------------------------------------- unit tests (no data)


def _stock(rows):
    return pd.DataFrame(
        rows, columns=["date", "facility_id", "component", "blood_group", "units_in_stock_end_of_day"]
    )


def test_red_stock_sums_rbc_and_wb_and_ignores_other_components():
    ds = _stock(
        [
            ("2026-01-01", "HSP-1", "RBC", "O+", 3),
            ("2026-01-01", "HSP-1", "WB", "O+", 2),
            ("2026-01-01", "HSP-1", "PLT", "O+", 50),
            ("2026-01-01", "HSP-1", "FFP", "O+", 50),
        ]
    )
    out = red_stock_frame(ds)
    assert out.to_dict("records") == [
        {"date": "2026-01-01", "facility_id": "HSP-1", "blood_group": "O+", "units": 5}
    ]


def test_usual_level_is_median_including_zero_days():
    ds = _stock([(f"2026-01-0{d}", "HSP-1", "RBC", "O+", u) for d, u in enumerate([0, 0, 7], 1)])
    out = usual_level_frame(red_stock_frame(ds))
    assert out.loc[0, "usual_level"] == 0


def test_usual_level_rounds_an_even_median_up():
    ds = _stock([(f"2026-01-0{d}", "HSP-1", "RBC", "O+", u) for d, u in enumerate([2, 3], 1)])
    assert usual_level_frame(red_stock_frame(ds)).loc[0, "usual_level"] == 3


def test_stock_lookup_returns_zero_for_missing_combinations():
    lookup = StockLookup(
        pd.DataFrame([{"date": "2026-01-01", "facility_id": "HSP-1", "blood_group": "O+", "units": 4}])
    )
    assert lookup.units("2026-01-01", "HSP-1", "O+") == 4
    assert lookup.units("2026-01-01", "HSP-1", "AB-") == 0
    assert lookup.units("2026-01-02", "HSP-1", "O+") == 0
    assert lookup.groups("2026-01-01", "HSP-1") == {g: (4 if g == "O+" else 0) for g in BLOOD_GROUPS}


# --------------------------------------------------------------------------- config


def test_kenya_config_matches_spec():
    cfg = config.load_config("kenya")
    assert cfg["sharing_allowed"] is True
    assert cfg["min_keep"] == 2
    assert cfg["o_neg_reserve"] == 2
    assert cfg["near_expiry_days"] == 10
    assert cfg["hospital_extra_dispatch_h"] == 0.0
    assert cfg["clinician_limit_h"] == 6.0
    assert cfg["baseline_quote_extra_h"] == 2.0
    assert cfg["eta_train_before"] == "2026-07-01"


def test_config_rejects_wrong_types(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("sharing_allowed: maybe\n")
    with pytest.raises(config.ConfigError, match="sharing_allowed"):
        config.load_config(path=bad)


def test_missing_data_dir_gives_a_clear_error(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    with pytest.raises(config.ConfigError, match="DATA_DIR is not set"):
        config.data_dir()


def test_db_path_defaults_to_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ENGINE_DB_PATH", raising=False)
    assert config.db_path() == tmp_path / "blood.db"


# --------------------------------------------------------------------------- real data


def test_db_has_every_table_with_csv_row_counts(built_db, data_dir):
    db, counts = built_db
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert set(CSV_TABLES) | {"red_stock", "usual_level"} <= tables
        for table, filename in CSV_TABLES.items():
            csv_rows = sum(1 for _ in open(data_dir / filename)) - 1
            (db_rows,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            assert db_rows == csv_rows == counts[table], table


def test_db_keeps_no_patient_details(built_db):
    """Data minimisation: only the request columns the engine uses reach the database."""
    db, _ = built_db
    with sqlite3.connect(db) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(requests)")]
    assert cols == REQUEST_COLUMNS
    for col in ("patient_sex", "patient_age_band", "clinical_indication", "facility_name_raw"):
        assert col not in cols


def test_satellites_hold_no_stock(frames):
    assert not frames.red_stock["facility_id"].str.startswith("SAT").any()
    assert not any(f.startswith("SAT") for f, _ in frames.usual_level)


def test_stock_lookup_matches_raw_csv(frames, data_dir):
    raw = pd.read_csv(data_dir / "daily_stock.csv")
    day, fac = "2026-10-30", "HSP-001"
    sel = raw[(raw.date == day) & (raw.facility_id == fac) & raw.component.isin(["RBC", "WB"])]
    expected = sel.groupby("blood_group").units_in_stock_end_of_day.sum().to_dict()
    for g in BLOOD_GROUPS:
        assert frames.stock.units(day, fac, g) == expected.get(g, 0), g


def test_usual_level_matches_median_of_365_days(frames):
    rs = frames.red_stock
    sel = rs[(rs.facility_id == "HSP-001") & (rs.blood_group == "O+")]
    assert len(sel) == 365
    assert frames.usual_level[("HSP-001", "O+")] == int(sel.units.median())


def test_starter_kit_passes_validation(data_dir):
    assert validate(read_csvs(data_dir)) == []


def test_validation_catches_broken_data(data_dir):
    raw = read_csvs(data_dir)
    broken = dict(raw)
    broken["daily_stock"] = raw["daily_stock"].copy()
    broken["daily_stock"].loc[0, "units_in_stock_end_of_day"] = -1
    broken["routes"] = raw["routes"][raw["routes"].from_facility_id != "RBTC-NBO"]
    broken["units"] = raw["units"].copy()
    broken["units"].loc[raw["units"].status == "transfused", "status_date"] = None
    problems = " | ".join(validate(broken))
    assert "negative stock" in problems
    assert "routes:" in problems
    assert "blank status_date" in problems


def test_build_refuses_invalid_data(tmp_path, data_dir):
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    for name in CSV_TABLES.values():
        (bad_dir / name).symlink_to(data_dir / name)
    (bad_dir / "daily_stock.csv").unlink()
    ds = pd.read_csv(data_dir / "daily_stock.csv")
    ds = ds[~((ds.facility_id == "HSP-001") & (ds.date == "2026-01-01"))]  # drop a day
    ds.to_csv(bad_dir / "daily_stock.csv", index=False)
    with pytest.raises(DataError, match="miss days"):
        build_db(bad_dir, tmp_path / "blood.db")
    assert not (tmp_path / "blood.db").exists()


def test_full_stock_scan_is_fast(frames):
    facilities = frames.facilities.index.tolist()
    start = time.perf_counter()
    for f in facilities:
        frames.stock.groups("2026-10-30", f)
    assert time.perf_counter() - start < 0.05  # one ranking call's worth of lookups
