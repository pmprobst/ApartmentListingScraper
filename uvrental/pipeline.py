"""
High-level orchestration helpers for running the full pipeline (ingest + extraction + build).
"""

import logging

from .db import get_connection, update_run_status_after_fetch
from .build_page import build_page as build_static_page
from .ingest import LISTINGS_DB, DEFAULT_DB, _env, ingest_all_downloaded_from_history
from .extraction_pipeline import run_initiate_phase, run_process_until_empty

log = logging.getLogger(__name__)


def print_listings(db_path: str) -> None:
    """Print all listings from the DB in a readable format."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, source, source_listing_id, title, link, price, beds, baths, "
            "first_seen, last_seen FROM listings ORDER BY id"
        ).fetchall()
        if not rows:
            print("No listings in DB.")
            return
        print(f"Listing data ({len(rows)} row(s)):")
        print(
            '(Note: Marketplace links may show "Not available" if the listing was '
            "removed or sold since fetch.)"
        )
        print()
        for r in rows:
            print("-" * 60)
            print(f"  id:                  {r['id']}")
            print(f"  source:              {r['source']}")
            print(f"  source_listing_id:   {r['source_listing_id']}")
            print(f"  title:               {r['title']}")
            print(f"  link:                {r['link']}")
            print(f"  price:               {r['price']}")
            print(f"  beds:                {r['beds']}")
            print(f"  baths:               {r['baths']}")
            print(f"  first_seen:          {r['first_seen']}")
            print(f"  last_seen:           {r['last_seen']}")
            print()
    finally:
        conn.close()


def run_full_pipeline() -> None:
    """
    Run the full pipeline: ingest downloaded snapshots, build HTML, run extraction
    (regex then Claude until queue empty), then build HTML again.
    On failure, updates run_status with success=False and re-raises.
    """
    db_path = _env(LISTINGS_DB, DEFAULT_DB)
    try:
        log.info("Starting full pipeline (ingest -> build -> extraction -> build)")
        n = ingest_all_downloaded_from_history(db_path)
        log.info("Ingest complete: %d records", n)
        print(f"Ingested {n} records from downloaded snapshots.")

        build_static_page()
        log.info("Build page (first pass) complete")
        print("Built HTML (first pass).")

        regex_count = run_initiate_phase(db_path)
        log.info("Regex extraction complete: %d listings", regex_count)
        print(f"Ran regex extraction on {regex_count} listings.")
        llm_processed = run_process_until_empty(db_path)
        log.info("Claude extraction complete: %d listings", llm_processed)
        print(f"Processed {llm_processed} listings with Claude extraction.")

        build_static_page()
        log.info("Build page (final) complete")
        print("Built HTML (final).")
        log.info("Full pipeline complete")
    except Exception as e:
        log.exception("Pipeline failed: %s", e)
        try:
            conn = get_connection(db_path)
            total_count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            update_run_status_after_fetch(
                conn,
                success=False,
                scraped=0,
                thrown=0,
                duplicate=0,
                added=0,
                total_count=total_count,
            )
            conn.close()
        except Exception as e2:
            log.warning("Could not update run_status on failure: %s", e2)
        raise


# Alias for backward compatibility; same as run_full_pipeline.
run_pipeline = run_full_pipeline


if __name__ == "__main__":
    run_full_pipeline()

