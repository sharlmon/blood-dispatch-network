"""Reproduce DS2's arrival validation, replay ladder and pre-alert evidence.

Run from the repository root: python scripts/evaluate_ds2.py --help
Raw data stays under the git-ignored data directory; outputs contain derived
model parameters, aggregate metrics and facility-level review alerts only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import yaml

from engine.arrival import evaluate_arrival_model, fit_arrival_model
from engine.artifacts import write_json
from engine.cleaning import clean_dataset
from engine.dataset import Dataset, EAT, local_datetime
from engine.prealert import evaluate_prealerts, generate_prealerts
from engine.replay import run_replay


def load_settings(base: Path, overrides: Path) -> dict:
    """Merge an experiment overlay without modifying the team's country config."""
    def merge(target, changes):
        if not isinstance(changes, dict):
            raise ValueError("Settings files must contain mappings")
        for key, value in changes.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = value
    settings = {}
    for path in (base, overrides):
        with path.open(encoding="utf-8") as stream:
            merge(settings, yaml.safe_load(stream))
    return settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("DATA_DIR", ROOT / "data" / "datasets terumo")))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--cleaned-dir", type=Path, default=ROOT / "data" / "cleaned")
    parser.add_argument("--skip-cleaning", action="store_true",
                        help="Use an already prepared data directory; still validate its schema and links")
    parser.add_argument("--settings", type=Path, default=ROOT / "backend" / "config" / "settings.default.yaml")
    parser.add_argument("--experiment-settings", type=Path, default=ROOT / "backend" / "engine" / "evaluation.settings.yaml")
    parser.add_argument("--train-before", type=local_datetime, default=local_datetime("2026-07-01T00:00:00"))
    parser.add_argument("--test-start", type=local_datetime, default=local_datetime("2026-09-01T00:00:00"))
    parser.add_argument("--test-end", type=local_datetime, default=local_datetime("2026-11-01T00:00:00"))
    parser.add_argument("--as-of", type=local_datetime, help="Pre-alert demo clock; defaults to the last test evening")
    parser.add_argument("--hospital-reserve-units", type=int,
                        help="Explicit research scenario: reserve this count per exact group/component; excludes O-negative")
    args = parser.parse_args(argv)
    try:
        if not args.train_before < args.test_start < args.test_end:
            raise ValueError("Require train-before < test-start < test-end")
        settings = load_settings(args.settings, args.experiment_settings)
        if args.hospital_reserve_units is not None:
            if args.hospital_reserve_units < 0:
                raise ValueError("Hospital reserve must be nonnegative")
            settings.setdefault("replay", {})["hospital_reserve_units"] = {
                group: args.hospital_reserve_units for group in ("O+", "A+", "B+", "AB+", "A-", "B-", "AB-")}
        if args.skip_cleaning:
            quality = {"performed": False, "reason": "Cleaning explicitly skipped by caller; core schema validation still runs."}
            data_directory = args.data_dir
        else:
            quality = clean_dataset(args.data_dir, args.cleaned_dir)
            data_directory = args.cleaned_dir
        dataset = Dataset.load(data_directory)
        if not dataset.stock or not dataset.requests:
            raise ValueError("Evaluation requires nonempty stock and request tables")
        observed_start = datetime.combine(min(key[0] for key in dataset.stock), datetime.min.time())
        observed_end = datetime.combine(max(key[0] for key in dataset.stock) + timedelta(days=1), datetime.min.time())
        if args.train_before <= observed_start or args.test_end > observed_end or args.test_start < observed_start:
            raise ValueError("Evaluation split is outside the available stock observation period")
        arrival_settings = settings.get("arrival", {})
        model = fit_arrival_model(dataset.requests, dataset.transfers, dataset.routes,
            trained_before=args.train_before, min_samples=arrival_settings.get("min_training_samples", 20),
            seed=arrival_settings.get("seed", 42))
        validation = evaluate_arrival_model(model, dataset.requests, dataset.transfers, dataset.routes,
            start=args.train_before, end=args.test_start, settings=settings)
        test = evaluate_arrival_model(model, dataset.requests, dataset.transfers, dataset.routes,
            start=args.test_start, end=args.test_end, settings=settings)
        replay = run_replay(dataset, start=args.test_start, end=args.test_end, model=model, settings=settings)
        prealert = evaluate_prealerts(dataset.stock, dataset.facilities, dataset.requests,
            start=args.test_start, end=args.test_end, settings=settings)
        demo_clock = args.as_of or (local_datetime(settings["demo_clock"]) if settings.get("demo_clock") else args.test_end - timedelta(hours=6))
        alerts = generate_prealerts(dataset.stock, dataset.facilities, as_of=demo_clock, settings=settings)
        settings_json = json.dumps(settings, sort_keys=True, allow_nan=False)
        metadata = {
            "schema_version": 1,
            "generated_at": datetime.now(EAT).isoformat(),
            "synthetic_data": True,
            "timezone": "Africa/Nairobi",
            "dataset_manifest": dataset.manifest,
            "settings": settings,
            "settings_sha256": hashlib.sha256(settings_json.encode()).hexdigest(),
            "seed": model.seed,
            "cleaning_performed": not args.skip_cleaning,
            "split": {"training_end_exclusive": args.train_before.isoformat(),
                      "validation_end_exclusive": args.test_start.isoformat(),
                      "test_end_exclusive": args.test_end.isoformat()},
        }
        artifacts = {
            "data_quality.json": quality,
            "arrival_model.json": model.to_dict(),
            "arrival_validation.json": {"validation": validation, "test": test},
            "replay_summary.json": replay,
            "prealert_evaluation.json": prealert,
            "prealerts.json": alerts,
        }
        for filename, payload in artifacts.items():
            write_json(args.output_dir / filename, {**metadata, "result": payload})
        summary = {
            "training_batches": model.sample_count,
            "test_arrival_batches": test["sample_count"],
            "arrival_test_metrics": test["metrics"],
            "replay_policies": replay["policies"],
            "prealert_metrics": prealert["metrics"],
        }
        write_json(args.output_dir / "summary.json", {**metadata, "result": summary})
        print(json.dumps({"status": "ok", "output_directory": str(args.output_dir.resolve()),
                          "artifacts": [*artifacts, "summary.json"],
                          "training_batches": model.sample_count,
                          "test_arrival_batches": test["sample_count"]}, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as error:
        print(f"Evaluation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
