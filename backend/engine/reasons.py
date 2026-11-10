"""Plain-language reasons from fixed string templates (spec sections 2 and 9).

No language model writes any text or number here. Every number in a reason is a
value the engine computed, rounded the same way as in the JSON.

Wording rules (from the council review, 2026-11-10):
- stock is always "yesterday's count ... (unconfirmed)", never stated as fact;
- a hospital's dispatch time is said to be *assumed*: the data has no hospital
  lending, so it reuses regional-centre dispatch waits;
- a hospital option says the lending hospital must agree.
"""

from __future__ import annotations

from engine import compat
from engine.stock import FLAG_LOW_CONNECTIVITY, FLAG_NO_BACKUP_POWER, FLAG_O_NEG_RESERVE

STOCK_NOTE = "Yesterday's closing count. Unconfirmed until the supplying site confirms."
BASELINE_RULE = "Supply centre first, then the nearest regional centres. Quote = map time + 2 h."

_SUPPLY = {
    "hospital": "Yesterday's count shows {spare} spare compatible {units_word} above its own safety stock (unconfirmed).",
    "centre": "Regional centre: yesterday's count shows {spare} compatible {units_word} (unconfirmed).",
}
_PARTIAL = "Can cover only {spare} of the {need} units needed."
_TIMING = (
    "About {wait} h to pack and dispatch, {road} h on the road. "
    "Most likely {p50} h; 8 in 10 arrive within {p10}-{p90} h."
)
_TIMING_HOSPITAL = (
    "Hospital dispatch time is assumed from regional-centre data{extra}: "
    "about {wait} h to pack and dispatch, {road} h on the road. "
    "Most likely {p50} h; 8 in 10 arrive within {p10}-{p90} h."
)
_TIMING_BASELINE = (
    "Past emergency deliveries like this took longer than the quote: "
    "about {wait} h to pack and dispatch, {road} h on the road. "
    "Most likely {p50} h; 8 in 10 arrive within {p10}-{p90} h."
)
_TIMING_FALLBACK = "This range uses rough defaults because no fitted arrival model was found."
_NEAR_EXPIRY = "{n} {units_word} {verb} within {days} days, so sharing them avoids waste."
_HOSPITAL_AGREES = "The lending hospital must agree before any unit moves."
_FLAGS = {
    FLAG_O_NEG_RESERVE: "It keeps its O- reserve for O- patients and women of childbearing age.",
    FLAG_NO_BACKUP_POWER: "Its blood fridge has no backup power.",
    FLAG_LOW_CONNECTIVITY: "It has 2G only, so confirmation may be slow.",
}
_BASELINE = {
    "supply": "Today's rule: this is the hospital's own supply centre, and it has enough stock.",
    "next": "Today's rule: the supply centre is short, so this is the nearest other regional centre with enough stock.",
}
_BASELINE_STOCK = "Yesterday's count shows {spare} compatible {units_word} (unconfirmed)."
_BASELINE_QUOTE = "Today's quote would be {quote} h (map time + 2 h, no range)."


def _units(n: int) -> str:
    return "unit" if n == 1 else "units"


def _h(x: float) -> str:
    return f"{x:.1f}"


def option_reason(
    option: dict,
    need: int,
    days: int,
    model_used: bool,
    patient_group: str,
    hospital_extra_h: float = 0.0,
) -> str:
    """Reason for one model-mode option. ``option`` uses the JSON field names."""
    parts = []
    spare = option["spare"]
    is_hospital = option["is_hospital"]
    parts.append(_SUPPLY["hospital" if is_hospital else "centre"].format(spare=spare, units_word=_units(spare)))
    if "partial" in option["flags"]:
        parts.append(_PARTIAL.format(spare=spare, need=need))
    if is_hospital:
        extra = f" plus {_h(hospital_extra_h)} h" if hospital_extra_h else ""
        parts.append(_timing(option["eta"], _TIMING_HOSPITAL, extra=extra))
    else:
        parts.append(_timing(option["eta"], _TIMING))
    if not model_used:
        parts.append(_TIMING_FALLBACK)
    n = option["near_expiry"]
    if n:
        parts.append(
            _NEAR_EXPIRY.format(n=n, units_word=_units(n), verb="expires" if n == 1 else "expire", days=days)
        )
    parts.extend(_FLAGS[f] for f in option["flags"] if f in _FLAGS)
    if is_hospital:
        parts.append(_HOSPITAL_AGREES)
    if compat.UNKNOWN_GROUP_FLAG in option["flags"]:
        parts.append(compat.UNKNOWN_GROUP_NOTE)
    return " ".join(parts)


def baseline_reason(option: dict, is_supply_centre: bool, quote: float, model_used: bool) -> str:
    """Reason for one baseline-mode option (always a regional centre)."""
    parts = [_BASELINE["supply" if is_supply_centre else "next"]]
    spare = option["spare"]
    parts.append(_BASELINE_STOCK.format(spare=spare, units_word=_units(spare)))
    parts.append(_BASELINE_QUOTE.format(quote=_h(quote)))
    template = _TIMING_BASELINE if option["eta"]["p50"] > quote else _TIMING
    parts.append(_timing(option["eta"], template))
    if not model_used:
        parts.append(_TIMING_FALLBACK)
    parts.extend(_FLAGS[f] for f in option["flags"] if f in _FLAGS)
    if compat.UNKNOWN_GROUP_FLAG in option["flags"]:
        parts.append(compat.UNKNOWN_GROUP_NOTE)
    return " ".join(parts)


def _timing(eta: dict, template: str, extra: str = "") -> str:
    return template.format(
        extra=extra,
        wait=_h(eta["wait_p50"]), road=_h(eta["road_p50"]),
        p50=_h(eta["p50"]), p10=_h(eta["p10"]), p90=_h(eta["p90"]),
    )
