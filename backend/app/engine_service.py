"""The API's adapter around the decision engine (backend/engine).

The engine's ranking JSON (spec section 9) passes through unchanged. Around it this adds
what the API needs: lazy, thread-safe loading with a status for /api/health, input checks
with plain 400 messages, the demo clock, and the facility names and map positions the
screens show. No Flask here; the routes turn the exceptions below into HTTP errors.
"""

from __future__ import annotations

import functools
import logging
import math
import os
import re
import sqlite3
import threading
import time
import weakref
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import PurePath

import numpy as np
import pandas as pd

from engine import config as engine_config
from engine import eta as engine_eta
from engine import rank as engine_rank
from engine.load import DataError, Frames, load_frames

log = logging.getLogger(__name__)

EAT = timezone(timedelta(hours=3), "EAT")  # East Africa Time, no daylight saving
CENTRE_TYPE = "regional_blood_centre"
SATELLITE_PREFIX = "SAT-"
MODES = ("model", "baseline")
MAX_UNITS = 100  # more than this in one emergency request is almost certainly a typo
MAX_LIMIT_H = 72.0
MAX_TOP_N = 10
RETRY_AFTER_S = 30.0  # after a failed load, wait this long before trying again
LOAD_WAIT_S = 20.0  # how long a request waits for a load that is already running
# Minus signs people paste for Rh negative (minus sign, en dash and look-alikes) -> "-".
_DASHES = str.maketrans(dict.fromkeys("\u2212\u2013\u2010\u2011\u2012\u2014\ufe63\uff0d", "-"))
FALLBACK_MODEL_NOTE = "No fitted arrival model found: time ranges use rough defaults."
# An absolute path in an error message. Relative text such as scripts/build_db.py or backend/ is left alone.
_ABS_PATH = re.compile(r"(?<![\w.~-])/[^\s'\"`]*[^\s'\"`.,;:)]")


class EngineUnavailable(Exception):
    """The engine's data cannot be loaded right now (HTTP 503 engine_unavailable)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidRequest(ValueError):
    """The input breaks the API contract or the engine's input rules (HTTP 400 invalid_request)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# --------------------------------------------------------------------------- JSON safety


def plain(value):
    """Plain JSON types only: numpy and pandas scalars become Python values, NaN and infinity null."""
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _text(value) -> str | None:
    value = plain(value)
    return None if value is None else str(value)


def _number(value, digits: int | None = None) -> float | None:
    value = plain(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), digits) if digits is not None else float(value)


# --------------------------------------------------------------------------- input


def to_eat(value) -> datetime:
    """ISO 8601 text (or a datetime) -> naive East Africa Time. Naive input is already EAT."""
    bad = InvalidRequest('requested_at must be an ISO 8601 date and time, e.g. "2026-10-31T00:58:00".')
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            raise bad from None
    else:
        raise bad
    try:
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(EAT).replace(tzinfo=None)
    except (OverflowError, ValueError):
        raise bad from None
    if not 2000 <= parsed.year <= 2100:
        raise InvalidRequest("requested_at must be between the years 2000 and 2100.")
    return parsed


def default_requested_at(demo_clock=None) -> datetime:
    """The request time when none is given: env DEMO_CLOCK, else the settings file's
    demo_clock, else now in East Africa Time."""
    for name, value in (("DEMO_CLOCK", os.environ.get("DEMO_CLOCK")), ("demo_clock", demo_clock)):
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        try:
            return to_eat(value)
        except InvalidRequest:
            log.warning("Ignoring %s=%r: not an ISO 8601 date and time.", name, value)
    return datetime.now(EAT).replace(tzinfo=None, microsecond=0)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _optional(payload: dict, key: str, default):
    value = payload.get(key)
    return default if value is None else value


@dataclass(frozen=True)
class RankInput:
    """A checked request body. Only these fields ever reach the engine or the store."""

    facility_id: str
    patient_group: str  # minus signs normalised; the engine checks the group itself
    units_needed: int
    component: str
    requested_at: str  # naive ISO 8601, East Africa Time
    limit_h: float | None  # None: the engine config's clinician_limit_h
    mode: str
    top_n: int

    def engine_request(self) -> dict:
        return {
            "facility_id": self.facility_id,
            "patient_group": self.patient_group,
            "units_needed": self.units_needed,
            "component": self.component,
            "requested_at": self.requested_at,
        }


def parse_rank_input(payload, *, demo_clock=None) -> RankInput:
    """Check a RankInput body (raises InvalidRequest). Unknown fields are dropped here."""
    if not isinstance(payload, dict):
        raise InvalidRequest("Send the request as a JSON object.")

    facility_id = payload.get("facility_id")
    if not isinstance(facility_id, str) or not facility_id.strip():
        raise InvalidRequest('facility_id is required: the requesting facility, e.g. "HSP-004".')

    group = payload.get("patient_group")
    if not isinstance(group, str) or not group.strip():
        raise InvalidRequest("patient_group is required: O-, O+, A-, A+, B-, B+, AB-, AB+ or unknown.")

    units = payload.get("units_needed")
    if not _is_int(units) or not 1 <= units <= MAX_UNITS:
        raise InvalidRequest(f"units_needed must be a whole number from 1 to {MAX_UNITS}.")

    component = _optional(payload, "component", "RBC")
    if not isinstance(component, str):
        raise InvalidRequest('component must be text, e.g. "RBC".')

    requested_at = payload.get("requested_at")
    if requested_at is None:
        when = default_requested_at(demo_clock)
    elif isinstance(requested_at, str):
        when = to_eat(requested_at)
    else:
        raise InvalidRequest('requested_at must be an ISO 8601 date and time, e.g. "2026-10-31T00:58:00".')

    limit_h = payload.get("limit_h")
    if limit_h is not None:
        if isinstance(limit_h, bool) or not isinstance(limit_h, (int, float)) or not 0 < limit_h <= MAX_LIMIT_H:
            raise InvalidRequest(f"limit_h must be a number of hours above 0 and at most {MAX_LIMIT_H:g}.")
        limit_h = float(limit_h)

    mode = _optional(payload, "mode", "model")
    if mode not in MODES:
        raise InvalidRequest('mode must be "model" or "baseline".')

    top_n = _optional(payload, "top_n", 5)
    if not _is_int(top_n) or not 1 <= top_n <= MAX_TOP_N:
        raise InvalidRequest(f"top_n must be a whole number from 1 to {MAX_TOP_N}.")

    return RankInput(
        facility_id=facility_id.strip(),
        patient_group=group.translate(_DASHES),
        units_needed=units,
        component=component.strip().upper(),
        requested_at=when.isoformat(),
        limit_h=limit_h,
        mode=mode,
        top_n=top_n,
    )


# --------------------------------------------------------------------------- facilities


def facility_json(facility_id: str, row: dict) -> dict:
    """One facility for the API (contract type Facility)."""
    is_centre = row.get("facility_type") == CENTRE_TYPE
    is_satellite = facility_id.startswith(SATELLITE_PREFIX)
    return {
        "facility_id": facility_id,
        "name": _text(row.get("name")),
        "facility_type": _text(row.get("facility_type")),
        "is_hospital": not (is_centre or is_satellite),
        "is_centre": is_centre,
        "is_satellite": is_satellite,
        "county": _text(row.get("county")),
        "lat": _number(row.get("lat")),
        "lon": _number(row.get("lon")),
        "supply_centre_id": _text(row.get("supply_centre_id")),
        "connectivity": _text(row.get("connectivity")),
        "has_backup_power": bool(plain(row.get("has_blood_fridge_backup_power"))),
    }


def _brief(frames: Frames, facility_id: str) -> dict:
    row = frames.facility_info.get(facility_id, {})
    return {
        "facility_id": facility_id,
        "name": _text(row.get("name")),
        "facility_type": _text(row.get("facility_type")),
        "county": _text(row.get("county")),
        "lat": _number(row.get("lat")),
        "lon": _number(row.get("lon")),
    }


def _site(frames: Frames, facility_id: str, requester_id: str) -> dict:
    """A supplying site, with its road distance and map time to the requester."""
    route = (facility_id, requester_id)  # routes are keyed (from, to)
    return {
        **_brief(frames, facility_id),
        "road_km": _number(frames.road_km.get(route), 1),
        "travel_hours_map": _number(frames.travel_hours.get(route), 2),  # rounded like the engine's options
    }


def _reason(exc: BaseException) -> str:
    """The failure in plain words, without the server's folders: /api/health shows it to anyone.
    Paths inside the repo become relative; any other absolute path keeps only its last part."""
    full = str(exc).strip() or type(exc).__name__
    log.warning("Engine data problem: %s", full)  # the operator's log keeps the folders
    text = full.replace(str(engine_config.REPO_ROOT) + os.sep, "")
    text = _ABS_PATH.sub(lambda m: PurePath(m.group(0)).name, text)
    if isinstance(exc, (engine_config.ConfigError, FileNotFoundError, DataError)):
        return text
    return f"Cannot read the engine data: {text}"


# --------------------------------------------------------------------------- service


def _reset_after_fork(ref: weakref.ref) -> None:
    """A forked worker (e.g. gunicorn --preload) copies a lock held by a loading thread that
    does not exist in the worker. Start again there with a fresh lock."""
    service = ref()
    if service is not None:
        service._lock = threading.Lock()
        if service._parts is None and service._state == "loading":
            service._state, service._message = "idle", None


class EngineService:
    """Loads the engine data once (lazily, thread-safe) and answers the API's calls with it.

    State: idle -> loading -> ready | error. After an error, a later call tries again, at
    most once every ``retry_after_s`` seconds. Pass ``frames`` (and ``config``,
    ``eta_model``) to start ready, with no disk access; tests do this.
    """

    def __init__(
        self,
        *,
        country: str | None = None,
        config: dict | None = None,
        frames: Frames | None = None,
        eta_model: engine_eta.EtaModel | None = None,
        retry_after_s: float = RETRY_AFTER_S,
        load_wait_s: float = LOAD_WAIT_S,
    ):
        self.country = country or os.environ.get("ENGINE_COUNTRY") or "kenya"
        self.retry_after_s = retry_after_s
        self.load_wait_s = load_wait_s
        self._lock = threading.Lock()
        self._config = config
        self._parts: tuple[dict, Frames, engine_eta.EtaModel] | None = None
        self._state = "idle"
        self._message: str | None = None
        self._failed_at = 0.0
        if hasattr(os, "register_at_fork"):
            os.register_at_fork(after_in_child=functools.partial(_reset_after_fork, weakref.ref(self)))
        if frames is not None:
            cfg = config if config is not None else engine_config.load_config(self.country)
            self._set_ready(cfg, frames, eta_model if eta_model is not None else engine_eta.EtaModel.fallback())

    # ------------------------------------------------------------------ loading

    def _set_ready(self, config: dict, frames: Frames, eta_model: engine_eta.EtaModel) -> None:
        self._message = None if eta_model.model_used else FALLBACK_MODEL_NOTE
        self._parts = (config, frames, eta_model)
        self._state = "ready"

    def _load(self) -> None:
        """Read config, data and arrival model. Called with the lock held."""
        self._state, self._message = "loading", "Loading the engine data."
        try:
            config = self._config if self._config is not None else engine_config.load_config(self.country)
            frames = load_frames(engine_config.db_path())
            try:
                model_path = engine_config.eta_model_path()
            except engine_config.ConfigError:  # ENGINE_DB_PATH set without DATA_DIR
                model_path = None
            eta_model = engine_eta.load_model(model_path)
        except (engine_config.ConfigError, FileNotFoundError, DataError, OSError, sqlite3.Error, ValueError) as exc:
            self._fail(_reason(exc))
        except Exception as exc:  # noqa: BLE001 - never leave the state stuck at "loading"
            log.exception("Loading the engine data failed")
            self._fail(f"Loading the engine data failed ({type(exc).__name__}).")
        else:
            self._set_ready(config, frames, eta_model)
            log.info("Engine data loaded: %s.", self.status())

    def _fail(self, message: str) -> None:
        log.warning("Engine unavailable: %s", message)
        self._state, self._message, self._failed_at = "error", message, time.monotonic()

    def _loaded(self) -> tuple[dict, Frames, engine_eta.EtaModel]:
        """(config, frames, eta_model), loading them on first use. Raises EngineUnavailable."""
        parts = self._parts
        if parts is not None:
            return parts
        # The message is the reason only, as in status(): the screens add "use the phone process".
        lock = self._lock
        if not lock.acquire(timeout=self.load_wait_s):
            raise EngineUnavailable("Still loading the engine data; try again in a moment.")
        try:
            if self._parts is None:
                too_soon = self._state == "error" and time.monotonic() - self._failed_at < self.retry_after_s
                if not too_soon:
                    self._load()
            if self._parts is None:
                raise EngineUnavailable(self._message or "The engine data could not be loaded.")
            return self._parts
        finally:
            lock.release()

    def warm_up(self) -> None:
        """Load the data and rank one request, so the first real request is fast. Never raises."""
        try:
            config, frames, eta_model = self._loaded()
            info = frames.facility_info
            hospital = next((fid for fid in sorted(info) if facility_json(fid, info[fid])["is_hospital"]), None)
            if hospital and frames.stock_dates:
                engine_rank.rank_sources(
                    {"facility_id": hospital, "patient_group": "O+", "units_needed": 1, "component": "RBC",
                     "requested_at": f"{frames.stock_dates[-1]}T12:00:00"},
                    config=config, frames=frames, eta_model=eta_model,
                )
        except EngineUnavailable as exc:  # the failure itself is logged once, by _fail
            log.debug("Engine warm-up skipped: %s", exc.message)
        except Exception:  # noqa: BLE001 - a warm-up must never take the app down
            log.exception("Engine warm-up failed")

    # ------------------------------------------------------------------ API

    def status(self) -> dict:
        """EngineStatus for /api/health. Never blocks and never loads anything."""
        parts = self._parts
        dates = parts[1].stock_dates if parts else ()
        return {
            "state": "ready" if parts else self._state,
            "model_used": bool(parts[2].model_used) if parts else None,
            "stock_first": str(dates[0]) if dates else None,
            "stock_last": str(dates[-1]) if dates else None,
            "message": self._message,
        }

    def facilities(self) -> list[dict]:
        _, frames, _ = self._loaded()
        rows = [facility_json(fid, row) for fid, row in frames.facility_info.items()]
        return sorted(rows, key=lambda f: ((f["name"] or "").casefold(), f["facility_id"]))

    def facility_names(self) -> dict[str, str | None]:
        _, frames, _ = self._loaded()
        return {fid: _text(row.get("name")) for fid, row in frames.facility_info.items()}

    def rank(self, payload: RankInput | dict, *, demo_clock=None) -> dict:
        """Rank one request and return the RankResult: the engine's JSON untouched under
        "ranking", plus the limit used and the requester's and sites' names and positions."""
        asked = payload if isinstance(payload, RankInput) else parse_rank_input(payload, demo_clock=demo_clock)
        config, frames, eta_model = self._loaded()
        # Spec section 6: the first day uses its own closing count, but before it there is no count at all.
        first = str(frames.stock_dates[0]) if frames.stock_dates else None
        if first and asked.requested_at[:10] < first:
            raise InvalidRequest(
                f"There is no stock count before {first}, so a request at {asked.requested_at} cannot be ranked. "
                "Check the request date."
            )
        if asked.limit_h is not None:
            config = {**config, "clinician_limit_h": asked.limit_h}
        try:
            ranking = engine_rank.rank_sources(
                asked.engine_request(), mode=asked.mode, top_n=asked.top_n,
                config=config, frames=frames, eta_model=eta_model,
            )
        except ValueError as exc:  # the engine's plain message for bad input
            raise InvalidRequest(str(exc)) from exc

        requester_id = ranking["request"]["facility_id"]
        site_ids = [o["facility_id"] for o in ranking["options"]]
        if ranking["baseline"]["facility_id"]:
            site_ids.append(ranking["baseline"]["facility_id"])
        return plain({
            "ranking": ranking,
            "clinician_limit_h": config["clinician_limit_h"],
            "requester": _brief(frames, requester_id),
            "sites": {fid: _site(frames, fid, requester_id) for fid in dict.fromkeys(site_ids)},
        })
