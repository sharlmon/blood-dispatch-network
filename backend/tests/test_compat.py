"""Step 2: fixed red cell compatibility table."""

from __future__ import annotations

import pytest

from engine import compat

ALL_EIGHT = {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"}

# Spec section 5, written out independently of compat.py.
SPEC_TABLE = {
    "O-": {"O-"},
    "O+": {"O+", "O-"},
    "A-": {"A-", "O-"},
    "A+": {"A+", "A-", "O+", "O-"},
    "B-": {"B-", "O-"},
    "B+": {"B+", "B-", "O+", "O-"},
    "AB-": {"AB-", "A-", "B-", "O-"},
    "AB+": ALL_EIGHT,
    "unknown": {"O-", "O+"},
}


def _antigens(group: str) -> tuple[set[str], bool]:
    abo, rh = group[:-1], group[-1]
    return ({"O": set(), "A": {"A"}, "B": {"B"}, "AB": {"A", "B"}}[abo], rh == "+")


def _antigen_rule(patient: str, unit: str) -> bool:
    """A unit is compatible if it carries no ABO antigen the patient lacks,
    and is Rh- unless the patient is Rh+."""
    p_abo, p_rh = _antigens(patient)
    u_abo, u_rh = _antigens(unit)
    return u_abo <= p_abo and (p_rh or not u_rh)


@pytest.mark.parametrize("patient", sorted(SPEC_TABLE))
def test_table_matches_spec(patient):
    assert set(compat.acceptable_unit_groups(patient)) == SPEC_TABLE[patient]


@pytest.mark.parametrize("patient", sorted(ALL_EIGHT))
def test_table_agrees_with_abo_rh_antigen_rule(patient):
    expected = {u for u in ALL_EIGHT if _antigen_rule(patient, u)}
    assert set(compat.acceptable_unit_groups(patient)) == expected


def test_own_group_always_first_and_no_duplicates():
    for patient in ALL_EIGHT:
        groups = compat.acceptable_unit_groups(patient)
        assert groups[0] == patient
        assert len(groups) == len(set(groups))


def test_unknown_gets_group_o_only_with_flag():
    assert set(compat.acceptable_unit_groups("unknown")) == {"O-", "O+"}
    assert compat.compatibility_flags("unknown") == ["group_unknown_emergency_O"]
    assert compat.UNKNOWN_GROUP_NOTE == (
        "Emergency group O per hospital protocol. Lab confirms before release."
    )


def test_known_groups_get_no_flag():
    for patient in ALL_EIGHT:
        assert compat.compatibility_flags(patient) == []


def test_compatibility_note_is_the_spec_text():
    assert compat.COMPATIBILITY_NOTE == (
        "From a fixed table. A qualified person crossmatches and releases every unit."
    )


@pytest.mark.parametrize("raw, expected", [("o+", "O+"), (" AB- ", "AB-"), ("Unknown", "unknown")])
def test_input_is_normalised(raw, expected):
    assert compat.normalise_group(raw) == expected


@pytest.mark.parametrize("bad", ["", "C+", "O", "A positive", None, 5])
def test_invalid_groups_are_rejected(bad):
    with pytest.raises(ValueError):
        compat.acceptable_unit_groups(bad)


def test_table_cannot_be_changed_at_runtime():
    with pytest.raises(TypeError):
        compat.RED_CELL_COMPATIBILITY["O-"] = ("A+",)
