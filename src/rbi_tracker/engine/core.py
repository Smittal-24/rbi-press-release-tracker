"""Single entry point: compare(new, previous, announcement) -> Diff."""
from __future__ import annotations

from typing import Any

from .auction import AUCTION_FAMILIES, compare_announcement, compare_result, split_item_id
from .models import Diff, Release
from .mpc import compare_mpc
from .periodic import compare_bop, compare_bulletin, compare_credit, compare_wss

_PERIODIC = {
    "wss": compare_wss,
    "bulletin": compare_bulletin,
    "bop": compare_bop,
    "sectoral_credit": compare_credit,
    "mpc_minutes": compare_mpc,
}


def _coerce(r: Release | dict[str, Any] | None) -> Release | None:
    if r is None or isinstance(r, Release):
        return r
    return Release.from_dict(r)


def compare(
    new: Release | dict[str, Any],
    previous: Release | dict[str, Any] | None = None,
    announcement: Release | dict[str, Any] | None = None,
) -> Diff:
    """Diff `new` against `previous` (the immediately preceding release of the SAME item type).

    `announcement` (optional, results only): the matching announcement, used to compare amount
    accepted against the notified amount. Raises ValueError on mismatched item types.
    """
    new, previous, announcement = _coerce(new), _coerce(previous), _coerce(announcement)
    if previous is not None and previous.item_id != new.item_id:
        raise ValueError(f"previous release is {previous.item_id!r} but new release is {new.item_id!r}")

    if new.item_id in _PERIODIC:
        return _PERIODIC[new.item_id](new, previous)

    family, kind = split_item_id(new.item_id)
    if family in AUCTION_FAMILIES and kind == "announcement":
        return compare_announcement(new, previous)
    if family in AUCTION_FAMILIES and kind == "result":
        if announcement is not None and announcement.item_id != f"{family}_announcement":
            raise ValueError(
                f"announcement must be {family}_announcement, got {announcement.item_id!r}")
        return compare_result(new, previous, announcement)
    raise ValueError(f"unknown item_id: {new.item_id!r}")
