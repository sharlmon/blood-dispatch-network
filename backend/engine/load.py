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


# --------------------------------------------------------------------------- validate


class DataError(ValueError):
    """The dataset breaks an assumption the engine relies on."""


def validate(frames: dict[str, pd.DataFrame]) -> list[str]:
    """Check the invariants the engine relies on. Returns a list of problems (empty = OK).

    The starter kit passes all of these. They exist so a different or edited dataset
    fails loudly at build time instead of producing quietly wrong rankings.
    """
    problems: list[str] = []
    fac, ds, ro = frames["facilities"], frames["daily_stock"], frames["routes"]
    units, tr, rq = frames["units"], frames["transfers"], frames["requests"]
    fids = set(fac["facility_id"])

    for name, key in [
        ("facilities", ["facility_id"]),
        ("units", ["unit_id"]),
        ("transfers", ["transfer_id"]),
        ("requests", ["request_id"]),
        ("routes", ["from_facility_id", "to_facility_id"]),
        ("daily_stock", ["date", "facility_id", "component", "blood_group"]),
    ]:
        n = int(frames[name].duplicated(key).sum())
        if n:
            problems.append(f"{name}: {n} duplicate rows for key {key}")

    if (ds["units_in_stock_end_of_day"] < 0).any():
        problems.append("daily_stock: negative stock counts")
    unknown = set(ds["facility_id"]) - fids
    if unknown:
        problems.append(f"daily_stock: unknown facility ids {sorted(unknown)[:5]}")
    if ds["facility_id"].str.startswith("SAT").any():
        problems.append("daily_stock: satellites (SAT-*) hold stock; spec says they never do")
    bad_groups = set(ds["blood_group"]) - set(BLOOD_GROUPS)
    if bad_groups:
        problems.append(f"daily_stock: unexpected blood groups {sorted(bad_groups)}")

    # Missing (facility, group) rows are read as zero stock, which is only safe if
    # every series that exists covers every day.
    n_days = ds["date"].nunique()
    red = ds[ds["component"].isin(RED_CELL_COMPONENTS)]
    days = red.groupby(["facility_id", "component", "blood_group"])["date"].nunique()
    short = days[days != n_days]
    if len(short):
        problems.append(f"daily_stock: {len(short)} red cell series miss days, e.g. {short.index[0]}")

    pairs = set(zip(ro["from_facility_id"], ro["to_facility_id"]))
    stocked = set(ds["facility_id"])
    hospitals = [f for f in fids if f.startswith("HSP")]
    missing = [(s, h) for s in stocked for h in hospitals if s != h and (s, h) not in pairs]
    if missing:
        problems.append(f"routes: {len(missing)} stocked-site -> hospital pairs missing, e.g. {missing[0]}")
    if (ro["typical_travel_hours"] <= 0).any():
        problems.append("routes: non-positive typical_travel_hours")

    # stock.py treats a blank status_date as "still on the shelf".
    blank_not_in_stock = units["status_date"].isna() & (units["status"] != "in_stock")
    if blank_not_in_stock.any():
        problems.append(
            f"units: {int(blank_not_in_stock.sum())} units have a blank status_date but are not in_stock"
        )

    done = tr["received_at"].notna()
    if (pd.to_datetime(tr.loc[done, "received_at"]) < pd.to_datetime(tr.loc[done, "dispatched_at"])).any():
        problems.append("transfers: received_at before dispatched_at")

    unknown = set(rq["facility_id"]) - fids
    if unknown:
        problems.append(f"requests: unknown facility ids {sorted(unknown)[:5]}")
    return problems


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
    problems = validate(frames)
    if problems:
        raise DataError("Dataset failed validation:\n  - " + "\n  - ".join(problems))
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


# A blank status_date means the unit is still in stock at the end of the dataset
# (validated in build_db). Give it a date far in the future so "on the shelf after
# as_of" is a plain comparison.
STILL_ON_SHELF = pd.Timestamp("2262-01-01")


def red_units_frame(units: pd.DataFrame) -> pd.DataFrame:
    """Red cell units with parsed dates, for the near-expiry count."""
    red = units[units["component"].isin(RED_CELL_COMPONENTS)]
    return pd.DataFrame(
        {
            "facility_id": red["current_facility_id"].to_numpy(),
            "blood_group": red["blood_group"].to_numpy(),
            "collection_date": pd.to_datetime(red["collection_date"]).to_numpy(),
            "expiry_date": pd.to_datetime(red["expiry_date"]).to_numpy(),
            "shelf_until": pd.to_datetime(red["status_date"]).fillna(STILL_ON_SHELF).to_numpy(),
        }
    )


@dataclass(frozen=True, eq=False)  # eq=False: hash by identity, so caches can key on it
class Frames:
    facilities: pd.DataFrame  # indexed by facility_id
    facility_info: dict[str, dict]  # facility_id -> row as a plain dict (fast access)
    routes: pd.DataFrame
    units: pd.DataFrame
    transfers: pd.DataFrame
    requests: pd.DataFrame
    red_stock: pd.DataFrame
    red_units: pd.DataFrame
    stock_dates: tuple[str, ...]  # sorted ISO dates that have stock counts
    usual_level: dict[tuple[str, str], int]  # (facility_id, blood_group) -> units
    stock: StockLookup
    travel_hours: dict[tuple[str, str], float]  # (from, to) -> typical_travel_hours
    road_km: dict[tuple[str, str], float]


def frames_from_tables(
    facilities: pd.DataFrame,
    routes: pd.DataFrame,
    units: pd.DataFrame,
    red_stock: pd.DataFrame,
    usual_level: pd.DataFrame,
    transfers: pd.DataFrame | None = None,
    requests: pd.DataFrame | None = None,
) -> Frames:
    """Assemble Frames from tables. Used by load_frames and by tests with tiny datasets."""
    facilities = facilities.set_index("facility_id", drop=False)
    facilities["has_blood_fridge_backup_power"] = facilities[
        "has_blood_fridge_backup_power"
    ].astype(bool)
    pairs = list(zip(routes["from_facility_id"], routes["to_facility_id"]))
    info = facilities.astype(object).where(facilities.notna(), None).to_dict("index")
    return Frames(
        facilities=facilities,
        facility_info=info,
        routes=routes,
        units=units,
        transfers=transfers if transfers is not None else pd.DataFrame(),
        requests=requests if requests is not None else pd.DataFrame(),
        red_stock=red_stock,
        red_units=red_units_frame(units),
        stock_dates=tuple(sorted(red_stock["date"].unique())),
        usual_level={
            (f, g): int(v)
            for f, g, v in zip(
                usual_level["facility_id"], usual_level["blood_group"], usual_level["usual_level"]
            )
        },
        stock=StockLookup(red_stock),
        travel_hours=dict(zip(pairs, routes["typical_travel_hours"].astype(float))),
        road_km=dict(zip(pairs, routes["road_km"].astype(float))),
    )


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
        return frames_from_tables(
            facilities=read("facilities"),
            routes=read("routes"),
            units=read("units"),
            red_stock=read("red_stock"),
            usual_level=read("usual_level"),
            transfers=read("transfers"),
            requests=read("requests"),
        )


def timed_build(data_dir: Path, db_path: Path) -> tuple[dict[str, int], float]:
    start = time.perf_counter()
    counts = build_db(data_dir, db_path)
    return counts, time.perf_counter() - start
