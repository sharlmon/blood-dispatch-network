"""Compare policies on identical historical stock snapshots without future data.

The reference provider is deliberately conservative: exact group and component
only. It is an offline comparator, not the production compatibility/ranking engine.
Inject an adapter around DS1's engine to evaluate its approved rules unchanged.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Mapping, Protocol, Sequence

from engine.arrival import ArrivalModel, estimate_arrival
from engine.dataset import Dataset, Row, local_datetime

GROUPS = frozenset(("O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"))


@dataclass(frozen=True)
class Candidate:
    """A source already screened by the provider's eligibility/stock rules."""

    facility_id: str
    available_units: int
    travel_hours: float
    road_km: float
    source_kind: str = "centre"

    def __post_init__(self):
        if not isinstance(self.facility_id, str) or not self.facility_id.strip():
            raise ValueError("Candidate facility_id must be a nonempty string")
        if (isinstance(self.available_units, bool) or not isinstance(self.available_units, int)
                or self.available_units < 0 or self.source_kind not in {"centre", "hospital"}):
            raise ValueError("Invalid available units or source kind")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
               for v in (self.travel_hours, self.road_km)):
            raise ValueError("Candidate travel and distance must be finite and nonnegative")


class CandidateProvider(Protocol):
    def __call__(self, request: Row, as_of: datetime, *, include_hospitals: bool) -> Sequence[Candidate]:
        """Return ALL eligible sources, not top-N, using information available at as_of."""
        ...


class ReferenceCandidateProvider:
    """Exact-match snapshot comparator, with opt-in research-only hospital reserves.

    No default hospital reserve is invented. A group absent from the configured
    reserve map cannot lend. O-negative lending is excluded in this comparator;
    the production engine owns its reviewed reserve and patient-specific rules.
    """

    def __init__(self, dataset: Dataset, settings: Mapping | None = None):
        self.dataset = dataset
        self.settings = settings or {}
        self.reserves = self.settings.get("replay", {}).get("hospital_reserve_units", {})
        if any(group not in GROUPS or not isinstance(count, int) or isinstance(count, bool) or count < 0
               for group, count in self.reserves.items()):
            raise ValueError("Replay hospital reserves must map known groups to nonnegative integers")

    def __call__(self, request: Row, as_of: datetime, *, include_hospitals: bool) -> list[Candidate]:
        previous_day = as_of.date() - timedelta(days=1)
        group = request["patient_blood_group"]
        component = request["component_requested"]
        candidates = []
        for facility_id, facility in self.dataset.facilities.items():
            if facility_id == request["facility_id"]:
                continue
            hospital = facility_id.startswith("HSP-")
            centre = facility.get("facility_type") == "regional_blood_centre"
            if not centre and not (hospital and include_hospitals and
                                   self.settings.get("lending", {}).get("enabled", True)):
                continue
            reserve = 0
            if hospital:
                if group == "O-" or group not in self.reserves:
                    continue
                reserve = self.reserves[group]
            stock = self.dataset.stock.get((previous_day, facility_id, component, group))
            route = self.dataset.routes.get((facility_id, request["facility_id"]))
            if stock is None or route is None or stock <= reserve:
                continue
            candidates.append(Candidate(facility_id, stock - reserve,
                                        float(route["typical_travel_hours"]), float(route["road_km"]),
                                        "hospital" if hospital else "centre"))
        return candidates


def _summary(outcomes: list[dict], deadline: float) -> dict:
    selected = [row for row in outcomes if row["arrival"] is not None]
    full = [row for row in selected if row["full"]]
    times = [row["arrival"]["p50_hours"] for row in full]
    return {
        "evaluated_requests": len(outcomes),
        "full_source_found": len(full),
        "partial_source_only": sum(not row["full"] for row in selected),
        "no_source_found": len(outcomes) - len(selected),
        "full_source_p50_within_deadline": sum(t <= deadline for t in times),
        "full_source_p90_within_deadline": sum(row["arrival"]["p90_hours"] is not None and
                                               row["arrival"]["p90_hours"] <= deadline for row in full),
        "median_p50_hours_full_sources": median(times) if times else None,
        "mean_p50_hours_full_sources": mean(times) if times else None,
        "previously_unfulfilled_p50_opportunities": sum(row["was_unfulfilled"] and
            row["arrival"]["p50_hours"] <= deadline for row in full),
        "hospital_sources_selected": sum(row["source_kind"] == "hospital" for row in full),
    }


def run_replay(dataset: Dataset, *, start: datetime, end: datetime,
               model: ArrivalModel | None = None, settings: Mapping | None = None,
               candidate_provider: CandidateProvider | None = None) -> dict:
    """Independent-request feasibility ladder, NOT an inventory-constrained simulation.

    Requests are selected using their prior-day requesting-site snapshot, never
    their observed units_from_local_stock. Every source must cover the entire
    request; local stock is not assumed to remain available at submission time.
    """
    start, end = local_datetime(start), local_datetime(end)
    if start >= end:
        raise ValueError("Replay start must be earlier than end")
    settings = settings or {}
    replay_settings = settings.get("replay", {})
    deadline = float(replay_settings.get("deadline_hours", 6))
    if not math.isfinite(deadline) or deadline <= 0:
        raise ValueError("Replay deadline must be finite and positive")
    components = set(replay_settings.get("components", ["RBC"]))
    urgencies = set(replay_settings.get("urgencies", ["emergency"]))
    provider = candidate_provider if candidate_provider is not None else ReferenceCandidateProvider(dataset, settings)
    if model is not None and local_datetime(model.trained_before) > start:
        raise ValueError("Arrival model must be trained before replay begins")
    policies = ("baseline", "all_centres", "centres_and_hospitals")
    outcomes = {name: [] for name in policies}
    exclusions = Counter()
    observed = Counter()
    observed_complete_times = []
    observed_timing_exclusions = Counter()
    estimate_cache = {}
    for request in sorted(dataset.requests, key=lambda row: (row["requested_at"], row["request_id"])):
        submitted = local_datetime(request["requested_at"])
        if not start <= submitted < end:
            continue
        if request["urgency"] not in urgencies or request["component_requested"] not in components:
            exclusions["outside_configured_cohort"] += 1
            continue
        group = request["patient_blood_group"]
        if group not in GROUPS:
            exclusions["unknown_group_requires_human_review"] += 1
            continue
        own_stock = dataset.stock.get((submitted.date() - timedelta(days=1), request["facility_id"],
                                       request["component_requested"], group))
        if own_stock is None:
            exclusions["missing_requester_prior_day_snapshot"] += 1
            continue
        required = int(request["units_requested"])
        if own_stock >= required:
            exclusions["no_shortage_in_prior_day_exact_match_snapshot"] += 1
            continue
        observed[request["outcome"]] += 1
        if request["outcome"] == "fulfilled" and request.get("last_unit_available_at"):
            available = local_datetime(request["last_unit_available_at"])
            duration = (available - submitted).total_seconds() / 3600
            if available >= end:
                observed_timing_exclusions["completion_at_or_after_end"] += 1
            elif duration >= 0:
                observed_complete_times.append(duration)
            else:
                observed_timing_exclusions["negative_duration"] += 1
        candidates = list(provider(request, submitted, include_hospitals=True))
        if any(candidate.facility_id == request["facility_id"] for candidate in candidates):
            raise ValueError("Candidate provider returned the requesting facility")
        if any(candidate.facility_id not in dataset.facilities for candidate in candidates):
            raise ValueError("Candidate provider returned an unknown facility")
        if len({candidate.facility_id for candidate in candidates}) != len(candidates):
            raise ValueError("Candidate provider returned duplicate facilities")
        centres = [candidate for candidate in candidates if candidate.source_kind == "centre"]
        supplier = dataset.facilities[request["facility_id"]].get("supply_centre_id")
        # Restrict before testing stock: choosing the nearest *stocked* centres
        # would silently improve the baseline's documented two-neighbour rule.
        nearby = sorted((facility_id for facility_id, facility in dataset.facilities.items()
                         if facility.get("facility_type") == "regional_blood_centre" and facility_id != supplier
                         and (facility_id, request["facility_id"]) in dataset.routes),
                        key=lambda fid: (float(dataset.routes[(fid, request["facility_id"])]["road_km"]), fid))[:2]
        order = [supplier] + nearby
        baseline = sorted((candidate for candidate in centres if candidate.facility_id in order),
                          key=lambda candidate: order.index(candidate.facility_id))
        for policy, options in (("baseline", baseline), ("all_centres", centres),
                                ("centres_and_hospitals", candidates)):
            evaluated = []
            for candidate in options:
                cache_key = (candidate.travel_hours, candidate.source_kind)
                if cache_key not in estimate_cache:
                    estimate_cache[cache_key] = estimate_arrival(candidate.travel_hours, model=model,
                        settings=settings, source_kind=candidate.source_kind)
                evaluated.append((candidate, estimate_cache[cache_key]))
            full = [pair for pair in evaluated if pair[0].available_units >= required]
            pool = full or evaluated
            if pool:
                selected, arrival = pool[0] if policy == "baseline" else min(
                    pool, key=lambda pair: (pair[1]["p50_hours"], -pair[0].available_units, pair[0].facility_id))
                result = {"arrival": arrival, "full": selected.available_units >= required,
                          "source_kind": selected.source_kind,
                          "baseline_quote_hours": selected.travel_hours + 2 if policy == "baseline" else None}
            else:
                result = {"arrival": None, "full": False, "source_kind": None, "baseline_quote_hours": None}
            result["was_unfulfilled"] = request["outcome"] == "not_fulfilled"
            outcomes[policy].append(result)
    summaries = {name: _summary(rows, deadline) for name, rows in outcomes.items()}
    quotes = [row["baseline_quote_hours"] for row in outcomes["baseline"] if row["full"]]
    summaries["baseline"]["median_map_plus_two_quote_hours"] = median(quotes) if quotes else None
    paired = []
    for baseline, network in zip(outcomes["baseline"], outcomes["centres_and_hospitals"]):
        if baseline["full"] and network["full"]:
            paired.append(baseline["arrival"]["p50_hours"] - network["arrival"]["p50_hours"])
    return {
        "evaluation_type": "independent_request_snapshot_feasibility",
        "period": {"start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()},
        "cohort": {"components": sorted(components), "urgencies": sorted(urgencies),
                   "definition": "known group; prior-day exact-match local stock below entire requested quantity"},
        "deadline_hours": deadline, "exclusions": dict(exclusions), "policies": summaries,
        "candidate_provider": type(provider).__name__,
        "observed_outcomes_same_cohort": dict(observed),
        "observed_fully_served_median_bedside_hours": median(observed_complete_times) if observed_complete_times else None,
        "observed_fully_served_timing_count": len(observed_complete_times),
        "observed_timing_exclusions": dict(observed_timing_exclusions),
        "paired_comparison": {"requests": len(paired),
                              "mean_p50_hours_saved": mean(paired) if paired else None,
                              "median_p50_hours_saved": median(paired) if paired else None},
        "assumptions": ["All policies use the same arrival estimator; map+2 is separately reported as a quote.",
                        "Stock is yesterday's closing snapshot, not confirmed live availability.",
                        "Each request is independent; stock can be reused across requests.",
                        "Counts are feasibility opportunities, not unique patients helped or blood actually delivered.",
                        "No source confirmation or dispatch is performed; human approval remains required.",
                        "Recorded bedside durations and predicted facility-arrival durations have different endpoints."],
        "limitations": ["Reference provider uses exact component/group only, not clinical substitution or WB pooling.",
                        "Hospital lending and reserves are research assumptions; no hospital-origin training transfers exist.",
                        "Reference hospital O-negative lending is excluded; production reserve rules belong to DS1.",
                        "No depletion, expiry/quarantine reconstruction, transport capacity or confirmation failures are simulated.",
                        "Starter snapshots reconstruct location using transfer dispatch dates; shelf counts are approximate.",
                        "A single full source is required; split-source fulfilment is not evaluated."]}
