"""
Claude/LLM extraction pass over listings stored in SQLite.

This module is responsible for:
- selecting listings that have not yet been enriched by the LLM, and
- calling the Claude client to extract structured fields, and
- persisting those fields into dedicated columns on the listings table, and
- updating run_status.llm_processed.

It is designed so the rest of the pipeline can call a single function with a
DB path; the function takes care of batching and status updates.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Optional, Tuple

import os

from dotenv import load_dotenv

from .db import get_connection, update_run_status_after_llm
from .claude_schema import ClaudeExtraction

load_dotenv()

LISTINGS_DB = "LISTINGS_DB"
DEFAULT_DB = "listings.db"


def _env(key: str, default: str | None = None) -> str:
    v = os.environ.get(key, default or "")
    return v.strip() if isinstance(v, str) else ""


ExtractFunc = Callable[..., Tuple[Optional[ClaudeExtraction], float]]


def _default_extract_from_text() -> ExtractFunc:
    from .claude_client import extract_from_text

    return extract_from_text


def _select_listings_for_llm(
    conn,
    *,
    limit: int | None = None,
) -> Iterable[Any]:
    """
    Select listings that have not yet been processed by the LLM.

    Strategy: process rows where all LLM columns are NULL. This keeps the step
    idempotent and avoids reprocessing already-enriched listings on each run.
    """
    sql = """
        SELECT
            id,
            source,
            source_listing_id,
            title,
            price,
            beds,
            baths,
            address_raw
        FROM listings
        WHERE washer_dryer IS NULL
          AND renter_paid_fees IS NULL
          AND availability IS NULL
          AND pet_policy IS NULL
          AND roommates IS NULL
        ORDER BY last_seen DESC, id DESC
    """
    params: tuple[Any, ...]
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params = (limit,)
    else:
        params = ()
    return conn.execute(sql, params).fetchall()


def run_llm_extraction_pass(
    db_path: str | None = None,
    *,
    limit: int | None = None,
    extract_func: ExtractFunc | None = None,
) -> int:
    """
    Run an LLM extraction pass over listings that need enrichment.

    Returns the number of listings successfully processed (i.e. for which
    the LLM returned a parsable ClaudeExtraction).

    `extract_func` is injectable to make testing easier; in production the
    default `uvrental.claude_client.extract_from_text` is used.
    """
    if db_path is None:
        db_path = _env(LISTINGS_DB, DEFAULT_DB)

    if extract_func is None:
        extract_func = _default_extract_from_text()

    conn = get_connection(db_path)
    try:
        rows = list(_select_listings_for_llm(conn, limit=limit))
        if not rows:
            return 0

        processed = 0
        for r in rows:
            extracted, _latency = extract_func(
                title=r["title"] or "",
                # Description is not stored in the DB today; we pass an empty
                # string here. In the future, when full text is available
                # during ingestion, extraction can be moved earlier in the
                # pipeline.
                description="",
                price=r["price"],
                beds=r["beds"],
                baths=r["baths"],
                address_raw=r["address_raw"],
            )
            if not extracted:
                continue

            washer_dryer = extracted.get("washer_dryer")
            renter_paid_fees = extracted.get("renter_paid_fees")
            availability = extracted.get("availability")
            pet_policy = extracted.get("pet_policy")
            roommates = extracted.get("roommates")

            renter_paid_fees_text: str | None
            if isinstance(renter_paid_fees, list):
                # Store as a JSON-like string for now; caller can parse as needed.
                import json

                renter_paid_fees_text = json.dumps(
                    [str(x) for x in renter_paid_fees],
                    ensure_ascii=False,
                    sort_keys=True,
                )
            else:
                renter_paid_fees_text = None if renter_paid_fees is None else str(
                    renter_paid_fees
                )

            conn.execute(
                """
                UPDATE listings
                SET
                    washer_dryer = ?,
                    renter_paid_fees = ?,
                    availability = ?,
                    pet_policy = ?,
                    roommates = ?
                WHERE id = ?
                """,
                (
                    washer_dryer,
                    renter_paid_fees_text,
                    availability,
                    pet_policy,
                    roommates,
                    r["id"],
                ),
            )
            processed += 1

        update_run_status_after_llm(conn, llm_processed=processed)
        return processed
    finally:
        conn.close()


if __name__ == "__main__":
    # Simple CLI for manual runs:
    #   python -m uvrental.llm_pipeline [env-configured DB]
    count = run_llm_extraction_pass()
    print(f"Processed {count} listings with LLM extraction.")

