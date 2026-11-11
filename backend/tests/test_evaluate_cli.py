"""Run the actual offline evaluation command against tiny generated CSV tables."""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

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


# --------------------------------------------------------------------------- DS1 candidate provider

DS1_DAYS = ("2025-11-01", "2026-08-31", "2026-09-01", "2026-10-30", "2026-10-31")


def _ds1_stock():
    """Complete daily series, as DS1's build_db requires. The centre holds 1 O+ and 1 O- unit.

    The lender HSP-002 usually holds 2 O+ units (its usual level, so it keeps them), but
    10 on the evening before the test request, so it can then lend 8.
    """
    return [{"date": day, "facility_id": facility, "component": "RBC", "blood_group": group,
             "units_in_stock_end_of_day": units}
            for day in DS1_DAYS
            for facility, group, units in (("HSP-001", "O+", "0"), ("RBTC-001", "O+", "1"), ("RBTC-001", "O-", "1"),
                                           ("HSP-002", "O+", "10" if day == "2026-09-01" else "2"))]


def _ds1_facilities():
    """The centre, the requester HSP-001 and a lending hospital, with the site details DS1 reads."""
    site = {"has_blood_fridge_backup_power": "True", "connectivity": "4G"}
    return [
        {"facility_id": "RBTC-001", "name": "Centre", "facility_type": "regional_blood_centre",
         "supply_centre_id": "", **site},
        {"facility_id": "HSP-001", "name": "Hospital", "facility_type": "county_hospital",
         "supply_centre_id": "RBTC-001", **site},
        {"facility_id": "HSP-002", "name": "Lender", "facility_type": "county_hospital",
         "supply_centre_id": "RBTC-001", **site},
    ]


@pytest.fixture
def ds1_experiment(experiment):
    """The same split plus what DS1's engine also reads: site details and a units table.

    The 2-unit O+ test request is short at the centre for an exact match (1 O+ unit),
    but covered under the fixed compatibility table (1 O+ and 1 O-). The hospital
    HSP-002 is nearer than the centre (0.5 h against 1 h) and can lend 8 O+ units,
    but only if hospitals may lend.
    """
    directory = experiment[0]
    _write_table(directory, "facilities", _ds1_facilities())
    # DS1's build_db needs a route from every stocked site to every other hospital.
    _write_table(directory, "routes", [
        {"from_facility_id": source, "to_facility_id": target, "road_km": km, "typical_travel_hours": hours}
        for source, target, km, hours in (("RBTC-001", "HSP-001", "30", "1"), ("HSP-001", "RBTC-001", "30", "1"),
                                          ("RBTC-001", "HSP-002", "30", "1"), ("HSP-001", "HSP-002", "15", "0.5"),
                                          ("HSP-002", "HSP-001", "15", "0.5"))
    ])
    _write_table(directory, "daily_stock", _ds1_stock())
    with (directory / "units.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["unit_id", "component", "blood_group", "collection_date", "expiry_date",
                         "current_facility_id", "status", "status_date"])
        writer.writerow(["UNIT-1", "RBC", "O+", "2026-08-01", "2026-09-30", "RBTC-001", "in_stock", ""])
    return experiment


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("evaluate_ds2", ROOT / "scripts" / "evaluate_ds2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_provider_flag_and_ds1_output_default(script):
    args = script.parse_args([])
    assert (args.candidate_provider, args.engine_country) == ("reference", "kenya")
    assert args.output_dir == ROOT / "results"
    # A DS1 run never lands on the committed reference artifacts unless asked to.
    assert script.parse_args(["--candidate-provider", "ds1"]).output_dir == ROOT / "results" / "ds1-provider"
    explicit = script.parse_args(["--candidate-provider", "ds1", "--output-dir", "elsewhere"])
    assert explicit.output_dir == Path("elsewhere")
    with pytest.raises(SystemExit):
        script.parse_args(["--candidate-provider", "llm"])


def test_cli_ds1_provider_counts_compatible_red_cells(ds1_experiment):
    directory, settings, output = ds1_experiment
    ds1_output = output.parent / "ds1-results"
    for run in (_run(ds1_experiment), _run((directory, settings, ds1_output), "--candidate-provider", "ds1")):
        assert run.returncode == 0, run.stderr
    reference = _strict_json(output / "replay_summary.json")
    ds1 = _strict_json(ds1_output / "replay_summary.json")
    assert {path.name for path in ds1_output.iterdir()} == ARTIFACTS
    assert reference["result"]["candidate_provider"] == "ReferenceCandidateProvider"
    assert ds1["result"]["candidate_provider"] == "DS1CandidateProvider"
    assert reference["result"]["policies"]["all_centres"]["partial_source_only"] == 1
    assert ds1["result"]["policies"]["all_centres"]["full_source_found"] == 1
    assert "ds1_engine" not in reference["settings"]
    # Only the DS1 settings that shape the replay are recorded: not its ETA, delay or quote.
    assert set(ds1["settings"]["ds1_engine"]) == {"country", "sharing_allowed", "min_keep", "o_neg_reserve"}
    assert ds1["settings"]["ds1_engine"]["min_keep"] == 2
    settings_json = json.dumps(ds1["settings"], sort_keys=True, allow_nan=False)
    assert ds1["settings_sha256"] == hashlib.sha256(settings_json.encode()).hexdigest()
    limitations = ds1["result"]["limitations"]
    assert not any(note.startswith("Reference ") for note in limitations)
    assert any(note.startswith("DS1 provider") for note in limitations)
    assert any("hospital_extra_dispatch_h" in note and "not used" in note for note in limitations)


def test_ds1_run_without_output_dir_leaves_the_reference_results_alone(script, ds1_experiment, monkeypatch, capsys):
    directory, settings, _ = ds1_experiment
    root = directory.parent / "repository"  # stands in for the repo root, so nothing real is written
    monkeypatch.setattr(script, "ROOT", root)
    monkeypatch.setattr(script, "DS1_OUTPUT_DIR", root / "results" / "ds1-provider")
    code = script.main(["--data-dir", str(directory), "--skip-cleaning", "--experiment-settings", str(settings),
                        "--settings", str(ROOT / "backend" / "config" / "settings.default.yaml"),
                        "--candidate-provider", "ds1"])
    assert code == 0, capsys.readouterr().err
    assert [path.name for path in (root / "results").iterdir()] == ["ds1-provider"]
    assert {path.name for path in (root / "results" / "ds1-provider").iterdir()} == ARTIFACTS


@pytest.mark.parametrize(("arguments", "overlay", "message"), [
    (("--hospital-reserve-units", "5"), "", "reference provider only"),
    ((), "replay:\n  components: [RBC, WB]\n", "red cell (RBC) requests only"),
    (("--engine-country", "atlantis"), "", "No settings file"),
    ((), 'lending:\n  enabled: "false"\n', "lending.enabled must be true or false"),  # a string is truthy
])
def test_ds1_provider_rejects_settings_it_cannot_honour(ds1_experiment, arguments, overlay, message):
    settings = ds1_experiment[1]
    settings.write_text(settings.read_text(encoding="utf-8") + overlay, encoding="utf-8")
    completed = _run(ds1_experiment, "--candidate-provider", "ds1", *arguments)
    assert completed.returncode == 1
    assert message in completed.stderr
    assert not ds1_experiment[2].exists()


@pytest.mark.parametrize(("overlay", "lends"), [("", True), ("lending:\n  enabled: false\n", False)])
def test_ds1_provider_follows_the_lending_switch(ds1_experiment, overlay, lends):
    """DS1 reads only its own sharing_allowed, so the script folds DS2's lending switch into it."""
    settings = ds1_experiment[1]
    settings.write_text(settings.read_text(encoding="utf-8") + overlay, encoding="utf-8")
    completed = _run(ds1_experiment, "--candidate-provider", "ds1")
    assert completed.returncode == 0, completed.stderr
    replay = _strict_json(ds1_experiment[2] / "replay_summary.json")
    assert replay["settings"]["lending"]["enabled"] is lends
    assert replay["settings"]["ds1_engine"]["sharing_allowed"] is lends
    network = replay["result"]["policies"]["centres_and_hospitals"]
    assert network["full_source_found"] == 1  # the centre covers the request either way
    assert network["hospital_sources_selected"] == (1 if lends else 0)  # the nearer HSP-002, only if it may lend


def test_ds1_provider_refuses_a_hospital_dispatch_delay_the_replay_cannot_apply(ds1_experiment, tmp_path):
    engine = yaml.safe_load((ROOT / "backend" / "config" / "kenya.yaml").read_text(encoding="utf-8"))
    (tmp_path / "slow.yaml").write_text(yaml.safe_dump({**engine, "hospital_extra_dispatch_h": 3}),
                                        encoding="utf-8")
    # load_config joins the name onto backend/config/, and an absolute path replaces that base.
    completed = _run(ds1_experiment, "--candidate-provider", "ds1", "--engine-country", str(tmp_path / "slow"))
    assert completed.returncode == 1
    assert "adds no hospital dispatch delay; set hospital_extra_dispatch_h to 0" in completed.stderr
    assert not ds1_experiment[2].exists()


def test_ds1_provider_names_facility_columns_its_ranking_reads(ds1_experiment):
    # DS2's tables and DS1's build_db do not need connectivity; DS1 reads it only when it ranks.
    facilities = [{key: value for key, value in row.items() if key != "connectivity"} for row in _ds1_facilities()]
    _write_table(ds1_experiment[0], "facilities", facilities)
    completed = _run(ds1_experiment, "--candidate-provider", "ds1")
    assert completed.returncode == 1
    assert "facilities.csv is missing columns ['connectivity']" in completed.stderr
    assert not ds1_experiment[2].exists()


def test_ds1_provider_reports_data_its_engine_rejects(ds1_experiment):
    gap = {"date": "2026-09-01", "facility_id": "RBTC-001", "component": "WB", "blood_group": "O+",
           "units_in_stock_end_of_day": "1"}  # a red cell series with one day of five
    _write_table(ds1_experiment[0], "daily_stock", _ds1_stock() + [gap])
    completed = _run(ds1_experiment, "--candidate-provider", "ds1")
    assert completed.returncode == 1
    assert "failed validation" in completed.stderr and "series miss days" in completed.stderr
    assert not ds1_experiment[2].exists()


def test_ds1_provider_needs_the_units_table(experiment):
    completed = _run(experiment, "--candidate-provider", "ds1")
    assert completed.returncode == 1
    assert "units.csv" in completed.stderr
    assert not experiment[2].exists()
