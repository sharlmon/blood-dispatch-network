"""Exercise cleaning decisions without relying on the private starter CSVs."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from engine.cleaning import CleaningError, SCHEMAS, clean_dataset


def _write(directory, table, rows, extra=()):
    fields = SCHEMAS[table].split() + list(extra)
    with (directory / f"{table}.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _rows(directory, table):
    with (directory / f"{table}.csv").open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


@pytest.fixture
def source(tmp_path):
    directory = tmp_path / "raw"
    directory.mkdir()
    for table in SCHEMAS:
        _write(directory, table, [])
    _write(directory, "facilities", [
        {"facility_id": "HSP-1", "name": "Hospital One", "facility_type": "county_hospital"},
        {"facility_id": "RBTC-1", "name": "Centre One", "facility_type": "regional_blood_centre"},
    ])
    return directory


def test_cleaning_preserves_raw_and_outputs_reproducible_manifest(source, tmp_path):
    _write(source, "requests", [{
        "request_id": " R1 ", "facility_id": "HSP-1", "facility_name_raw": " wrong name ",
        "requested_at": "2026-01-01T22:00:00Z", "patient_blood_group": " unknown ",
        "component_requested": "rbc", "units_requested": "1", "extra": " untouched ",
    }], extra=("extra",))
    before = {path.name: path.read_bytes() for path in source.glob("*.csv")}
    first = tmp_path / "cleaned"
    report = clean_dataset(source, first)
    row = _rows(first, "requests")[0]
    assert row["facility_name_raw"] == "Hospital One"
    assert row["requested_at"] == "2026-01-02 01:00:00"
    assert row["patient_blood_group"] == "unknown"
    assert row["component_requested"] == "RBC"
    assert row["extra"] == "untouched"
    assert "unknown_patient_blood_group" in row["quality_flags"]
    assert report == json.loads((first / "data_quality.json").read_text())
    assert all(path.read_bytes() == before[path.name] for path in source.glob("*.csv"))
    assert report == clean_dataset(source, tmp_path / "again")
    for name, counts in report["files"].items():
        assert counts["cleaned_sha256"] == hashlib.sha256((first / name).read_bytes()).hexdigest()


def test_only_documented_temperature_sentinels_are_blanked(source, tmp_path):
    _write(source, "temperature_logs", [
        {"facility_id": "HSP-1", "recorded_at": f"2026-01-01 {hour:02}:00:00", "temp_c": value}
        for hour, value in enumerate(("-99.0", "99.9", "0.0", "-2.0", "24.0", "4.2"))
    ])
    report = clean_dataset(source, tmp_path / "out")
    rows = _rows(tmp_path / "out", "temperature_logs")
    assert [row["temp_c"] for row in rows] == ["", "", "", "-2.0", "24.0", "4.2"]
    assert report["corrections"]["temperature_sentinels_removed"] == 3
    assert report["missingness"]["temperature_logs.csv"]["temp_c"] == 3


def test_missing_receipts_and_negative_chronology_stay_flagged_not_imputed(source, tmp_path):
    _write(source, "transfers", [
        {"transfer_id": "T1", "unit_id": "U1", "from_facility_id": "RBTC-1",
         "to_facility_id": "HSP-1", "dispatched_at": "2026-01-01 10:00:00"},
        {"transfer_id": "T2", "unit_id": "U2", "from_facility_id": "RBTC-1",
         "to_facility_id": "HSP-1", "dispatched_at": "2026-01-01 10:00:00",
         "received_at": "2026-01-01 09:00:00"},
    ])
    clean_dataset(source, tmp_path / "out")
    rows = _rows(tmp_path / "out", "transfers")
    assert len(rows) == 2  # No per-unit grouping or deletion.
    assert rows[0]["received_at"] == ""
    assert rows[0]["quality_flags"] == "missing_received_at"
    assert "negative_chronology_dispatched_at_received_at" in rows[1]["quality_flags"]


def test_exact_duplicate_removed_conflicting_key_fails_before_publishing(source, tmp_path):
    record = {"date": "2026-01-01", "facility_id": "HSP-1", "component": "RBC",
              "blood_group": "O+", "units_in_stock_end_of_day": "3"}
    _write(source, "daily_stock", [record, record])
    destination = tmp_path / "out"
    report = clean_dataset(source, destination)
    assert len(_rows(destination, "daily_stock")) == 1
    assert report["exclusions"]["exact_duplicate_rows"] == 1
    before = {path.name: path.read_bytes() for path in destination.glob("*.csv")}
    _write(source, "daily_stock", [record, dict(record, units_in_stock_end_of_day="4")])
    with pytest.raises(CleaningError, match="conflicting duplicate") as caught:
        clean_dataset(source, destination)
    assert caught.value.report["status"] == "failed"
    assert (destination / "cleaning_failure.json").is_file()
    assert all(path.read_bytes() == before[path.name] for path in destination.glob("*.csv"))
    # A failure report contains aggregate reasons, never the conflicting record ID.
    assert "HSP-1" not in json.dumps(caught.value.report)


def test_missing_and_invalid_groups_never_receive_inferred_groups(source, tmp_path):
    _write(source, "daily_stock", [
        {"date": "2026-01-01", "facility_id": "HSP-1", "component": "RBC",
         "blood_group": "o+", "units_in_stock_end_of_day": "0"},
    ])
    _write(source, "donors", [
        {"donor_id": "D1", "blood_group": ""},
        {"donor_id": "D2", "blood_group": "invalid"},
    ])
    clean_dataset(source, tmp_path / "out")
    rows = _rows(tmp_path / "out", "donors")
    assert rows[0]["blood_group"] == ""
    assert rows[1]["blood_group"] == "invalid"
    assert "missing_blood_group" in rows[0]["quality_flags"]
    assert "invalid_blood_group" in rows[1]["quality_flags"]
    stock = _rows(tmp_path / "out", "daily_stock")
    assert len(stock) == 1 and stock[0]["blood_group"] == "O+"


def test_ambiguous_donor_identity_and_short_gap_flagged_without_merging(source, tmp_path):
    common = {"birth_date": "1990-01-01", "sex": "F", "home_county": "County", "phone_last4": "0012"}
    _write(source, "donors", [dict(common, donor_id="D1"), dict(common, donor_id="D2")])
    _write(source, "donations", [
        {"donation_id": "N1", "donor_id": "D1", "collection_date": "2026-01-31", "outcome": "collected"},
        {"donation_id": "N2", "donor_id": "D1", "collection_date": "2026-05-30", "outcome": "collected"},
        {"donation_id": "N3", "donor_id": "D1", "collection_date": "2026-09-30", "outcome": "collected"},
    ])
    clean_dataset(source, tmp_path / "out")
    donors = _rows(tmp_path / "out", "donors")
    assert len(donors) == 2
    assert all("possible_duplicate_donor_review" in row["quality_flags"] for row in donors)
    donations = _rows(tmp_path / "out", "donations")
    assert donations[1]["collection_date"] == "2026-05-30"
    assert donations[1]["quality_flags"] == "short_donation_gap_review"
    assert donations[2]["quality_flags"] == ""


@pytest.mark.parametrize("relation", ["same", "ancestor"])
def test_source_overwrite_and_ancestor_output_rejected(source, relation):
    destination = source if relation == "same" else source.parent
    with pytest.raises(ValueError, match="must not equal or contain"):
        clean_dataset(source, destination)


def test_missing_schema_column_fails_without_publishing_csvs(source, tmp_path):
    (source / "routes.csv").write_text("from_facility_id,to_facility_id\n", encoding="utf-8")
    with pytest.raises(CleaningError, match="missing required columns"):
        clean_dataset(source, tmp_path / "out")
    assert not list((tmp_path / "out").glob("*.csv"))


def test_output_can_be_nested_below_source(source):
    report = clean_dataset(source, source / "cleaned")
    assert report["status"] == "complete"
    assert len(report["files"]) == 11
