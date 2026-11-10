"""Request-to-receiving-facility arrival estimates and temporal validation.

The paired empirical model keeps preparation delay and transport multiplier from
the same shipment together. It estimates receiving-facility arrival, not clinical
readiness at the bedside. Hospital lending is an explicitly labelled extrapolation.
"""

from .model import (
    ArrivalModel,
    estimate_arrival,
    evaluate_arrival_model,
    fit_arrival_model,
)

__all__ = [
    "ArrivalModel",
    "estimate_arrival",
    "evaluate_arrival_model",
    "fit_arrival_model",
]
