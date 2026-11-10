"""Red cell compatibility: a fixed lookup table (spec section 5). Never a model.

The engine only uses this to decide which stock to *count*. A qualified person
crossmatches and releases every unit.
"""

from __future__ import annotations

from types import MappingProxyType

UNKNOWN = "unknown"

COMPATIBILITY_NOTE = (
    "From a fixed table. A qualified person crossmatches and releases every unit."
)
UNKNOWN_GROUP_FLAG = "group_unknown_emergency_O"
UNKNOWN_GROUP_NOTE = "Emergency group O per hospital protocol. Lab confirms before release."

# Patient group -> acceptable red cell unit groups. Copied from spec section 5.
_TABLE = {
    "O-": ("O-",),
    "O+": ("O+", "O-"),
    "A-": ("A-", "O-"),
    "A+": ("A+", "A-", "O+", "O-"),
    "B-": ("B-", "O-"),
    "B+": ("B+", "B-", "O+", "O-"),
    "AB-": ("AB-", "A-", "B-", "O-"),
    "AB+": ("AB+", "AB-", "A+", "A-", "B+", "B-", "O+", "O-"),
    # Emergency protocol: group O only (both Rh types).
    UNKNOWN: ("O-", "O+"),
}
RED_CELL_COMPATIBILITY = MappingProxyType(_TABLE)

PATIENT_GROUPS = tuple(RED_CELL_COMPATIBILITY)


def normalise_group(patient_group: str) -> str:
    """Accept 'o+', ' O+ ', 'Unknown'. Reject anything not in the table."""
    if not isinstance(patient_group, str):
        raise ValueError(f"Patient group must be text, got {patient_group!r}.")
    cleaned = patient_group.strip()
    key = UNKNOWN if cleaned.lower() == UNKNOWN else cleaned.upper()
    if key not in RED_CELL_COMPATIBILITY:
        raise ValueError(
            f"Unknown patient group {patient_group!r}. Use one of: {', '.join(PATIENT_GROUPS)}."
        )
    return key


def acceptable_unit_groups(patient_group: str) -> tuple[str, ...]:
    """Red cell unit groups a patient can receive, from the fixed table."""
    return RED_CELL_COMPATIBILITY[normalise_group(patient_group)]


def is_unknown(patient_group: str) -> bool:
    return normalise_group(patient_group) == UNKNOWN


def compatibility_flags(patient_group: str) -> list[str]:
    """Flags that the compatibility step adds to every option for this patient."""
    return [UNKNOWN_GROUP_FLAG] if is_unknown(patient_group) else []
