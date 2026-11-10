"""Read the committed DS2 result artifacts (results/*.json) for the API.

Only whitelisted file names, and scenario folders that exist, are ever opened: the request
text is compared against those names and never used to build a path.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULT_FILES = ("arrival_validation", "data_quality", "prealert_evaluation", "replay_summary", "summary")
PREALERTS = "prealerts"
_SCENARIO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class ArtifactNotFound(LookupError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def results_dir() -> Path:
    """RESULTS_DIR (relative paths resolve from the repo root), default <repo>/results."""
    raw = os.environ.get("RESULTS_DIR")
    if not raw:
        return REPO_ROOT / "results"
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def scenarios(root: Path) -> list[str]:
    """Subfolders holding a summary.json, e.g. hospital-reserve-5."""
    try:
        entries = list(Path(root).iterdir())
    except OSError:
        return []
    return sorted(p.name for p in entries if _SCENARIO.fullmatch(p.name) and (p / "summary.json").is_file())


def files(root: Path) -> list[str]:
    return [name for name in RESULT_FILES if (Path(root) / f"{name}.json").is_file()]


def _read(root: Path, name: str, scenario: str | None = None) -> tuple[dict, Path]:
    folder = Path(root)
    if scenario:
        if scenario not in scenarios(root):
            raise ArtifactNotFound(f"No results scenario {scenario!r}.")
        folder = folder / scenario
    path = folder / f"{name}.json"
    if not path.is_file():
        raise ArtifactNotFound(f"No {name} results file.")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh), path


def read_result(root: Path, name: str, scenario: str | None = None) -> dict:
    """One artifact's full envelope, unchanged."""
    if name not in RESULT_FILES:
        raise ArtifactNotFound(f"No results file called {name!r}.")
    return _read(root, name, scenario)[0]


def read_prealerts(root: Path, names: dict[str, str | None]) -> dict:
    """The evening pre-alert list, each row with the facility's name (null when unknown)."""
    envelope, path = _read(root, PREALERTS)
    result = envelope.get("result") or {}

    def named(rows) -> list[dict]:
        rows = [row for row in rows or [] if isinstance(row, dict)]
        return [{**row, "facility_name": names.get(row.get("facility_id"))} for row in rows]

    try:
        source = path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:  # outside the repo: don't show the server's folders
        source = path.name
    return {
        "generated_at": result.get("generated_at", envelope.get("generated_at")),
        "stock_as_of": result.get("stock_as_of"),
        "alerts": named(result.get("alerts")),
        "missing_snapshot": named(result.get("missing_snapshot")),
        "assumptions": list(result.get("assumptions") or []),
        # The project only ever uses the synthetic starter data; never claim otherwise by default.
        "synthetic_data": envelope.get("synthetic_data") is not False,
        "source": source,
    }
