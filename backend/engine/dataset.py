"""Load the synthetic CSV contract once and build indexes for repeated queries.

This does not replace the application's SQLite ingest. Offline experiments use
the same column names, so the API can later supply equivalent records from SQL.
"""

from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

EAT = timezone(timedelta(hours=3))
Row = dict[str, str]
StockKey = tuple[date, str, str, str]

REQUIRED_COLUMNS = {
    "facilities": {"facility_id", "facility_type", "supply_centre_id"},
    "routes": {"from_facility_id", "to_facility_id", "road_km", "typical_travel_hours"},
    "requests": {"request_id", "facility_id", "requested_at", "patient_blood_group",
                 "component_requested", "units_requested", "units_issued", "urgency",
                 "outcome", "last_unit_available_at"},
    "transfers": {"transfer_id", "request_id", "unit_id", "from_facility_id",
                  "to_facility_id", "transfer_type", "dispatched_at", "received_at"},
    "daily_stock": {"date", "facility_id", "component", "blood_group", "units_in_stock_end_of_day"},
}


class DatasetError(ValueError):
    """A missing file or inconsistent input prevents a reproducible evaluation."""


def local_datetime(value: str | datetime) -> datetime:
    """Treat unzoned starter times as EAT; normalize zoned times to naive EAT."""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return parsed.astimezone(EAT).replace(tzinfo=None) if parsed.tzinfo else parsed


def _read_table(root: Path, name: str) -> list[Row]:
    path = root / f"{name}.csv"
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            missing = REQUIRED_COLUMNS[name] - set(reader.fieldnames or [])
            if missing:
                raise DatasetError(f"{path.name}: missing columns {sorted(missing)}")
            rows = list(reader)
    except FileNotFoundError as exc:
        raise DatasetError(f"Required dataset file not found: {path}") from exc
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise DatasetError(f"{path.name}: malformed CSV row")
    return rows


@dataclass
class Dataset:
    """Indexed records. IDs, rather than free-text facility names, are authoritative."""

    facilities: dict[str, Row]
    routes: dict[tuple[str, str], Row]
    requests: list[Row]
    transfers: list[Row]
    stock: dict[StockKey, int]
    manifest: dict

    @classmethod
    def load(cls, directory: str | Path) -> Dataset:
        root = Path(directory)
        tables = {name: _read_table(root, name) for name in REQUIRED_COLUMNS}
        facilities = {row["facility_id"]: row for row in tables["facilities"]}
        if len(facilities) != len(tables["facilities"]):
            raise DatasetError("facilities.csv: duplicate facility_id")
        for name, key in (("requests", "request_id"), ("transfers", "transfer_id")):
            if len({row[key] for row in tables[name]}) != len(tables[name]):
                raise DatasetError(f"{name}.csv: duplicate {key}")
        request_ids = {row["request_id"] for row in tables["requests"]}
        routes = {}
        for row in tables["routes"]:
            key = (row["from_facility_id"], row["to_facility_id"])
            if key in routes:
                raise DatasetError(f"routes.csv: duplicate route {key}")
            for field in ("road_km", "typical_travel_hours"):
                value = float(row[field])
                if not math.isfinite(value) or value < 0:
                    raise DatasetError(f"routes.csv: invalid {field} for {key}")
            routes[key] = row
        stock = {}
        for row in tables["daily_stock"]:
            key = (date.fromisoformat(row["date"]), row["facility_id"], row["component"], row["blood_group"])
            value = int(row["units_in_stock_end_of_day"])
            if key in stock or value < 0:
                raise DatasetError(f"daily_stock.csv: duplicate key or negative stock: {key}")
            stock[key] = value
        for name, fields in (("requests", ("facility_id",)), ("daily_stock", ("facility_id",)),
                             ("routes", ("from_facility_id", "to_facility_id")),
                             ("transfers", ("from_facility_id", "to_facility_id"))):
            if any(row[field] not in facilities for row in tables[name] for field in fields):
                raise DatasetError(f"{name}.csv: unknown facility reference")
        for row in tables["requests"]:
            local_datetime(row["requested_at"])
            if int(row["units_requested"]) <= 0 or int(row["units_issued"]) < 0:
                raise DatasetError("requests.csv: invalid unit count")
        if any(row["request_id"] and row["request_id"] not in request_ids for row in tables["transfers"]):
            raise DatasetError("transfers.csv: unknown request_id")
        manifest = {}
        for name, rows in tables.items():
            checksum = hashlib.sha256()
            with (root / f"{name}.csv").open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    checksum.update(chunk)
            manifest[f"{name}.csv"] = {"rows": len(rows), "sha256": checksum.hexdigest()}
        return cls(facilities, routes, tables["requests"], tables["transfers"], stock, manifest)
