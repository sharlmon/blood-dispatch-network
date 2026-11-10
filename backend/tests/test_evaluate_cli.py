"""Run the actual offline evaluation command against tiny generated CSV tables."""

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from engine.arrival import ArrivalModel, estimate_arrival
from engine.dataset import REQUIRED_COLUMNS


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = {
    "arrival_model.json", "arrival_validation.json", "replay_summary.json",
    "prealert_evaluation.json", "prealerts.json", "summary.json", "data_quality.json",
}


def _write_table(directory, name, rows):
    columns = sorted(REQUIRED_COLUMNS[name] | {key for row in rows for key in row})
    with (directory / f"{name}.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def experiment(tmp_path):
    """One independent completed shipment in each chronological split."""
    directory = tmp_path / "fixture dataset"
    directory.mkdir()
    _write_table(directory, "facilities", [
        {"facility_id": "RBTC-001", "facility_type": "regional_blood_centre", "supply_centre_id": ""},
        {"facility_id": "HSP-001", "facility_type": "county_hospital", "supply_centre_id": "RBTC-001"},
    ])
    _write_table(directory, "routes", [
        {"from_facility_id": "RBTC-001", "to_facility_id": "HSP-001", "road_km": "30", "typical_travel_hours": "1"},
        {"from_facility_id": "HSP-001", "to_facility_id": "RBTC-001", "road_km": "30", "typical_travel_hours": "1"},
    ])
    requests, transfers = [], []
    for label, day, hour in (("TRAIN", "2026-05-01", 10), ("VALIDATION", "2026-08-01", 10), ("TEST", "2026-09-02", 20)):
        requests.append({
            "request_id": f"REQ-{label}", "facility_id": "HSP-001",
            "requested_at": f"{day}T{hour}:00:00", "patient_blood_group": "O+",
            "component_requested": "RBC", "units_requested": "2" if label == "TEST" else "1",
            "units_issued": "1", "urgency": "emergency",
            "outcome": "partially_fulfilled" if label == "TEST" else "fulfilled",
            "last_unit_available_at": f"{day}T{hour + 3}:00:00",
        })
        transfers.append({
            "transfer_id": f"TRANSFER-{label}", "request_id": f"REQ-{label}",
            "unit_id": f"UNIT-{label}", "from_facility_id": "RBTC-001", "to_facility_id": "HSP-001",
            "transfer_type": "emergency_request", "dispatched_at": f"{day}T{hour + 1}:00:00",
            "received_at": f"{day}T{hour + 3}:00:00",
        })
    _write_table(directory, "requests", requests)
    _write_table(directory, "transfers", transfers)
    inventory = []
    for day in ("2025-11-01", "2026-08-31", "2026-09-01", "2026-10-30", "2026-10-31"):
        for facility, units in (("HSP-001", "0"), ("RBTC-001", "10")):
            inventory.append({
                "date": day, "facility_id": facility, "component": "RBC",
                "blood_group": "O+", "units_in_stock_end_of_day": units,
            })
    _write_table(directory, "daily_stock", inventory)
    settings = tmp_path / "experiment.yaml"
    settings.write_text(
        "arrival:\n  min_training_samples: 1\n  seed: 17\n"
        "prealert:\n  components: [RBC]\n  blood_groups: [O+]\n",
        encoding="utf-8",
    )
    return directory, settings, tmp_path / "results"


def _run(experiment, *extra):
    directory, settings, output = experiment
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_ds2.py"),
         "--data-dir", str(directory), "--output-dir", str(output),
         "--skip-cleaning", "--experiment-settings", str(settings), *extra],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )


def _strict_json(path):
    def invalid_constant(value):
        raise AssertionError(f"Invalid JSON constant {value} in {path.name}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_constant)


def test_cli_builds_reproducible_strict_json_evidence(experiment):
    completed = _run(experiment)
    assert completed.returncode == 0, completed.stderr
    status = json.loads(completed.stdout)
    assert status["status"] == "ok"
    assert set(status["artifacts"]) == ARTIFACTS
    directory, _, output = experiment
    assert {path.name for path in output.iterdir()} == ARTIFACTS
    artifacts = {name: _strict_json(output / name) for name in ARTIFACTS}
    assert artifacts["data_quality.json"]["result"]["performed"] is False
    summary = artifacts["summary.json"]["result"]
    assert summary["training_batches"] == 1
    assert summary["test_arrival_batches"] == 1
    assert summary["arrival_test_metrics"]["nominal_interval_probability"] == 0.8
    assert summary["arrival_test_metrics"]["p10_p90_coverage"] == 1
    assert summary["arrival_test_metrics"]["median_absolute_error_hours"] == 0
    for payload in artifacts.values():
        assert payload["schema_version"] == 1
        assert payload["synthetic_data"] is True
        assert payload["seed"] == 17
        assert payload["timezone"] == "Africa/Nairobi"
        assert payload["cleaning_performed"] is False
        assert payload["split"]["training_end_exclusive"] == "2026-07-01T00:00:00"
        settings_json = json.dumps(payload["settings"], sort_keys=True, allow_nan=False)
        assert payload["settings_sha256"] == hashlib.sha256(settings_json.encode()).hexdigest()
        assert set(payload["dataset_manifest"]) == {f"{name}.csv" for name in REQUIRED_COLUMNS}
        for name, record in payload["dataset_manifest"].items():
            assert record["sha256"] == hashlib.sha256((directory / name).read_bytes()).hexdigest()
            assert record["rows"] > 0
    model = ArrivalModel.from_dict(artifacts["arrival_model.json"]["result"])
    assert ArrivalModel.load(output / "arrival_model.json").to_dict() == model.to_dict()
    estimate = estimate_arrival(1, model=model)
    assert estimate["model_used"] is True
    assert estimate["p10_hours"] == estimate["p50_hours"] == estimate["p90_hours"] == 3
    assert estimate["interval_probability"] == 0.8
    validation = artifacts["arrival_validation.json"]["result"]
    assert validation["validation"]["sample_count"] == validation["test"]["sample_count"] == 1
    policies = artifacts["replay_summary.json"]["result"]["policies"]
    assert policies["baseline"]["full_source_found"] == 1
    assert policies["all_centres"]["full_source_p90_within_deadline"] == 1
    alerts = artifacts["prealerts.json"]["result"]["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["facility_id"] == "HSP-001"
    assert alerts[0]["human_review_required"] is True
    prealert = artifacts["prealert_evaluation.json"]["result"]["metrics"]
    assert prealert["detected_unmet_request_count"] == 1
    assert prealert["censored_window_count"] == 1
    # Aggregate evidence and model parameters must not expose raw request IDs.
    assert all("REQ-TEST" not in (output / name).read_text(encoding="utf-8") for name in ARTIFACTS)


@pytest.mark.parametrize(("arguments", "message"), [
    (("--train-before", "2026-09-01"), "train-before < test-start < test-end"),
    (("--test-end", "2026-11-02"), "outside the available stock observation period"),
    (("--hospital-reserve-units", "-1"), "reserve must be nonnegative"),
])
def test_invalid_cli_experiment_fails_before_creating_results(experiment, arguments, message):
    completed = _run(experiment, *arguments)
    assert completed.returncode == 1
    assert message in completed.stderr
    assert not experiment[2].exists()


def test_missing_csv_schema_fails_without_partial_results(experiment):
    (experiment[0] / "facilities.csv").write_text("wrong_column\nvalue\n", encoding="utf-8")
    completed = _run(experiment)
    assert completed.returncode == 1
    assert "facilities.csv: missing columns" in completed.stderr
    assert not experiment[2].exists()
