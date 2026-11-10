"""Strict JSON artifacts, written atomically so readers never see partial output."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def write_json(path: str | Path, payload: dict) -> None:
    # Serialize first: NaN/Infinity or unsupported objects must not damage a file.
    content = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
