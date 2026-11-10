"""Step 7: `python -m engine.rank` prints valid JSON (spec section 12, "Done")."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from engine import config, eta, rank

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cli_env(built_db, frames, tmp_path_factory):
    """Env pointing the CLI at the test DB and a freshly fitted model."""
    db, _ = built_db
    data = tmp_path_factory.mktemp("cli_data")
    model, _ = eta.fit(frames, config.load_config("kenya")["eta_train_before"])
    eta.save_json(model, data / "eta_model.json")
    return {**os.environ, "DATA_DIR": str(data), "DB_PATH": str(db)}


def run_cli(env, *args):
    return subprocess.run(
        [sys.executable, "-m", "engine.rank", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120,
    )


@pytest.mark.parametrize("request_id", ["REQ-020421", "REQ-005594", "REQ-003159"])
def test_cli_prints_valid_json_for_golden_requests(cli_env, request_id):
    result = run_cli(cli_env, "--request-id", request_id)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["mode"] == "model" and out["model_used"] is True
    assert out["options"], request_id
    assert list(out) == ["request", "mode", "model_used", "sharing_allowed", "compatibility_note",
                         "stock_note", "advice", "options", "baseline"]


def test_cli_baseline_mode_and_manual_request(cli_env):
    result = run_cli(cli_env, "--request-id", "REQ-020421", "--mode", "baseline")
    assert json.loads(result.stdout)["options"][0]["facility_id"] == "RBTC-ELD"

    result = run_cli(cli_env, "--facility", "HSP-004", "--group", "O+", "--units", "1",
                     "--at", "2026-10-31T00:58:20", "--top-n", "2")
    out = json.loads(result.stdout)
    assert [o["facility_id"] for o in out["options"]] == ["HSP-001", "HSP-002"]


def test_cli_reports_bad_input_without_a_traceback(cli_env):
    result = run_cli(cli_env, "--request-id", "REQ-999999")
    assert result.returncode == 2
    assert result.stderr.strip() == "error: No request 'REQ-999999' in the dataset."
    assert "Traceback" not in result.stderr


def test_cli_explains_a_missing_database(cli_env, tmp_path):
    result = run_cli({**cli_env, "DB_PATH": str(tmp_path / "none.db")}, "--request-id", "REQ-020421")
    assert result.returncode == 2
    assert "build_db.py" in result.stderr


@pytest.mark.parametrize(
    "argv",
    [[], ["--facility", "HSP-004"], ["--request-id", "REQ-020421", "--group", "O+"]],
)
def test_cli_rejects_incomplete_or_mixed_arguments(argv):
    with pytest.raises(SystemExit) as exc:
        rank.main(argv)
    assert exc.value.code == 2
