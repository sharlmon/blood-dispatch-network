"""Fit the arrival-time model on emergency transfers and print holdout metrics.

Writes $DATA_DIR/eta_model.json and $DATA_DIR/eta_metrics.json.

Usage (from backend/, after build_db.py):
    export DATA_DIR=data
    python scripts/fit_eta.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `engine` importable

from engine import config, eta  # noqa: E402
from engine.load import load_frames  # noqa: E402

# Spec section 7: expected values on the test period.
EXPECTED = {
    "mae_map_only_h": 2.74,
    "mae_map_plus_2h_h": 1.17,
    "mae_model_p50_h": 0.95,
    "coverage_p10_p90": 0.79,
}
LABELS = {
    "mae_map_only_h": "MAE, map time only",
    "mae_map_plus_2h_h": "MAE, map time + 2 h",
    "mae_model_p50_h": "MAE, model p50",
    "coverage_p10_p90": "Share inside p10-p90",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--country", default="kenya")
    args = parser.parse_args(argv)

    cfg = config.load_config(args.country)
    frames = load_frames(config.db_path())
    model, metrics = eta.fit(frames, cfg["eta_train_before"])
    metrics["expected_from_spec"] = EXPECTED

    eta.save_json(model, config.eta_model_path())
    eta.save_json(metrics, config.eta_metrics_path())

    print(f"Trained on requests before {cfg['eta_train_before']}: "
          f"{model['n_wait']} waits, {model['n_ratio']} road ratios "
          f"(corr wait/ratio {model['wait_ratio_corr']})")
    print(f"Tested on {metrics['n_test']} transfers from {metrics['test_from']}\n")
    print(f"  {'metric':<24}{'ours':>8}{'spec':>8}")
    for key, label in LABELS.items():
        print(f"  {label:<24}{metrics[key]:>8.2f}{EXPECTED[key]:>8.2f}")
    print(f"  {'Mean p10-p90 width (h)':<24}{metrics['mean_width_p10_p90_h']:>8.2f}")
    print(f"\nWrote {config.eta_model_path()} and {config.eta_metrics_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
