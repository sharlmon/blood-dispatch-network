"""The sample outputs in engine/examples/ must match what the engine prints today."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from engine import config

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import make_examples  # noqa: E402


@pytest.fixture(scope="module")
def fresh(frames, eta_model):
    return make_examples.build(frames, eta_model, config.load_config("kenya"))


@pytest.mark.parametrize("filename", [e[0] for e in make_examples.EXAMPLES])
def test_example_file_is_up_to_date(fresh, filename):
    path = make_examples.EXAMPLES_DIR / filename
    assert path.is_file(), f"{filename} missing: run python scripts/make_examples.py"
    assert json.loads(path.read_text()) == fresh[filename], (
        f"{filename} is stale: run python scripts/make_examples.py")


def test_examples_cover_the_cases_teammates_need(fresh):
    assert fresh["full_source.json"]["advice"] is None
    assert fresh["baseline_mode.json"]["mode"] == "baseline"
    assert fresh["partial.json"]["advice"] == "no_full_source"
    assert all("partial" in o["flags"] for o in fresh["partial.json"]["options"])
    assert fresh["too_long.json"]["advice"] == "consider_emergency_O_or_transfer"
