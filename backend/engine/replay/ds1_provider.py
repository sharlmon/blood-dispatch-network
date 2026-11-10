"""Replay adapter for DS1's candidate rules (docs/ds2-implementation.md, "Replay ladder").

DS1's engine is called unchanged: engine.stock.candidates applies the fixed
compatibility table, the previous-day snapshot and the spare-stock rules. This
module only maps its output onto the replay's Candidate records.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping

from engine import rank, stock
from engine.dataset import Row, local_datetime
from engine.load import Frames

from .runner import Candidate

# Keys DS1's stock rules read; engine.config.load_config always fills them.
CONFIG_KEYS = ("sharing_allowed", "min_keep", "o_neg_reserve", "near_expiry_days")


class DS1CandidateProvider:
    """DS1's eligibility and spare-stock rules behind the replay's CandidateProvider contract.

    How it differs from ReferenceCandidateProvider:

    - Compatible groups come from DS1's fixed table (spec section 5), not an exact
      match: an O+ patient's sources count both O+ and O- units.
    - RBC and WB are pooled as red cell supply, as DS1 v1 does. The reference counts
      the requested component only.
    - A hospital keeps max(usual_level, min_keep) units of each group and never lends
      O- below o_neg_reserve; a regional centre can lend everything. The reference
      lends from hospitals only under an explicit research reserve, and never lends O-.
    - DS1's sharing_allowed decides whether hospitals lend. The provider reads no DS2
      settings: scripts/evaluate_ds2.py folds DS2's ``lending.enabled`` into
      sharing_allowed and refuses ``replay.hospital_reserve_units``.
    - usual_level is a median over the whole year, so the replay sees some later
      information (backend/engine/README.md, "Lookahead in replay numbers").
    - DS1 v1 ranks red cells only, so a request for any other component is refused
      rather than counted as a request with no source.

    The runner still picks requests by the requester's exact-match snapshot and
    times every source with its own arrival estimator (DS1's ETA model,
    hospital_extra_dispatch_h, clinician_limit_h and baseline_quote_extra_h are not
    used; scripts/evaluate_ds2.py refuses a nonzero hospital_extra_dispatch_h), so
    both providers are compared on the same requests and the same clock.
    """

    # Replay artifacts show these in place of the runner's reference-provider notes.
    limitations = (
        "DS1 provider: compatible groups come from the fixed table, and RBC and WB are pooled as red cell supply.",
        "DS1 provider: hospitals keep max(usual level, min_keep) per group and the O-negative reserve; "
        "the usual level is a whole-year median, so replays see some later information.",
        "Requests are still selected by the requester's prior-day exact-match snapshot, "
        "so both providers are compared on the same requests.",
        "DS1 provider: every source is timed by DS2's arrival estimator against replay.deadline_hours, "
        "with no extra hospital dispatch delay, and the baseline quote is map + 2 h. DS1's ETA model, "
        "hospital_extra_dispatch_h, clinician_limit_h and baseline_quote_extra_h are not used.",
    )

    def __init__(self, frames: Frames, config: Mapping):
        missing = [key for key in CONFIG_KEYS if key not in config]
        if missing:
            raise ValueError(f"DS1 config is missing {', '.join(missing)}; use engine.config.load_config")
        self.frames = frames
        self.config = dict(config)

    def __call__(self, request: Row, as_of: datetime, *, include_hospitals: bool) -> list[Candidate]:
        """Every source with spare compatible units and a route on file, not DS1's top-N."""
        if request["component_requested"] not in rank.SUPPORTED_COMPONENTS:
            # DS1 has no stock rules for other components. Returning no candidates would
            # charge DS1 with "no source found" for requests it never ranks.
            raise ValueError("DS1 ranks red cell (RBC) requests only; set replay.components to [RBC]")
        requester = request["facility_id"]
        requested_at = local_datetime(as_of)  # naive EAT, the dataset's clock
        config = {**self.config, "sharing_allowed": self.config["sharing_allowed"] and include_hospitals}
        snapshot, sites = stock.candidates(self.frames, requester, request["patient_blood_group"],
                                           requested_at, config)
        # DS1 reads the closing count of the EAT day before the request: the replay's
        # prior-day snapshot. If that day has no count it uses the latest earlier one,
        # except before the data starts, where it would use a later count. Refuse that.
        previous_day = (requested_at.date() - timedelta(days=1)).isoformat()
        if snapshot > previous_day:
            raise ValueError(f"No stock count on or before {previous_day}; "
                             f"DS1 would use the later {snapshot} count")
        hours, km = self.frames.travel_hours, self.frames.road_km
        return [
            Candidate(site.facility_id, int(site.spare), float(hours[(site.facility_id, requester)]),
                      float(km[(site.facility_id, requester)]),
                      "hospital" if site.is_hospital else "centre")
            for site in sites
            # No route on file means no arrival time, so the site cannot be offered.
            if site.spare > 0 and (site.facility_id, requester) in hours
        ]
