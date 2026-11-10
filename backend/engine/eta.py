"""Arrival-time range (spec section 7).

arrival = dispatch wait + extra + ratio x typical_travel_hours

- ``wait``  = dispatched_at - requested_at on past emergency transfers;
- ``ratio`` = actual road time / map time (typical_travel_hours);
- ``extra`` = hospital_extra_dispatch_h when the lender is a hospital (default 0).
  Every emergency lender in the starter data is a regional centre, so this is a
  sensitivity setting, not something the data can fit.

The fit stores the empirical training samples of wait and ratio. A query draws
from them independently (they are uncorrelated in the data: r = -0.004) with a
fixed seed, so the same input always gives the same answer, and every candidate
in one ranking is scored against the same draws.
"""

from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from engine.load import Frames

log = logging.getLogger(__name__)

MODEL_VERSION = 1
N_DRAWS = 4000
SEED = 20261031

# Used when the model file is missing (spec section 7).
FALLBACK_WAIT_H = 2.0
FALLBACK_RATIO = 1.2
FALLBACK_HALF_WIDTH = 0.5  # p10 = p50 x 0.5, p90 = p50 x 1.5


# --------------------------------------------------------------------------- fit


def emergency_transfers(frames: Frames) -> pd.DataFrame:
    """Emergency transfers joined to their request time and map travel time."""
    tr = frames.transfers
    em = tr[tr["transfer_type"].str.startswith("emergency")].copy()
    requested = frames.requests.set_index("request_id")["requested_at"]
    em["requested_at"] = pd.to_datetime(em["request_id"].map(requested))
    em["dispatched_at"] = pd.to_datetime(em["dispatched_at"])
    em["received_at"] = pd.to_datetime(em["received_at"])
    em["travel_hours"] = [
        frames.travel_hours[(a, b)] for a, b in zip(em["from_facility_id"], em["to_facility_id"])
    ]
    em["lender_is_hospital"] = em["from_facility_id"].str.startswith("HSP")
    em["wait_h"] = (em["dispatched_at"] - em["requested_at"]).dt.total_seconds() / 3600
    road_h = (em["received_at"] - em["dispatched_at"]).dt.total_seconds() / 3600
    em["ratio"] = road_h / em["travel_hours"]  # NaN where received_at is missing
    em["actual_h"] = (em["received_at"] - em["requested_at"]).dt.total_seconds() / 3600
    return em


def fit(frames: Frames, train_before: str) -> tuple[dict, dict]:
    """Fit on requests before ``train_before``; score on the rest. Returns (model, metrics)."""
    em = emergency_transfers(frames)
    train_mask = em["requested_at"] < pd.Timestamp(train_before)
    train, test = em[train_mask], em[~train_mask]

    wait = train["wait_h"].dropna().to_numpy()
    ratio = train["ratio"].dropna().to_numpy()  # drops the ~3% with no received_at
    model = {
        "version": MODEL_VERSION,
        "fitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_before": train_before,
        "n_wait": int(len(wait)),
        "n_ratio": int(len(ratio)),
        "wait_ratio_corr": round(float(np.corrcoef(train.dropna(subset=["ratio"])[["wait_h", "ratio"]].T)[0, 1]), 4),
        "wait_h": [round(float(x), 4) for x in np.sort(wait)],
        "ratio": [round(float(x), 4) for x in np.sort(ratio)],
    }
    fitted = EtaModel.from_dict(model)
    metrics = holdout_metrics(fitted, test)
    metrics["train_before"] = train_before
    metrics["by_group"] = holdout_by_group(fitted, test, frames)
    return model, metrics


def holdout_metrics(model: EtaModel, test: pd.DataFrame, extra_h: float = 0.0) -> dict:
    """MAE of map time, map time + 2 h, model p50; share of arrivals inside p10-p90."""
    scored = test.dropna(subset=["actual_h"])
    actual = scored["actual_h"].to_numpy()
    travel = scored["travel_hours"].to_numpy()
    q = model.quantiles(travel, extra_h=extra_h)
    inside = (actual >= q["p10"]) & (actual <= q["p90"])
    return {
        "n_test": int(len(scored)),
        "test_from": str(scored["requested_at"].min().date()) if len(scored) else None,
        "mae_map_only_h": round(float(np.mean(np.abs(actual - travel))), 3),
        "mae_map_plus_2h_h": round(float(np.mean(np.abs(actual - (travel + 2.0)))), 3),
        "mae_model_p50_h": round(float(np.mean(np.abs(actual - q["p50"]))), 3),
        "coverage_p10_p90": round(float(np.mean(inside)), 3),
        "mean_width_p10_p90_h": round(float(np.mean(q["p90"] - q["p10"])), 3),
    }


DISTANCE_BANDS = ((0.0, 2.0, "map < 2 h"), (2.0, 5.0, "map 2-5 h"), (5.0, float("inf"), "map 5 h+"))


def holdout_by_group(model: EtaModel, test: pd.DataFrame, frames: Frames) -> list[dict]:
    """Fairness check: holdout metrics split by distance and by the receiving hospital's
    connectivity, so remote or poorly connected sites are not served worse unnoticed."""
    conn = test["to_facility_id"].map(lambda f: frames.facility_info[f]["connectivity"])
    groups = [(label, test[(test["travel_hours"] >= lo) & (test["travel_hours"] < hi)])
              for lo, hi, label in DISTANCE_BANDS]
    groups += [(f"receiver {c}", test[conn == c]) for c in sorted(conn.dropna().unique())]
    return [{"group": label, **holdout_metrics(model, g)} for label, g in groups if len(g)]


def save_json(obj: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(path)


# --------------------------------------------------------------------------- query


@dataclass(frozen=True, eq=False)
class EtaModel:
    """Fixed draws of (wait, ratio). ``model_used`` is False for the fallback."""

    wait_draws: np.ndarray | None
    ratio_draws: np.ndarray | None
    model_used: bool

    @classmethod
    def from_dict(cls, d: dict, n_draws: int = N_DRAWS, seed: int = SEED) -> "EtaModel":
        wait, ratio = np.asarray(d["wait_h"], float), np.asarray(d["ratio"], float)
        if wait.size == 0 or ratio.size == 0:
            raise ValueError("ETA model has no samples.")
        rng = np.random.default_rng(seed)
        return cls(
            wait_draws=rng.choice(wait, size=n_draws, replace=True),
            ratio_draws=rng.choice(ratio, size=n_draws, replace=True),  # independent of wait
            model_used=True,
        )

    @classmethod
    def fallback(cls) -> "EtaModel":
        return cls(wait_draws=None, ratio_draws=None, model_used=False)

    def quantiles(self, travel_hours, extra_h: float = 0.0) -> dict[str, np.ndarray]:
        """p10/p50/p90 plus parts, vectorised over an array of travel times (hours)."""
        travel = np.atleast_1d(np.asarray(travel_hours, float))
        if not self.model_used:
            wait_p50 = np.full(travel.shape, FALLBACK_WAIT_H + extra_h)
            road_p50 = FALLBACK_RATIO * travel
            p50 = wait_p50 + road_p50
            return {
                "p10": p50 * (1 - FALLBACK_HALF_WIDTH),
                "p50": p50,
                "p90": p50 * (1 + FALLBACK_HALF_WIDTH),
                "wait_p50": wait_p50,
                "road_p50": road_p50,
            }
        # rows = candidates, columns = draws
        arrival = self.wait_draws[None, :] + extra_h + self.ratio_draws[None, :] * travel[:, None]
        p10, p50, p90 = np.quantile(arrival, [0.10, 0.50, 0.90], axis=1)
        return {
            "p10": p10,
            "p50": p50,
            "p90": p90,
            "wait_p50": np.full(travel.shape, float(np.median(self.wait_draws)) + extra_h),
            "road_p50": float(np.median(self.ratio_draws)) * travel,
        }


@lru_cache(maxsize=8)
def _load_cached(path: str, mtime: float) -> EtaModel:
    with open(path) as fh:
        return EtaModel.from_dict(json.load(fh))


def load_model(path: str | Path | None) -> EtaModel:
    """Load the fitted model, or fall back (model_used=False) if it is missing or unreadable."""
    if path is None or not Path(path).is_file():
        log.info("No ETA model at %s; using fallback.", path)
        return EtaModel.fallback()
    try:
        return _load_cached(str(path), Path(path).stat().st_mtime)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        warnings.warn(f"ETA model at {path} is unreadable ({exc}); using fallback.", stacklevel=2)
        return EtaModel.fallback()


def eta_window(
    travel_hours: float,
    lender_is_hospital: bool,
    config: dict,
    model: EtaModel,
) -> dict:
    """Arrival range for one candidate: p10, p50, p90, wait_p50, road_p50 (hours, unrounded)."""
    extra = config["hospital_extra_dispatch_h"] if lender_is_hospital else 0.0
    q = model.quantiles([travel_hours], extra_h=extra)
    return {k: float(v[0]) for k, v in q.items()}


def baseline_quote(travel_hours: float, config: dict) -> float:
    """Today's rule: map time + 2 h. A single number with no range."""
    return float(travel_hours) + config["baseline_quote_extra_h"]
