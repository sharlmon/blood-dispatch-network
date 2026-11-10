"""Plain-language reasons from fixed string templates (spec sections 2 and 9).

No language model writes any text or number here. Every number in a reason is a
value the engine computed, rounded the same way as in the JSON.
"""

from __future__ import annotations

from engine import compat
from engine.stock import FLAG_LOW_CONNECTIVITY, FLAG_NO_BACKUP_POWER, FLAG_O_NEG_RESERVE

STOCK_NOTE = "Yesterday's closing count. Unconfirmed until the supplying site confirms."
BASELINE_RULE = "Supply centre first, then the nearest regional centres. Quote = map time + 2 h."

_SUPPLY = {
    "hospital": "Has {spare} spare compatible {units_word} above its own safety stock.",
    "centre": "Regional centre with {spare} compatible {units_word} in yesterday's count.",
}
_PARTIAL = "Can cover only {spare} of the {need} units needed."
_TIMING = (
    "About {wait} h to pack and dispatch, {road} h on the road. "
    "Most likely {p50} h; 8 in 10 arrive within {p10}-{p90} h."
)
_TIMING_FALLBACK = "This range uses rough defaults because no fitted arrival model was found."
_NEAR_EXPIRY = "{n} {units_word} {verb} within {days} days, so sharing them avoids waste."
_FLAGS = {
    FLAG_O_NEG_RESERVE: "It keeps its O- reserve for O- patients and women of childbearing age.",
    FLAG_NO_BACKUP_POWER: "Its blood fridge has no backup power.",
    FLAG_LOW_CONNECTIVITY: "It has 2G only, so confirmation may be slow.",
}
_BASELINE = {
    "supply": "Today's rule: this is the hospital's own supply centre, and it has enough stock.",
    "next": "Today's rule: the supply centre is short, so this is the nearest other regional centre with enough stock.",
}
_BASELINE_QUOTE = "Today's quote would be {quote} h (map time + 2 h, no range)."


def _units(n: int) -> str:
    return "unit" if n == 1 else "units"


def _h(x: float) -> str:
    return f"{x:.1f}"


def option_reason(option: dict, need: int, days: int, model_used: bool, patient_group: str) -> str:
    """Reason for one model-mode option. ``option`` uses the JSON field names."""
    parts = []
    spare = option["spare"]
    kind = "hospital" if option["is_hospital"] else "centre"
    parts.append(_SUPPLY[kind].format(spare=spare, units_word=_units(spare)))
    if "partial" in option["flags"]:
        parts.append(_PARTIAL.format(spare=spare, need=need))
    parts.append(_timing(option["eta"]))
    if not model_used:
        parts.append(_TIMING_FALLBACK)
    n = option["near_expiry"]
    if n:
        parts.append(
            _NEAR_EXPIRY.format(n=n, units_word=_units(n), verb="expires" if n == 1 else "expire", days=days)
        )
    parts.extend(_FLAGS[f] for f in option["flags"] if f in _FLAGS)
    if compat.UNKNOWN_GROUP_FLAG in option["flags"]:
        parts.append(compat.UNKNOWN_GROUP_NOTE)
    return " ".join(parts)


def baseline_reason(option: dict, is_supply_centre: bool, quote: float, model_used: bool) -> str:
    """Reason for one baseline-mode option."""
    parts = [_BASELINE["supply" if is_supply_centre else "next"]]
    parts.append(_BASELINE_QUOTE.format(quote=_h(quote)))
    parts.append(_timing(option["eta"]))
    if not model_used:
        parts.append(_TIMING_FALLBACK)
    parts.extend(_FLAGS[f] for f in option["flags"] if f in _FLAGS)
    if compat.UNKNOWN_GROUP_FLAG in option["flags"]:
        parts.append(compat.UNKNOWN_GROUP_NOTE)
    return " ".join(parts)


def _timing(eta: dict) -> str:
    return _TIMING.format(
        wait=_h(eta["wait_p50"]), road=_h(eta["road_p50"]),
        p50=_h(eta["p50"]), p10=_h(eta["p10"]), p90=_h(eta["p90"]),
    )
