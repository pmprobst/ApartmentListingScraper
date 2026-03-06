"""
DB-backed extraction pipeline: Stage 1 (regex) and Stage 2 (LLM) queue.

Listings with description and llm_extraction_status IS NULL are candidates for regex.
After regex, rows with _needs_llm get llm_extraction_status = 'pending'.
Process script selects pending, calls Claude, writes results, sets 'done'.
"""

from __future__ import annotations

import json
from typing import Any

from .db import get_connection, update_listing_extraction
from .extraction_regex import run_stage1


def get_listings_needing_regex(conn=None, db_path: str | None = None):
    """Listings that have description but have not been through extraction yet."""
    if conn is None:
        conn = get_connection(db_path or "listings.db")
    return conn.execute(
        """
        SELECT id, title, description, beds, baths
        FROM listings
        WHERE description IS NOT NULL AND description != ''
          AND llm_extraction_status IS NULL
        ORDER BY id
        """
    ).fetchall()


def get_listings_pending_llm(conn=None, limit: int = 5, db_path: str | None = None):
    """Listings queued for LLM (regex already run, _needs_llm was True)."""
    if conn is None:
        conn = get_connection(db_path or "listings.db")
    return conn.execute(
        """
        SELECT id, title, description, beds, baths, in_unit_washer_dryer,
               has_roommates, gender_preference, utilities_included,
               non_included_utilities_cost, lease_length
        FROM listings
        WHERE llm_extraction_status = 'pending'
        ORDER BY id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def stage1_to_db_values(s1: dict) -> dict[str, Any]:
    """Convert run_stage1() output to kwargs for update_listing_extraction."""
    def bool_to_int(v):
        if v is None:
            return None
        return 1 if v else 0

    utilities = s1.get("utilities_included")
    if isinstance(utilities, list):
        utilities_str = json.dumps(utilities)
    else:
        utilities_str = utilities  # "all" or None

    return {
        "beds": s1.get("bedrooms") if s1.get("bedrooms") is not None else None,
        "baths": s1.get("bathrooms") if s1.get("bathrooms") is not None else None,
        "in_unit_washer_dryer": bool_to_int(s1.get("in_unit_washer_dryer")),
        "has_roommates": bool_to_int(s1.get("has_roommates")),
        "gender_preference": s1.get("gender_preference") or None,
        "utilities_included": utilities_str,
        "non_included_utilities_cost": s1.get("non_included_utilities_cost"),
        "lease_length": s1.get("lease_length"),
        "llm_extraction_status": "pending" if s1.get("_needs_llm") else "done",
    }


def row_to_stage1_prefill(row) -> dict:
    """Build a stage1-like dict from a DB row for Claude pre-fill."""
    return {
        "bedrooms": row["beds"],
        "bathrooms": row["baths"],
        "in_unit_washer_dryer": None if row["in_unit_washer_dryer"] is None else bool(row["in_unit_washer_dryer"]),
        "has_roommates": None if row["has_roommates"] is None else bool(row["has_roommates"]),
        "gender_preference": row["gender_preference"] or "any",
        "utilities_included": _parse_utilities_included(row["utilities_included"]),
        "non_included_utilities_cost": row["non_included_utilities_cost"],
        "lease_length": row["lease_length"],
    }


def _parse_utilities_included(val) -> list | str | None:
    if val is None or val == "":
        return None
    if val == "all":
        return "all"
    try:
        return json.loads(val)
    except (TypeError, json.JSONDecodeError):
        return val


def llm_result_to_db_values(llm_out: dict) -> dict[str, Any]:
    """Convert Claude batch response item to kwargs for update_listing_extraction."""
    def bool_to_int(v):
        if v is None:
            return None
        if isinstance(v, bool):
            return 1 if v else 0
        return v

    utilities = llm_out.get("utilities_included")
    if isinstance(utilities, list):
        utilities_str = json.dumps(utilities)
    else:
        utilities_str = str(utilities) if utilities is not None else None

    return {
        "beds": llm_out.get("bedrooms"),
        "baths": llm_out.get("bathrooms"),
        "in_unit_washer_dryer": bool_to_int(llm_out.get("in_unit_washer_dryer")),
        "has_roommates": bool_to_int(llm_out.get("has_roommates")),
        "gender_preference": llm_out.get("gender_preference"),
        "utilities_included": utilities_str,
        "non_included_utilities_cost": llm_out.get("non_included_utilities_cost"),
        "lease_length": llm_out.get("lease_length"),
        "llm_extraction_status": "done",
    }


def run_regex_and_update(conn, listing_id: int, title: str, description: str) -> None:
    """Run Stage 1 on one listing and write results to DB."""
    s1 = run_stage1(title, description or "")
    values = stage1_to_db_values(s1)
    update_listing_extraction(conn, listing_id, **values)
