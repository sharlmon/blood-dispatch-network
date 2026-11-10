"""CSV -> SQLite, plus the precomputed tables and cached frames the engine reads.

Tables written to SQLite:

- raw copies of the CSVs the engine uses (spec section 4): facilities, routes,
  daily_stock, units, transfers, requests;
- ``red_stock``: end-of-day red cell stock per (date, facility_id, blood_group),
  RBC + WB summed (spec: treat both as red cell supply for v1);
- ``usual_level``: median end-of-day red cell stock per (facility_id, blood_group).

Data facts this relies on (checked against the starter kit):

- every (facility, component, group) present in daily_stock has all 365 days,
  with zero stock written as an explicit 0, so a missing combination means
  zero stock all year;
- satellites (SAT-*) have no daily_stock rows, so they never get stock.
"""

from __future__ import annotations

import math
import sqlite3
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

RED_CELL_COMPONENTS = ("RBC", "WB")
BLOOD_GROUPS = ("O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+")

CSV_TABLES = {
    "facilities": "facilities.csv",
    "routes": "routes.csv",
    "daily_stock": "daily_stock.csv",
    "units": "units.csv",
    "transfers": "transfers.csv",
    "requests": "requests.csv",
}

INDEXES = {
    "facilities": ["facility_id"],
    "routes": ["from_facility_id, to_facility_id"],
    "daily_stock": ["date, facility_id"],
    "units": ["current_facility_id, blood_group"],
    "transfers": ["request_id"],
    "requests": ["request_id"],
    "red_stock": ["date, facility_id"],
    "usual_level": ["facility_id, blood_group"],
}


# --------------------------------------------------------------------------- precompute


def red_stock_frame(daily_stock: pd.DataFrame) -> pd.DataFrame:
    """Sum RBC + WB end-of-day stock per (date, facility_id, blood_group)."""
    red = daily_stock[daily_stock["component"].isin(RED_CELL_COMPONENTS)]
    out = (
        red.groupby(["date", "facility_id", "blood_group"], as_index=False)[
            "units_in_stock_end_of_day"
        ]
        .sum()
        .rename(columns={"units_in_stock_end_of_day": "units"})
    )
    out["units"] = out["units"].astype(int)
    return out


def usual_level_frame(red_stock: pd.DataFrame) -> pd.DataFrame:
    """Median end-of-day red cell stock per (facility_id, blood_group).

    With 365 days the median is always an observed whole number. If a facility ever
    has an even number of days, round the median up: keeping one unit more is the
    safe side for the lending hospital.
    """
    med = red_stock.groupby(["facility_id", "blood_group"], as_index=False)["units"].median()
    med["usual_level"] = med["units"].map(lambda v: int(math.ceil(v)))
    return med[["facility_id", "blood_group", "usual_level"]]


# --------------------------------------------------------------------------- build


def read_csvs(data_dir: Path) -> dict[str, pd.DataFrame]:
    frames = {}
    for table, filename in CSV_TABLES.items():
        path = Path(data_dir) / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing {filename} in DATA_DIR ({data_dir}).")
        frames[table] = pd.read_csv(path)
    return frames


def build_db(data_dir: Path, db_path: Path) -> dict[str, int]:
    """Write the raw tables and precomputed tables to ``db_path``. Returns row counts."""
    frames = read_csvs(data_dir)
    frames["red_stock"] = red_stock_frame(frames["daily_stock"])
    frames["usual_level"] = usual_level_frame(frames["red_stock"])

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_suffix(db_path.suffix + ".tmp")
    tmp_path.unlink(missing_ok=True)

    with sqlite3.connect(tmp_path) as conn:
        for table, frame in frames.items():
            frame.to_sql(table, conn, index=False)
        for table, cols in INDEXES.items():
            for i, col in enumerate(cols):
                conn.execute(f"CREATE INDEX idx_{table}_{i} ON {table} ({col})")
    # Swap in atomically so a half-written DB is never read.
    tmp_path.replace(db_path)
    load_frames.cache_clear()
    return {table: len(frame) for table, frame in frames.items()}


# --------------------------------------------------------------------------- read


class StockLookup:
    """O(1) lookup of red cell stock keyed by (date, facility_id, blood_group).

    Combinations with no row are zero stock (see module docstring).
    """

    def __init__(self, red_stock: pd.DataFrame):
        self._by_day: dict[tuple[str, str], dict[str, int]] = {}
        for (day, facility), grp in red_stock.groupby(["date", "facility_id"]):
            self._by_day[(day, facility)] = dict(zip(grp["blood_group"], grp["units"].astype(int)))

    def units(self, day: str, facility_id: str, blood_group: str) -> int:
        return self._by_day.get((day, facility_id), {}).get(blood_group, 0)

    def groups(self, day: str, facility_id: str) -> dict[str, int]:
        """All eight groups for one facility-day, zeros included."""
        found = self._by_day.get((day, facility_id), {})
        return {g: found.get(g, 0) for g in BLOOD_GROUPS}


@dataclass(frozen=True)
class Frames:
    facilities: pd.DataFrame  # indexed by facility_id
    routes: pd.DataFrame
    units: pd.DataFrame
    transfers: pd.DataFrame
    requests: pd.DataFrame
    red_stock: pd.DataFrame
    usual_level: dict[tuple[str, str], int]  # (facility_id, blood_group) -> units
    stock: StockLookup
    travel_hours: dict[tuple[str, str], float]  # (from, to) -> typical_travel_hours
    road_km: dict[tuple[str, str], float]


@lru_cache(maxsize=4)
def load_frames(db_path: str | Path) -> Frames:
    """Read everything the engine needs from SQLite once per process."""
    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(
            f"No database at {db_path}. Run `python scripts/build_db.py` from backend/ first."
        )
    with sqlite3.connect(db_path) as conn:
        read = lambda table: pd.read_sql_query(f"SELECT * FROM {table}", conn)  # noqa: E731
        facilities = read("facilities").set_index("facility_id", drop=False)
        routes = read("routes")
        units = read("units")
        transfers = read("transfers")
        requests = read("requests")
        red_stock = read("red_stock")
        usual = read("usual_level")

    facilities["has_blood_fridge_backup_power"] = facilities[
        "has_blood_fridge_backup_power"
    ].astype(bool)
    pairs = list(zip(routes["from_facility_id"], routes["to_facility_id"]))
    return Frames(
        facilities=facilities,
        routes=routes,
        units=units,
        transfers=transfers,
        requests=requests,
        red_stock=red_stock,
        usual_level={
            (f, g): int(v)
            for f, g, v in zip(usual["facility_id"], usual["blood_group"], usual["usual_level"])
        },
        stock=StockLookup(red_stock),
        travel_hours=dict(zip(pairs, routes["typical_travel_hours"].astype(float))),
        road_km=dict(zip(pairs, routes["road_km"].astype(float))),
    )


def timed_build(data_dir: Path, db_path: Path) -> tuple[dict[str, int], float]:
    start = time.perf_counter()
    counts = build_db(data_dir, db_path)
    return counts, time.perf_counter() - start
