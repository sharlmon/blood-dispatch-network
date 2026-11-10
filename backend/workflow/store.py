"""Emergency requests and their audit log, in the API's own SQLite file (DB_PATH).

The engine suggests and people decide: this module only records each request, the
ranking the lab worker saw, and every human step after it. A pick is checked against the
options that were shown. Data minimisation: only the fields below are stored, never a
patient identifier or free text (docs/DATA_PROTECTION.md).
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

EAT = timezone(timedelta(hours=3), "EAT")

STATUSES = ("open", "awaiting_shelf", "confirmed", "dispatched", "arrived", "escalated", "cancelled")
FINAL_STATUSES = frozenset({"arrived", "cancelled"})
_ESCALATE = "escalate"  # open -> escalated; any other allowed status stays as it is
_ACTIVE = frozenset({"open", "escalated", "awaiting_shelf", "confirmed", "dispatched"})

# action -> (statuses it may follow, status afterwards)
TRANSITIONS: dict[str, tuple[frozenset, str]] = {
    "pick": (frozenset({"open", "escalated", "awaiting_shelf"}), "awaiting_shelf"),
    "shelf_confirmed": (frozenset({"awaiting_shelf"}), "confirmed"),
    "dispatched": (frozenset({"confirmed"}), "dispatched"),
    "arrived": (frozenset({"dispatched"}), "arrived"),
    "not_on_shelf": (frozenset({"awaiting_shelf"}), "open"),
    "confirm_timeout": (frozenset({"awaiting_shelf"}), "open"),
    "emergency_group_o": (_ACTIVE, _ESCALATE),
    "transfer_patient": (_ACTIVE, _ESCALATE),
    "cancel": (frozenset({"open", "escalated", "awaiting_shelf", "confirmed"}), "cancelled"),
}
ACTIONS = tuple(TRANSITIONS)
# Steps about the selected site. A facility_id sent with one must name the current selection, so a
# screen that missed a re-pick cannot book a confirmation (or a "no stock") against the wrong site.
SITE_STEPS = frozenset({"shelf_confirmed", "dispatched", "arrived", "not_on_shelf", "confirm_timeout"})
_STATUS_WORDS = {"awaiting_shelf": "waiting for the shelf check"}

RECORD_FIELDS = (
    "id", "created_at", "facility_id", "facility_name", "patient_group", "units_needed", "component",
    "limit_h", "requested_at", "status", "selected_facility_id", "selected_name",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    user_id TEXT,
    created_at TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    facility_name TEXT,
    patient_group TEXT NOT NULL,
    units_needed INTEGER NOT NULL,
    component TEXT NOT NULL,
    limit_h REAL NOT NULL,
    requested_at TEXT NOT NULL,
    status TEXT NOT NULL,
    selected_facility_id TEXT,
    selected_name TEXT,
    result_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requests_org ON requests (org_id);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES requests (id),
    at TEXT NOT NULL,
    action TEXT NOT NULL,
    user_id TEXT,
    org_id TEXT,
    org_role TEXT,
    detail_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_request ON audit (request_id, id);
"""


class WorkflowError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class RequestNotFound(WorkflowError):
    """No such request for the caller's organisation (HTTP 404)."""


class InvalidEvent(WorkflowError):
    """Unknown action, a pick without a valid facility, or a facility_id that is not a site id (HTTP 400)."""


class InvalidTransition(WorkflowError):
    """The action is not possible from the request's current status, or names a site that is no
    longer the selected one (HTTP 409)."""


def new_request_id() -> str:
    return "BDN-" + secrets.token_hex(4).upper()


def _now() -> datetime:
    return datetime.now(EAT).replace(microsecond=0)


def _record(row: sqlite3.Row) -> dict:
    return {field: row[field] for field in RECORD_FIELDS}


def _entry(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "request_id": row["request_id"],
        "at": row["at"],
        "action": row["action"],
        "actor": {"user_id": row["user_id"], "org_id": row["org_id"], "org_role": row["org_role"]},
        "detail": json.loads(row["detail_json"]),
    }


class Store:
    """One SQLite connection per operation, so it is safe under Flask's threaded server.
    The file and tables are created on first use."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    # ------------------------------------------------------------------ plumbing

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if not self._schema_ready:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.path, timeout=10)
                try:
                    conn.executescript(SCHEMA)
                finally:
                    conn.close()
                self._schema_ready = True

    @contextmanager
    def _transaction(self, write: bool = False):
        """A transaction; a write takes the write lock first, so read-check-update is atomic."""
        self._ensure_schema()
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield conn
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    @staticmethod
    def _row(conn: sqlite3.Connection, request_id: str, org_id: str | None) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM requests WHERE id = ? AND org_id = ?", (request_id, org_id)).fetchone()
        if row is None:  # unknown, or another organisation's: the same answer for both
            raise RequestNotFound(f"No request {request_id} for your hospital.")
        return row

    @staticmethod
    def _trail(conn: sqlite3.Connection, request_id: str) -> list[dict]:
        rows = conn.execute("SELECT * FROM audit WHERE request_id = ? ORDER BY id", (request_id,))
        return [_entry(r) for r in rows]

    @staticmethod
    def _audit(conn, request_id: str, at: datetime, action: str, actor: dict, detail: dict) -> None:
        conn.execute(
            "INSERT INTO audit (request_id, at, action, user_id, org_id, org_role, detail_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (request_id, at.isoformat(), action, actor.get("user_id"), actor.get("org_id"),
             actor.get("org_role"), json.dumps(detail, allow_nan=False)),
        )

    @staticmethod
    def _free_id(conn: sqlite3.Connection) -> str:
        for _ in range(100):
            candidate = new_request_id()
            if conn.execute("SELECT 1 FROM requests WHERE id = ?", (candidate,)).fetchone() is None:
                return candidate
        raise RuntimeError("Could not find a free request id.")

    # ------------------------------------------------------------------ requests

    def create_request(self, result: dict, *, component: str, actor: dict) -> tuple[dict, list[dict]]:
        """Store a ranked request (status open) and its "request_created" audit entry.

        ``result`` is the RankResult the lab worker sees; the record's fields come from it.
        """
        ranking = result["ranking"]
        asked = ranking["request"]
        fields = {
            "facility_id": asked["facility_id"],
            "facility_name": (result.get("requester") or {}).get("name"),
            "patient_group": asked["patient_group"],
            "units_needed": asked["units_needed"],
            "component": component,
            "limit_h": result["clinician_limit_h"],
            "requested_at": asked["requested_at"],
        }
        detail = {
            "patient_group": fields["patient_group"],
            "units_needed": fields["units_needed"],
            "component": component,
            "limit_h": fields["limit_h"],
            "requested_at": fields["requested_at"],
            "as_of_stock_date": asked["as_of_stock_date"],
            "mode": ranking["mode"],
            "advice": ranking["advice"],
            "model_used": ranking["model_used"],
            "option_facility_ids": [o["facility_id"] for o in ranking["options"]],
            "baseline_facility_id": ranking["baseline"]["facility_id"],
        }
        with self._transaction(write=True) as conn:
            now = _now()
            request_id = self._free_id(conn)
            conn.execute(
                "INSERT INTO requests (id, org_id, user_id, created_at, facility_id, facility_name, patient_group,"
                " units_needed, component, limit_h, requested_at, status, result_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
                (request_id, actor["org_id"], actor.get("user_id"), now.isoformat(), fields["facility_id"],
                 fields["facility_name"], fields["patient_group"], fields["units_needed"], component,
                 fields["limit_h"], fields["requested_at"], json.dumps(result, allow_nan=False)),
            )
            self._audit(conn, request_id, now, "request_created", actor, detail)
            return _record(self._row(conn, request_id, actor["org_id"])), self._trail(conn, request_id)

    def list_requests(self, org_id: str, limit: int = 20) -> list[dict]:
        """The organisation's requests, newest first."""
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM requests WHERE org_id = ? ORDER BY rowid DESC LIMIT ?", (org_id, limit)
            )
            return [_record(r) for r in rows]

    def get_request(self, request_id: str, org_id: str) -> tuple[dict, dict, list[dict]]:
        """(record, stored RankResult, audit trail oldest first)."""
        with self._transaction() as conn:
            row = self._row(conn, request_id, org_id)
            return _record(row), json.loads(row["result_json"]), self._trail(conn, request_id)

    def record_event(self, request_id: str, action, facility_id=None, *, actor: dict) -> tuple[dict, list[dict]]:
        """Apply one human decision or workflow step and audit it. Returns (record, full trail).

        A site step (SITE_STEPS) may name its site with facility_id. It must be the current
        selection, or nothing is recorded (409); without one the step is about the selection.
        """
        if not isinstance(action, str) or action not in TRANSITIONS:
            what = "action is required" if action is None else f"Unknown action {action!r}"
            raise InvalidEvent(f"{what}. Use one of: {', '.join(ACTIONS)}.")
        if action == "pick" and (not isinstance(facility_id, str) or not facility_id.strip()):
            raise InvalidEvent("A pick needs the facility_id of one of the offered sites.")
        named = None  # the site a site step says it is about
        if action in SITE_STEPS and facility_id is not None:
            if not isinstance(facility_id, str) or not facility_id.strip():
                raise InvalidEvent("facility_id must name the selected site.")
            named = facility_id.strip()

        with self._transaction(write=True) as conn:
            now = _now()
            row = self._row(conn, request_id, actor.get("org_id"))
            status = row["status"]
            allowed_from, target = TRANSITIONS[action]
            if status not in allowed_from:
                raise InvalidTransition(
                    f"Cannot record {action} while the request is {_STATUS_WORDS.get(status, status)}."
                )
            if named is not None and named != row["selected_facility_id"]:  # a stale screen: write nothing
                current = row["selected_name"] or row["selected_facility_id"]
                raise InvalidTransition(
                    f"The selected site is now {current}, not {named}. Reload the request before recording this step."
                )
            new_status = ("escalated" if status == "open" else status) if target == _ESCALATE else target
            selected_id, selected_name = row["selected_facility_id"], row["selected_name"]
            detail = {"from_status": status, "to_status": new_status}

            if action == "pick":
                selected_id = facility_id.strip()
                selected_name, extra = self._offered(json.loads(row["result_json"]), selected_id)
                detail.update(facility_id=selected_id, facility_name=selected_name,
                              previous_facility_id=row["selected_facility_id"], **extra)
            elif action in ("not_on_shelf", "confirm_timeout"):
                waited = self._minutes_since_pick(conn, request_id, now)
                detail.update(previous_facility_id=selected_id, waited_minutes=waited)
                selected_id = selected_name = None  # back to the list: the next option
            else:
                detail["facility_id"] = selected_id

            conn.execute(
                "UPDATE requests SET status = ?, selected_facility_id = ?, selected_name = ? WHERE id = ?",
                (new_status, selected_id, selected_name, request_id),
            )
            self._audit(conn, request_id, now, action, actor, detail)
            return _record(self._row(conn, request_id, actor.get("org_id"))), self._trail(conn, request_id)

    @staticmethod
    def _offered(result: dict, facility_id: str) -> tuple[str | None, dict]:
        """Check a pick against what the lab worker was shown: (site name, audit detail)."""
        ranking = result["ranking"]
        options = {o["facility_id"]: o for o in ranking["options"]}
        baseline = ranking["baseline"]
        if facility_id not in options and facility_id != baseline["facility_id"]:
            raise InvalidEvent(f"{facility_id} was not offered for this request. Pick one of the listed sites.")
        site = (result.get("sites") or {}).get(facility_id) or {}
        name = site.get("name") or (options.get(facility_id) or baseline).get("name")
        rank = options[facility_id]["rank"] if facility_id in options else None
        return name, {"option_rank": rank, "is_baseline": facility_id == baseline["facility_id"]}

    @staticmethod
    def _minutes_since_pick(conn: sqlite3.Connection, request_id: str, now: datetime) -> float | None:
        row = conn.execute(
            "SELECT at FROM audit WHERE request_id = ? AND action = 'pick' ORDER BY id DESC LIMIT 1", (request_id,)
        ).fetchone()
        if row is None:
            return None
        return round((now - datetime.fromisoformat(row["at"])).total_seconds() / 60, 1)
