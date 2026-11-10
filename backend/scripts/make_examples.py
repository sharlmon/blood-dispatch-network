"""Write sample engine outputs to backend/engine/examples/ for teammates.

The web and SMS teammates can build against these files without installing
Python or the dataset. tests/test_examples.py fails if they go out of date;
rerun this script after any change to the engine's output.

Usage (from backend/, after build_db.py and fit_eta.py):
    export DATA_DIR=data
    python scripts/make_examples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `engine` importable

from engine import config, eta, rank  # noqa: E402
from engine.load import load_frames  # noqa: E402

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "engine" / "examples"

# (file name, request_id, mode, what it shows)
EXAMPLES = [
    ("full_source.json", "REQ-020421", "model",
     "Nearby hospitals can cover the request; normal case (golden case 1)."),
    ("baseline_mode.json", "REQ-020421", "baseline",
     "Same request under today's rule (mode=baseline)."),
    ("partial.json", "REQ-004890", "model",
     "No site can cover all 6 units: options flagged partial, advice no_full_source."),
    ("too_long.json", "REQ-003159", "model",
     "Nothing close: advice consider_emergency_O_or_transfer (golden case 3)."),
]


def build(frames, model, cfg) -> dict[str, dict]:
    out = {}
    for filename, request_id, mode, _ in EXAMPLES:
        req = rank.request_from_dataset(frames, request_id)
        out[filename] = rank.rank_sources(req, mode=mode, config=cfg, frames=frames, eta_model=model)
    return out


def dumps(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    frames = load_frames(config.db_path())
    model = eta.load_model(config.eta_model_path())
    if not model.model_used:
        print("error: no fitted arrival model; run scripts/fit_eta.py first", file=sys.stderr)
        return 2
    EXAMPLES_DIR.mkdir(exist_ok=True)
    for filename, payload in build(frames, model, config.load_config()).items():
        (EXAMPLES_DIR / filename).write_text(dumps(payload))
        print(f"wrote {EXAMPLES_DIR / filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
