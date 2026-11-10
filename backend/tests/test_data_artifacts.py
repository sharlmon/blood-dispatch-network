"""Input failures and output atomicity must be explicit rather than silent."""

import csv
import json
from datetime import datetime

import pytest

from engine.artifacts import write_json
from engine.arrival import ArrivalModel
from engine.dataset import Dataset, DatasetError, REQUIRED_COLUMNS, local_datetime


def write_tables(root):
    for name, columns in REQUIRED_COLUMNS.items():
        with (root / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow(sorted(columns))


def test_missing_dataset_reports_file(tmp_path):
    with pytest.raises(DatasetError, match="Required dataset file"):
        Dataset.load(tmp_path)


def test_missing_required_columns_reports_schema(tmp_path):
    (tmp_path / "facilities.csv").write_text("wrong_column\nvalue\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="missing columns"):
        Dataset.load(tmp_path)


def test_duplicate_stock_is_rejected(tmp_path):
    write_tables(tmp_path)
    (tmp_path / "facilities.csv").write_text("facility_id,facility_type,supply_centre_id\nHSP-1,county_hospital,\n")
    (tmp_path / "daily_stock.csv").write_text(
        "date,facility_id,component,blood_group,units_in_stock_end_of_day\n"
        "2026-09-01,HSP-1,RBC,O+,0\n2026-09-01,HSP-1,RBC,O+,0\n")
    with pytest.raises(DatasetError, match="duplicate key"):
        Dataset.load(tmp_path)


def test_json_is_strict_and_does_not_damage_existing_artifact(tmp_path):
    path = tmp_path / "nested" / "result.json"
    write_json(path, {"value": None})
    assert json.loads(path.read_text()) == {"value": None}
    with pytest.raises(ValueError):
        write_json(path, {"value": float("nan")})
    assert json.loads(path.read_text()) == {"value": None}
    assert list(path.parent.glob("*.tmp")) == []


def test_timezone_normalization():
    assert local_datetime("2026-09-01T00:00:00+00:00") == datetime(2026, 9, 1, 3)


def test_cli_model_artifact_can_be_loaded_directly(tmp_path):
    model = ArrivalModel(samples=((2, 1.2),), trained_before=datetime(2026, 7, 1))
    path = tmp_path / "arrival_model.json"
    write_json(path, {"schema_version": 1, "result": model.to_dict()})
    assert ArrivalModel.load(path).to_dict() == model.to_dict()
