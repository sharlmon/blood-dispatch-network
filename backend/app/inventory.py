"""Shared availability arithmetic for operational RBC ranking and reservation."""


def available_units(row, snapshot_cap=None):
    """Never lend safety stock or units already allocated to another request.

    A ranking cap is already net of the reservations present when it was made.
    Compare it with current free stock; do not subtract those reservations twice.
    """
    available = max(0, row['on_hand'] - row['safety_stock'] - row['reserved'])
    return available if snapshot_cap is None else min(available, max(0, snapshot_cap))
