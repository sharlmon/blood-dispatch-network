"""One-off: starter-kit CSVs -> SQLite, plus the precomputed usual_level and red_stock tables.

Usage (from backend/):
    export DATA_DIR=data            # relative paths resolve from the repo root; absolute paths work too
    python scripts/build_db.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `engine` importable

from engine import config  # noqa: E402
from engine.load import load_frames, timed_build  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", help="override DATA_DIR")
    parser.add_argument("--db-path", help="override ENGINE_DB_PATH")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else config.data_dir()
    db_path = Path(args.db_path) if args.db_path else config.db_path()

    counts, seconds = timed_build(data_dir, db_path)
    print(f"Built {db_path} in {seconds:.1f} s")
    for table, n in counts.items():
        print(f"  {table:<12} {n:>8,} rows")

    frames = load_frames(db_path)
    hospitals = sum(1 for (f, _g) in frames.usual_level if f.startswith("HSP"))
    print(f"  usual_level covers {hospitals} hospital-group pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
