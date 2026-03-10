"""
DB-backed extraction pipeline: Stage 1 (regex) and Stage 2 (LLM) queue.

Phase 3: Only NEW listings (first_seen >= run_start_ts) within price range
are extracted. Listings with llm_extraction_status IS NULL and non-empty
description get regex (Stage 1); rows needing more get 'pending' for Claude.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import get_db_path, get_price_min, get_price_max
from .db import get_connection, update_listing_extraction, update_run_status_after_llm
from .extraction_regex import run_stage1

log = logging.getLogger(__name__)


def _get_new_cutoff_ts(conn) -> str | None:
    """
    Return cutoff timestamp for 'new' listings: run_start_ts from run_status.
    If NULL (legacy), use last_run_ts - 3600 seconds as heuristic.
    """
    row = conn.execute(
        "SELECT run_start_ts, last_run_ts FROM run_status WHERE id = 1"
    ).fetchone()
    if not row:
        return None
    run_start = row["run_start_ts"] if "run_start_ts" in row.keys() else None
    if run_start:
        return run_start
    last_run = row["last_run_ts"] if "last_run_ts" in row.keys() else None
    if last_run:
        # SQLite: datetime(last_run_ts, '-3600 seconds')
        r = conn.execute(
            "SELECT datetime(?, '-3600 seconds') AS cutoff",
            (last_run,),
        ).fetchone()
        return r["cutoff"] if r else None
    return None


def get_listings_needing_regex(
    conn=None,
    db_path: str | None = None,
    *,
    run_start_ts: str | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
):
    """
    Listings not yet extracted (llm_extraction_status IS NULL) with non-empty
    description. Phase 3: only NEW (first_seen >= run_start_ts) and in price range.
    """
    if conn is None:
        conn = get_connection(db_path or get_db_path())
    if run_start_ts is None:
        run_start_ts = _get_new_cutoff_ts(conn)
    if price_min is None:
        price_min = get_price_min()
    if price_max is None:
        price_max = get_price_max()

    if run_start_ts is None:
        # No run status: skip extraction (no new listings to identify)
        return []

    return conn.execute(
        """
        SELECT id, title, description, beds, baths, price
        FROM listings
        WHERE llm_extraction_status IS NULL
          AND description IS NOT NULL AND TRIM(description) != ''
          AND first_seen >= ?
          AND (price IS NULL OR (price >= ? AND price <= ?))
        ORDER BY id
        """,
        (run_start_ts, price_min, price_max),
    ).fetchall()


def get_listings_pending_llm(
    conn=None,
    limit: int = 5,
    db_path: str | None = None,
    *,
    run_start_ts: str | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
):
    """
    Listings queued for LLM (llm_extraction_status = 'pending').
    Phase 3: only NEW and in price range.
    """
    if conn is None:
        conn = get_connection(db_path or get_db_path())
    if run_start_ts is None:
        run_start_ts = _get_new_cutoff_ts(conn)
    if price_min is None:
        price_min = get_price_min()
    if price_max is None:
        price_max = get_price_max()

    if run_start_ts is None:
        return []

    return conn.execute(
        """
        SELECT id, title, description, price, beds, baths, in_unit_washer_dryer,
               has_roommates, gender_preference, utilities_included,
               non_included_utilities_cost, lease_length
        FROM listings
        WHERE llm_extraction_status = 'pending'
          AND first_seen >= ?
          AND (price IS NULL OR (price >= ? AND price <= ?))
        ORDER BY id
        LIMIT ?
        """,
        (run_start_ts, price_min, price_max, limit),
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


VALID_LEASE_LENGTHS = frozenset({"summer", "summer w/ option to review", "fall/winter"})


def _normalize_lease_length(val: Any) -> str | None:
    """Return val if it's a valid lease_length option, else None."""
    if val is None or not isinstance(val, str):
        return None
    s = val.strip()
    return s if s in VALID_LEASE_LENGTHS else None


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
        "lease_length": _normalize_lease_length(llm_out.get("lease_length")),
        "llm_extraction_status": "done",
    }


def run_regex_and_update(
    conn,
    listing_id: int,
    title: str,
    description: str,
    price: float | None = None,
    db_beds: float | None = None,
) -> None:
    """Run Stage 1 on one listing and write results to DB."""
    s1 = run_stage1(title, description or "", price=price, db_beds=db_beds)
    values = stage1_to_db_values(s1)
    update_listing_extraction(conn, listing_id, **values)


def run_initiate_phase(db_path: str) -> int:
    """
    Run regex extraction on all listings that have description but no extraction yet.
    Returns the number of listings processed.
    """
    log.info("Extraction phase started (regex then Claude).")
    conn = get_connection(db_path)
    try:
        rows = get_listings_needing_regex(conn)
        log.info("Regex phase: %d listings to process", len(rows))
        for r in rows:
            run_regex_and_update(
                conn,
                r["id"],
                r["title"] or "",
                r["description"] or "",
                r["price"],
                r["beds"],
            )
        return len(rows)
    finally:
        conn.close()


def run_process_until_empty(db_path: str, batch_size: int = 5) -> int:
    """
    Process the LLM queue until no listings have llm_extraction_status = 'pending'.
    Calls Claude in batches, updates DB, updates run_status.llm_processed, builds HTML.
    Returns total number of listings processed by Claude in this run.
    """
    from .extraction_claude import call_claude_batch, call_claude

    total_processed = 0
    while True:
        conn = get_connection(db_path)
        try:
            rows = get_listings_pending_llm(conn, limit=batch_size, db_path=db_path)
            if not rows:
                break
            log.info("Claude batch: processing %d pending listings", len(rows))
        finally:
            conn.close()

        batch = [
            {
                "title": r["title"] or "",
                "description": r["description"] or "",
                "stage1": run_stage1(
                    r["title"] or "",
                    r["description"] or "",
                    price=r.get("price"),
                    db_beds=r.get("beds"),
                ),
            }
            for r in rows
        ]
        try:
            llm_results = call_claude_batch(batch)
        except Exception as e:
            log.warning("Claude batch failed (%s), falling back to single-item calls", e)
            llm_results = []
            for item in batch:
                try:
                    out = call_claude(
                        item["title"], item["description"], item["stage1"]
                    )
                    llm_results.append(out)
                except Exception as e2:
                    log.warning("Claude single-item failed: %s", e2)
                    llm_results.append({})
        conn = get_connection(db_path)
        try:
            for row, llm_out in zip(rows, llm_results):
                if llm_out:
                    values = llm_result_to_db_values(llm_out)
                    update_listing_extraction(conn, row["id"], **values)
            count = sum(1 for o in llm_results if o)
            total_processed += count
        finally:
            conn.close()

    if total_processed:
        conn = get_connection(db_path)
        try:
            update_run_status_after_llm(conn, llm_processed=total_processed)
        finally:
            conn.close()
    log.info("Extraction phase complete: %d listings processed by Claude.", total_processed)
    return total_processed
