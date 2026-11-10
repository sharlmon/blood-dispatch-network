"""Rank candidate sources and build the JSON contract (spec sections 8 and 9).

The engine suggests; it never dispatches. People accept, change or reject.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from engine import compat, config as config_mod, eta as eta_mod, reasons, stock
from engine.load import Frames, load_frames

ADVICE_TOO_LONG = "consider_emergency_O_or_transfer"
ADVICE_NO_FULL = "no_full_source"
FLAG_PARTIAL = "partial"
SUPPORTED_COMPONENTS = ("RBC",)


@dataclass
class Scored:
    cand: stock.Candidate
    travel_hours: float
    eta: dict  # unrounded p10/p50/p90/wait_p50/road_p50


# --------------------------------------------------------------------------- inputs


def _validate_request(request: dict) -> dict:
    missing = [k for k in ("facility_id", "patient_group", "units_needed", "requested_at") if k not in request]
    if missing:
        raise ValueError(f"Request is missing {', '.join(missing)}.")
    component = request.get("component", "RBC")
    if component not in SUPPORTED_COMPONENTS:
        raise ValueError(f"Component {component!r} is out of scope; v1 ranks red cells (RBC) only.")
    need = request["units_needed"]
    if isinstance(need, bool) or not isinstance(need, int) or need < 1:
        raise ValueError(f"units_needed must be a whole number of at least 1, got {need!r}.")
    return {
        **request,
        "patient_group": compat.normalise_group(request["patient_group"]),
        "requested_at": pd.Timestamp(request["requested_at"]),
    }


def _resolve(config, frames, eta_model):
    config = config or config_mod.load_config()
    frames = frames or load_frames(config_mod.db_path())
    if eta_model is None:
        eta_model = eta_mod.load_model(config_mod.eta_model_path())
    return config, frames, eta_model


# --------------------------------------------------------------------------- scoring


def _score(frames: Frames, cands, facility_id: str, config: dict, eta_model) -> list[Scored]:
    """Attach map time and arrival range to each candidate (one batched query per lender type)."""
    routed = []
    for c in cands:
        travel = frames.travel_hours.get((c.facility_id, facility_id))
        if travel is not None:  # no road route on file: cannot quote an arrival time
            routed.append((c, travel))
    out = []
    for is_hospital in (False, True):
        group = [(c, t) for c, t in routed if c.is_hospital == is_hospital]
        if not group:
            continue
        extra = config["hospital_extra_dispatch_h"] if is_hospital else 0.0
        q = eta_model.quantiles([t for _, t in group], extra_h=extra)
        for i, (c, t) in enumerate(group):
            out.append(Scored(c, t, {k: float(v[i]) for k, v in q.items()}))
    return out


def sort_key(s: Scored):
    """Spec 8.3: quarter-hour p50, near-expiry (most first), backup power first, spare (most first)."""
    return (
        round(s.eta["p50"] * 4) / 4,
        -s.cand.near_expiry,
        not s.cand.has_backup_power,
        -s.cand.spare,
        s.cand.facility_id,  # stable tie-break so output never flickers
    )


def baseline_sources(frames: Frames, facility_id: str, need: int, scored: list[Scored]) -> list[tuple[Scored, bool]]:
    """Today's rule, in order: the supply centre if it has enough, then the other regional
    centres with enough stock, nearest by road_km first. Returns (source, is_supply_centre)."""
    supply = frames.facility_info[facility_id]["supply_centre_id"]
    centres = [s for s in scored if not s.cand.is_hospital and s.cand.spare >= need]
    out = [(s, True) for s in centres if s.cand.facility_id == supply]
    others = sorted(
        (s for s in centres if s.cand.facility_id != supply),
        key=lambda s: (frames.road_km[(s.cand.facility_id, facility_id)], s.cand.facility_id),
    )
    return out + [(s, False) for s in others]


# --------------------------------------------------------------------------- output


def _eta_json(e: dict) -> dict:
    return {
        "p10": round(e["p10"], 1),
        "p50": round(e["p50"], 1),
        "p90": round(e["p90"], 1),
        "wait_p50": round(e["wait_p50"], 1),
        "road_p50": round(e["road_p50"], 2),
    }


def _option_json(rank: int, s: Scored, extra_flags: list[str]) -> dict:
    c = s.cand
    return {
        "rank": rank,
        "facility_id": c.facility_id,
        "name": c.name,
        "facility_type": c.facility_type,
        "is_hospital": bool(c.is_hospital),
        "spare": int(c.spare),
        "stock_seen": int(c.stock_seen),
        "near_expiry": int(c.near_expiry),
        "has_backup_power": bool(c.has_backup_power),
        "connectivity": c.connectivity,
        "travel_hours_map": round(float(s.travel_hours), 2),
        "eta": _eta_json(s.eta),
        "flags": list(c.flags) + extra_flags,
        "reason": "",
        # Added 2026-11-10 (additive): spare units per compatible blood group,
        # e.g. {"O+": 21, "O-": 1}, so a clinician sees which groups would be lent.
        "spare_by_group": {g: int(n) for g, n in c.spare_by_group.items()},
    }


def _baseline_json(choice: tuple[Scored, bool] | None, config: dict) -> dict:
    if choice is None:
        return {"facility_id": None, "name": None, "quote_hours": None, "rule": reasons.BASELINE_RULE}
    s, _ = choice
    return {
        "facility_id": s.cand.facility_id,
        "name": s.cand.name,
        "quote_hours": round(eta_mod.baseline_quote(s.travel_hours, config), 1),
        "rule": reasons.BASELINE_RULE,
    }


def _advice(options: list[dict], full: bool, config: dict) -> str | None:
    # The clinical safety message wins over no_full_source (decided 2026-11-10).
    if options and options[0]["eta"]["p90"] > config["clinician_limit_h"]:
        return ADVICE_TOO_LONG
    if not full:
        return ADVICE_NO_FULL
    return None


# --------------------------------------------------------------------------- public


def rank_sources(
    request: dict,
    mode: str = "model",
    top_n: int = 5,
    config: dict | None = None,
    frames: Frames | None = None,
    eta_model: eta_mod.EtaModel | None = None,
) -> dict:
    """Rank sources for one red cell request and return the section 9 JSON as a dict.

    ``request`` = {request_id?, facility_id, patient_group, units_needed, component: "RBC",
    clinical_indication?, requested_at}. Works for any requested_at in the dataset.
    """
    if mode not in ("model", "baseline"):
        raise ValueError(f"mode must be 'model' or 'baseline', got {mode!r}.")
    if top_n < 1:
        raise ValueError("top_n must be at least 1.")
    req = _validate_request(request)
    config, frames, eta_model = _resolve(config, frames, eta_model)
    facility_id, group, need = req["facility_id"], req["patient_group"], req["units_needed"]

    as_of, cands = stock.candidates(frames, facility_id, group, req["requested_at"], config)
    scored = _score(frames, cands, facility_id, config, eta_model)
    baseline = baseline_sources(frames, facility_id, need, scored)

    if mode == "model":
        full = sorted((s for s in scored if s.cand.spare >= need), key=sort_key)
        has_full = bool(full)
        if has_full:
            picked, extra = full[:top_n], []
        else:
            picked = sorted((s for s in scored if s.cand.spare > 0), key=sort_key)[:top_n]
            extra = [FLAG_PARTIAL]
        options = [_option_json(i, s, extra) for i, s in enumerate(picked, 1)]
        for opt in options:
            opt["reason"] = reasons.option_reason(
                opt, need, config["near_expiry_days"], eta_model.model_used, group,
                hospital_extra_h=config["hospital_extra_dispatch_h"],
            )
    else:
        has_full = bool(baseline)
        options = []
        for i, (s, is_supply) in enumerate(baseline[:top_n], 1):
            opt = _option_json(i, s, [])
            opt["reason"] = reasons.baseline_reason(
                opt, is_supply, eta_mod.baseline_quote(s.travel_hours, config), eta_model.model_used
            )
            options.append(opt)

    return {
        "request": {
            "facility_id": facility_id,
            "patient_group": group,
            "units_needed": need,
            "requested_at": req["requested_at"].isoformat(),
            "as_of_stock_date": as_of,
        },
        "mode": mode,
        "model_used": bool(eta_model.model_used),
        "sharing_allowed": bool(config["sharing_allowed"]),
        "compatibility_note": compat.COMPATIBILITY_NOTE,
        "stock_note": reasons.STOCK_NOTE,
        "advice": _advice(options, has_full, config),
        "options": options,
        "baseline": _baseline_json(baseline[0] if baseline else None, config),
    }


def request_from_dataset(frames: Frames, request_id: str) -> dict:
    """Build a rank_sources() request from a row of requests.csv (used by the CLI and replay)."""
    rq = frames.requests
    row = rq[rq["request_id"] == request_id]
    if row.empty:
        raise ValueError(f"No request {request_id!r} in the dataset.")
    r = row.iloc[0]
    return {
        "request_id": r["request_id"],
        "facility_id": r["facility_id"],
        "patient_group": r["patient_blood_group"],
        "units_needed": int(r["units_requested"]),
        "component": r["component_requested"],
        "clinical_indication": r["clinical_indication"],
        "requested_at": r["requested_at"],
    }


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    """Print the ranking JSON for one request.

    Examples (from backend/, with DATA_DIR set):
        python -m engine.rank --request-id REQ-020421
        python -m engine.rank --request-id REQ-020421 --mode baseline
        python -m engine.rank --facility HSP-004 --group O+ --units 1 --at 2026-10-31T00:58
    """
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m engine.rank",
        description="Rank sources for one emergency red cell request and print the JSON.",
    )
    parser.add_argument("--request-id", help="a request_id from requests.csv, e.g. REQ-020421")
    parser.add_argument("--facility", help="requesting facility_id, e.g. HSP-004")
    parser.add_argument("--group", help="patient blood group, e.g. O+ or unknown")
    parser.add_argument("--units", type=int, help="units needed")
    parser.add_argument("--at", help="request time, e.g. 2026-10-31T00:58")
    parser.add_argument("--mode", choices=["model", "baseline"], default="model")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--country", default="kenya", help="settings file in config/ (default kenya)")
    args = parser.parse_args(argv)

    manual = [args.facility, args.group, args.units, args.at]
    if args.request_id and any(v is not None for v in manual):
        parser.error("use --request-id, or --facility/--group/--units/--at, not both")
    if not args.request_id and not all(v is not None for v in manual):
        parser.error("give --request-id, or all of --facility, --group, --units and --at")

    try:
        cfg = config_mod.load_config(args.country)
        frames = load_frames(config_mod.db_path())
        if args.request_id:
            request = request_from_dataset(frames, args.request_id)
        else:
            request = {"facility_id": args.facility, "patient_group": args.group,
                       "units_needed": args.units, "component": "RBC", "requested_at": args.at}
        out = rank_sources(request, mode=args.mode, top_n=args.top_n, config=cfg, frames=frames)
    except (ValueError, FileNotFoundError, config_mod.ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
