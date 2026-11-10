"""Conservative, reproducible cleaning of the synthetic starter CSVs.

Raw inputs are never edited. Cleaning changes representations, not clinical
facts: groups are never inferred, donor identities are never merged, missing
stock is never filled, and per-unit transfers are never collapsed. Rows requiring
review remain in the output with machine-readable ``quality_flags``.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


EAT = timezone(timedelta(hours=3))
GROUPS = frozenset({"O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"})
COMPONENTS = frozenset({"RBC", "WB", "PLT", "FFP", "CRYO"})

# Full starter schemas: extra source columns are retained, never silently dropped.
SCHEMAS = {
    "facilities": "facility_id name facility_type county lat lon keph_level beds grid_reliability connectivity supply_centre_id makes_platelets separates_components has_blood_fridge_backup_power routine_deliveries_per_week",
    "routes": "from_facility_id to_facility_id road_km typical_travel_hours road_quality",
    "donors": "donor_id sex birth_date blood_group home_county donor_category registration_date registration_site_id preferred_channel consent_to_contact phone_last4",
    "drives": "drive_id date collecting_site_id county venue_type registered_donors donations_collected donors_deferred",
    "donations": "donation_id donor_id drive_id collection_date collecting_site_id outcome deferral_reason volume_ml screening_result tti_marker tested_date",
    "units": "unit_id donation_id component blood_group collection_date expiry_date processed_at_id current_facility_id status status_date temp_excursion_exposed issued_request_id opening_stock",
    "requests": "request_id facility_id facility_name_raw requested_at clinical_indication patient_sex patient_age_band patient_blood_group component_requested units_requested urgency units_issued units_issued_group_substituted units_from_local_stock emergency_supplied_from_id last_unit_available_at outcome",
    "transfers": "transfer_id unit_id from_facility_id to_facility_id transfer_type request_id dispatched_at received_at transport_mode coolbox_max_temp_c",
    "daily_stock": "date facility_id component blood_group units_in_stock_end_of_day",
    "power_outages": "outage_id facility_id start_time end_time duration_hours backup_power_engaged",
    "temperature_logs": "facility_id recorded_at temp_c",
}
KEYS = {
    "facilities": ("facility_id",), "routes": ("from_facility_id", "to_facility_id"),
    "donors": ("donor_id",), "drives": ("drive_id",), "donations": ("donation_id",),
    "units": ("unit_id",), "requests": ("request_id",), "transfers": ("transfer_id",),
    "daily_stock": ("date", "facility_id", "component", "blood_group"),
    "power_outages": ("outage_id",), "temperature_logs": ("facility_id", "recorded_at"),
}
TIMESTAMPS = frozenset({"requested_at", "last_unit_available_at", "dispatched_at",
                        "received_at", "start_time", "end_time", "recorded_at"})
DATES = frozenset({"birth_date", "registration_date", "date", "collection_date",
                   "tested_date", "expiry_date", "status_date"})
FACILITY_FIELDS = frozenset({"facility_id", "from_facility_id", "to_facility_id",
                            "supply_centre_id", "registration_site_id", "collecting_site_id",
                            "processed_at_id", "current_facility_id", "emergency_supplied_from_id"})
CHRONOLOGY = {
    "donors": (("birth_date", "registration_date"),),
    "donations": (("collection_date", "tested_date"),),
    "units": (("collection_date", "expiry_date"), ("collection_date", "status_date")),
    "requests": (("requested_at", "last_unit_available_at"),),
    "transfers": (("dispatched_at", "received_at"),),
    "power_outages": (("start_time", "end_time"),),
}
NUMERIC_NONNEGATIVE = frozenset({"beds", "road_km", "typical_travel_hours", "volume_ml",
                               "registered_donors", "donations_collected", "donors_deferred",
                               "units_requested", "units_issued", "units_issued_group_substituted",
                               "units_from_local_stock", "units_in_stock_end_of_day", "duration_hours"})


class CleaningError(ValueError):
    """Validation failed; ``report`` contains aggregate findings without raw IDs."""

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read(path: Path):
    """Yield complete CSV dictionaries and reject ragged rows before cleaning."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        if len(header) != len(set(header)):
            raise ValueError(f"{path.name}: duplicate column names")
        required = set(SCHEMAS[path.stem].split())
        if not required.issubset(header):
            raise ValueError(f"{path.name}: missing required columns {sorted(required - set(header))}")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path.name}: malformed CSV row at line {reader.line_num}")
            yield header, row


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(EAT).replace(tzinfo=None)
    return parsed


def _donor_signature(row: dict) -> tuple | None:
    signature = tuple(row[field].strip() for field in ("birth_date", "sex", "home_county", "phone_last4"))
    return signature if all(signature) else None


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _review_indexes(source: Path) -> tuple[Counter, set]:
    """Small donor indexes support review flags, never identity consolidation."""
    signatures = Counter()
    sex = {}
    for _, row in _read(source / "donors.csv"):
        signature = _donor_signature(row)
        if signature:
            signatures[signature] += 1
        sex[row["donor_id"].strip()] = row["sex"].strip()
    donations = defaultdict(list)
    for _, row in _read(source / "donations.csv"):
        if row["outcome"].strip() != "collected":
            continue
        try:
            collected = date.fromisoformat(row["collection_date"].strip())
        except ValueError:
            continue
        donations[row["donor_id"].strip()].append((collected, row["donation_id"].strip()))
    too_soon = set()
    for donor, events in donations.items():
        months = {"M": 3, "F": 4}.get(sex.get(donor))
        if months is None:
            continue
        previous = None
        # Repeated identical donation rows are not separate donation events.
        for collected, identifier in sorted(set(events)):
            if previous is not None and collected < _add_months(previous, months):
                too_soon.add(identifier)
            previous = collected
    return signatures, too_soon


def _normalize(row: dict, table: str, facilities: dict, signatures: Counter,
               too_soon: set, corrections: Counter) -> tuple[dict, set]:
    result = {field: value.strip() for field, value in row.items()}
    corrections["whitespace_trimmed_cells"] += sum(row[field] != value for field, value in result.items())
    flags = set(filter(None, result.get("quality_flags", "").split(";")))
    for field, value in list(result.items()):
        if not value or field == "quality_flags":
            continue
        if field in {"blood_group", "patient_blood_group"}:
            normalized = value.upper()
            if normalized == "UNKNOWN":
                normalized = "unknown"
            if normalized in GROUPS or normalized == "unknown":
                if normalized != value:
                    corrections["blood_groups_normalized"] += 1
                result[field] = normalized
                if normalized == "unknown":
                    flags.add(f"unknown_{field}")
            else:
                flags.add(f"invalid_{field}")
        elif field in {"component", "component_requested"}:
            if value.upper() in COMPONENTS:
                result[field] = value.upper()
                corrections["components_normalized"] += result[field] != value
            else:
                flags.add(f"invalid_{field}")
        elif field in TIMESTAMPS:
            try:
                normalized = _timestamp(value).isoformat(sep=" ")
                corrections["timestamps_normalized"] += normalized != value
                result[field] = normalized
            except ValueError:
                flags.add(f"invalid_{field}")
        elif field in DATES:
            try:
                result[field] = date.fromisoformat(value).isoformat()
            except ValueError:
                flags.add(f"invalid_{field}")
        if field in NUMERIC_NONNEGATIVE:
            try:
                number = float(value)
                if not math.isfinite(number) or number < 0:
                    flags.add(f"invalid_{field}")
            except ValueError:
                flags.add(f"invalid_{field}")
        if field in FACILITY_FIELDS and table != "facilities" and value not in facilities:
            flags.add(f"unknown_{field}")
    if table == "requests":
        canonical = facilities.get(result["facility_id"])
        if canonical is not None and result["facility_name_raw"] != canonical:
            result["facility_name_raw"] = canonical
            corrections["facility_names_canonicalized"] += 1
    if table == "temperature_logs" and result["temp_c"]:
        try:
            number = float(result["temp_c"])
            if number in {-99.0, 99.9, 0.0}:
                result["temp_c"] = ""
                flags.add("documented_temperature_sensor_glitch")
                corrections["temperature_sentinels_removed"] += 1
            elif not math.isfinite(number):
                flags.add("invalid_temp_c")
        except ValueError:
            flags.add("invalid_temp_c")
    for earlier, later in CHRONOLOGY.get(table, ()):
        if result[earlier] and result[later]:
            try:
                if _timestamp(result[later]) < _timestamp(result[earlier]):
                    flags.add(f"negative_chronology_{earlier}_{later}")
            except ValueError:
                pass  # The invalid field already carries its own flag.
    if table == "transfers" and not result["received_at"]:
        flags.add("missing_received_at")
    for field in ("blood_group", "patient_blood_group"):
        if field in result and not result[field]:
            flags.add(f"missing_{field}")
    if table == "donors" and signatures[_donor_signature(result)] > 1:
        flags.add("possible_duplicate_donor_review")
    if table == "donations" and result["donation_id"] in too_soon:
        flags.add("short_donation_gap_review")
    result["quality_flags"] = ";".join(sorted(flags))
    return result, flags


def _write_json(path: Path, payload: dict) -> None:
    # Failure reports use the same atomic replacement rule as successful manifests.
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def clean_dataset(source_dir: str | Path, output_dir: str | Path) -> dict:
    """Write cleaned copies of all eleven CSVs and return an aggregate manifest.

    Every table is staged before publication, so schema/key conflicts leave any
    prior successful CSVs intact. Exact raw duplicates alone are dropped; records
    with conflicting duplicate keys fail rather than selecting an arbitrary row.
    Timestamps become ISO strings representing naive East Africa Time (UTC+03).
    """
    source, output = Path(source_dir).resolve(), Path(output_dir).resolve()
    if output == source or output in source.parents:
        raise ValueError("Cleaned output must not equal or contain the source directory")
    for table in SCHEMAS:
        if not (source / f"{table}.csv").is_file():
            raise ValueError(f"Missing required source file: {table}.csv")
        target = output / f"{table}.csv"
        if target.exists() and target.resolve() == (source / f"{table}.csv").resolve():
            raise ValueError("Cleaned output must not overwrite a source CSV through a symbolic link")
    report = {
        "schema_version": 1, "cleaning_policy_version": "conservative_v1", "status": "complete",
        "time_basis": "Unzoned timestamps represent East Africa Time (UTC+03:00); zoned timestamps are converted to that local time.",
        "files": {}, "corrections": {}, "missingness": {}, "review_flags": {},
        "exclusions": {"exact_duplicate_rows": 0, "other_rows": 0},
        "limitations": [
            "Synthetic data only; findings do not describe real facilities or patients.",
            "Missing values, unknown blood groups, and absent stock series are not imputed.",
            "Possible duplicate donor identities and short donation gaps require review; identities and dates are unchanged.",
            "Flagged rows remain present; consuming models must enforce their own eligibility and complete-observation rules.",
            "No clinical compatibility, hospital reserves, unit final-state history, or safe lending eligibility is inferred.",
            "Only the three documented temperature sentinel values are blanked; other readings remain for review.",
            "Files publish atomically one at a time, with the manifest last; do not run concurrent cleaners against one output directory.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    corrections, all_flags = Counter(), Counter()
    current_file = None
    try:
        signatures, too_soon = _review_indexes(source)
        facilities = {}
        with tempfile.TemporaryDirectory(prefix=".cleaning-", dir=output) as temporary:
            staging = Path(temporary)
            for table in SCHEMAS:
                filename = f"{table}.csv"
                current_file = filename
                original = source / filename
                cleaned = staging / filename
                seen, missing, flag_counts = {}, Counter(), Counter()
                stats = {"source_rows": 0, "cleaned_rows": 0, "exact_duplicate_rows_removed": 0,
                         "flagged_rows": 0, "source_sha256": _sha256(original)}
                report["files"][filename] = stats
                with cleaned.open("w", encoding="utf-8", newline="") as stream:
                    writer = None
                    for header, raw in _read(original):
                        stats["source_rows"] += 1
                        if writer is None:
                            fields = list(header)
                            if "quality_flags" not in fields:
                                fields.append("quality_flags")
                            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
                            writer.writeheader()
                        # Compare original cells, before any representational corrections.
                        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")).digest()
                        row, flags = _normalize(raw, table, facilities, signatures, too_soon, corrections)
                        key = tuple(row[field] for field in KEYS[table])
                        if not all(key):
                            raise ValueError(f"{filename}: missing record-key field")
                        if key in seen:
                            if seen[key] != digest:
                                stats["conflicting_duplicate_keys"] = stats.get("conflicting_duplicate_keys", 0) + 1
                                raise ValueError(f"{filename}: conflicting duplicate record key")
                            stats["exact_duplicate_rows_removed"] += 1
                            report["exclusions"]["exact_duplicate_rows"] += 1
                            continue
                        seen[key] = digest
                        if table == "facilities":
                            facilities[row["facility_id"]] = row["name"]
                        writer.writerow(row)
                        stats["cleaned_rows"] += 1
                        stats["flagged_rows"] += bool(flags)
                        flag_counts.update(flags)
                        missing.update(field for field, value in row.items() if not value and field != "quality_flags")
                    if writer is None:
                        # Even empty tables retain their supplied columns and the flag column.
                        with original.open(encoding="utf-8-sig", newline="") as raw_stream:
                            fields = next(csv.reader(raw_stream))
                        if "quality_flags" not in fields:
                            fields.append("quality_flags")
                        csv.DictWriter(stream, fieldnames=fields, lineterminator="\n").writeheader()
                stats["cleaned_sha256"] = _sha256(cleaned)
                stats["flags"] = dict(sorted(flag_counts.items()))
                report["missingness"][filename] = dict(sorted(missing.items()))
                all_flags.update(flag_counts)
            report["corrections"] = dict(sorted(corrections.items()))
            report["review_flags"] = dict(sorted(all_flags.items()))
            for table in SCHEMAS:
                os.replace(staging / f"{table}.csv", output / f"{table}.csv")
            _write_json(output / "data_quality.json", report)
    except (ValueError, OSError) as error:
        report["status"] = "failed"
        report["corrections"] = dict(sorted(corrections.items()))
        report["review_flags"] = dict(sorted(all_flags.items()))
        report["failure"] = {"file": current_file, "reason": str(error)}
        _write_json(output / "cleaning_failure.json", report)
        raise CleaningError(str(error), report) from error
    return report
