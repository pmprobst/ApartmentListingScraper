"""
Schema definitions for Claude-extracted listing fields.

This module intentionally focuses on a small, high-value subset of fields
that you care about for apartment hunting right now:

- washer_dryer
- renter_paid_fees
- availability
- pet_policy
- roommates

All fields are optional at runtime and are persisted to dedicated columns
on the `listings` table (e.g. `washer_dryer`, `renter_paid_fees`, etc.).
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


WasherDryer = Literal[
    "in_unit",
    "hookups_only",
    "shared_laundry",
    "laundry_in_building",
    "coin_op_on_site",
    "no_laundry",
    "not_mentioned",
]


class ClaudeExtraction(TypedDict, total=False):
    """
    Structured fields extracted from a rental listing by Claude.

    All keys are optional; missing keys and explicit `None` values are both
    treated as \"unknown / not mentioned\".
    """

    washer_dryer: NotRequired[WasherDryer | None]
    renter_paid_fees: NotRequired[list[str] | None]
    availability: NotRequired[str | None]
    pet_policy: NotRequired[str | None]
    roommates: NotRequired[str | None]

