"""Paths and per-country settings.

Paths come from environment variables so nothing machine-specific is hard-coded:

- ``DATA_DIR`` (required): folder holding the starter-kit CSVs. Engine outputs
  (``blood.db``, ``eta_model.json``, ``eta_metrics.json``) are written here too.
- ``ENGINE_DB_PATH`` (optional): the engine's SQLite file. Defaults to ``$DATA_DIR/blood.db``.
  (Named apart from the Flask API's own ``DB_PATH`` so the two never collide.)

Relative paths are resolved against the repository root, so the same ``.env``
works whether you run from the repo root or from ``backend/``.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ENGINE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ENGINE_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
CONFIG_DIR = BACKEND_DIR / "config"

# Spec section 10. Used to fill gaps and to type-check a country file.
DEFAULTS: dict = {
    "country": "Kenya",
    "sharing_allowed": True,
    "min_keep": 2,
    "o_neg_reserve": 2,
    "near_expiry_days": 10,
    "hospital_extra_dispatch_h": 0.0,
    "clinician_limit_h": 6.0,
    "baseline_quote_extra_h": 2.0,
    "eta_train_before": "2026-07-01",
    "language": "en",
}


class ConfigError(RuntimeError):
    """Raised when a required setting or environment variable is missing or invalid."""


def _resolve(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def data_dir() -> Path:
    raw = os.environ.get("DATA_DIR")
    if not raw:
        raise ConfigError(
            "DATA_DIR is not set. Point it at the folder holding the starter-kit CSVs, "
            "e.g. `export DATA_DIR=data`."
        )
    path = _resolve(raw)
    if not path.is_dir():
        raise ConfigError(f"DATA_DIR={raw!r} resolves to {path}, which is not a folder.")
    return path


def db_path() -> Path:
    raw = os.environ.get("ENGINE_DB_PATH")
    return _resolve(raw) if raw else data_dir() / "blood.db"


def eta_model_path() -> Path:
    return data_dir() / "eta_model.json"


def eta_metrics_path() -> Path:
    return data_dir() / "eta_metrics.json"


def load_config(country: str = "kenya", path: str | Path | None = None) -> dict:
    """Load ``config/<country>.yaml``, fill missing keys from the spec defaults, check types."""
    cfg_path = Path(path) if path else CONFIG_DIR / f"{country}.yaml"
    if not cfg_path.is_file():
        raise ConfigError(f"No settings file at {cfg_path}.")
    with cfg_path.open() as fh:
        loaded = yaml.safe_load(fh) or {}

    cfg = dict(DEFAULTS)
    cfg.update(loaded)

    for key, default in DEFAULTS.items():
        value = cfg[key]
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise ConfigError(f"{cfg_path.name}: {key} must be true or false, got {value!r}.")
        elif isinstance(default, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ConfigError(f"{cfg_path.name}: {key} must be a number, got {value!r}.")
            if value < 0:
                raise ConfigError(f"{cfg_path.name}: {key} must not be negative, got {value!r}.")
            cfg[key] = type(default)(value) if isinstance(default, float) else int(value)
        else:
            cfg[key] = str(value)
    return cfg
