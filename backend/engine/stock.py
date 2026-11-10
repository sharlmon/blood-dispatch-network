"""What each candidate site holds and can spare (spec section 6).

Every figure here is the previous day's closing count. It is unconfirmed until the
supplying site checks its shelf.
"""

from __future__ import annotations

import bisect
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from engine import compat
from engine.load import Frames

REGIONAL_CENTRE = "regional_blood_centre"
SATELLITE = "satellite_blood_centre"

FLAG_NO_BACKUP_POWER = "no_backup_power"
FLAG_LOW_CONNECTIVITY = "low_connectivity_2g"
FLAG_O_NEG_RESERVE = "o_neg_reserve_applied"


@dataclass
class Candidate:
    facility_id: str
    name: str
    facility_type: str
    is_hospital: bool
    stock_seen: int  # compatible red cell units at yesterday's close
    spare: int  # of those, what the site can lend
    near_expiry: int  # spare units expiring within near_expiry_days, capped at spare
    has_backup_power: bool
    connectivity: str
    supply_centre_id: str | None
    stock_by_group: dict[str, int] = field(default_factory=dict)
    spare_by_group: dict[str, int] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- dates


def request_date(requested_at) -> pd.Timestamp:
    """Calendar day of the request (EAT, as in the dataset), at midnight."""
    ts = pd.Timestamp(requested_at)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Africa/Nairobi").tz_localize(None)
    return ts.normalize()


def as_of_date(frames: Frames, requested_at) -> str:
    """Latest closing count known at request time: request day minus one, as ISO date.

    After the dataset ends (e.g. a live demo clock) this is the last day with counts.
    Before the dataset starts there is no earlier count, so the first day is used and
    the returned date shows it.
    """
    target = (request_date(requested_at) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    dates = frames.stock_dates
    if not dates:
        raise ValueError("No stock counts loaded.")
    i = bisect.bisect_right(dates, target)
    return dates[i - 1] if i > 0 else dates[0]


# --------------------------------------------------------------------------- candidates


def candidate_ids(frames: Frames, requesting_facility: str, sharing_allowed: bool) -> list[str]:
    """Every facility except the requester and satellites; centres only if sharing is off."""
    info = frames.facility_info
    if requesting_facility not in info:
        raise ValueError(f"Unknown facility_id {requesting_facility!r}.")
    return [
        fid
        for fid, row in info.items()
        if fid != requesting_facility
        and row["facility_type"] != SATELLITE
        and (sharing_allowed or row["facility_type"] == REGIONAL_CENTRE)
    ]


def hospital_spare(
    stock: int, usual_level: int, blood_group: str, config: dict
) -> tuple[int, bool]:
    """Units a hospital can lend from one group, and whether the O- reserve was the binding limit.

    spare = max(0, stock - max(usual_level, min_keep)); for O- the hospital also never
    goes below o_neg_reserve.
    """
    keep = max(usual_level, config["min_keep"])
    reserve_applied = False
    if blood_group == "O-" and config["o_neg_reserve"] > keep:
        reserve_applied = stock > keep  # the reserve held back units the safety stock would have released
        keep = config["o_neg_reserve"]
    return max(0, stock - keep), reserve_applied


def near_expiry_counts(
    frames: Frames,
    facility_ids: list[str],
    unit_groups: tuple[str, ...],
    as_of: str,
    requested_at,
    near_expiry_days: int,
) -> dict[str, int]:
    """Compatible red cell units on each facility's shelf at as_of that expire soon.

    This approximates "on the shelf that day" from final-status data: units.csv holds
    each unit's *last* location and status, not a daily history. A unit counts if it
    was collected by as_of, left the shelf after as_of (or is still in stock), and
    expires between the request day and near_expiry_days after it. A unit that moved
    between sites after as_of is counted at its final site.
    """
    ru = frames.red_units
    day = request_date(requested_at)
    as_of_ts = np.datetime64(as_of)
    mask = (
        ru["facility_id"].isin(facility_ids).to_numpy()
        & ru["blood_group"].isin(unit_groups).to_numpy()
        & (ru["collection_date"].to_numpy() <= as_of_ts)
        & (ru["shelf_until"].to_numpy() > as_of_ts)
        & (ru["expiry_date"].to_numpy() >= day.to_datetime64())
        & (ru["expiry_date"].to_numpy() <= (day + pd.Timedelta(days=near_expiry_days)).to_datetime64())
    )
    return ru.loc[mask, "facility_id"].value_counts().to_dict()


def candidates(
    frames: Frames,
    requesting_facility: str,
    patient_group: str,
    requested_at,
    config: dict,
) -> tuple[str, list[Candidate]]:
    """All candidate sites with their compatible stock, spare and near-expiry counts.

    Returns (as_of date, candidates). Sites with zero spare are included; the ranker
    decides what is enough.
    """
    unit_groups = compat.acceptable_unit_groups(patient_group)
    as_of = as_of_date(frames, requested_at)
    ids = candidate_ids(frames, requesting_facility, config["sharing_allowed"])
    expiring = near_expiry_counts(
        frames, ids, unit_groups, as_of, requested_at, config["near_expiry_days"]
    )
    group_flags = compat.compatibility_flags(patient_group)

    out: list[Candidate] = []
    for fid in ids:
        row = frames.facility_info[fid]
        is_hospital = row["facility_type"] != REGIONAL_CENTRE
        day_stock = frames.stock.groups(as_of, fid)
        stock_by_group = {g: day_stock[g] for g in unit_groups}

        flags = list(group_flags)
        if is_hospital:
            spare_by_group = {}
            for g, units in stock_by_group.items():
                usual = frames.usual_level.get((fid, g), 0)
                spare_by_group[g], reserve_applied = hospital_spare(units, usual, g, config)
                if reserve_applied:
                    flags.append(FLAG_O_NEG_RESERVE)
        else:
            spare_by_group = dict(stock_by_group)  # a regional centre can spare all its stock

        spare = sum(spare_by_group.values())
        backup = bool(row["has_blood_fridge_backup_power"])
        if not backup:
            flags.append(FLAG_NO_BACKUP_POWER)
        if row["connectivity"] == "2G":
            flags.append(FLAG_LOW_CONNECTIVITY)

        out.append(
            Candidate(
                facility_id=fid,
                name=row["name"],
                facility_type=row["facility_type"],
                is_hospital=is_hospital,
                stock_seen=sum(stock_by_group.values()),
                spare=spare,
                near_expiry=min(expiring.get(fid, 0), spare),
                has_backup_power=backup,
                connectivity=row["connectivity"],
                supply_centre_id=row["supply_centre_id"],
                stock_by_group=stock_by_group,
                spare_by_group=spare_by_group,
                flags=flags,
            )
        )
    return as_of, out
