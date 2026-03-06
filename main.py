"""
Pipeline orchestrator for Utah Valley Rental Skimmer.

High-level flow:
1. Ingest downloaded Bright Data snapshots into SQLite.
2. Build HTML (first pass).
3. Run extraction: regex on listings with description, then Claude on queue until empty.
4. Build the static HTML page from the enriched listings.

This script is designed to be run locally or from GitHub Actions.
See CLAUDE.md for additional context and commands.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from uvrental.build_page import build_page
from uvrental.ingest import ingest_all_downloaded_from_history
from uvrental.extraction_pipeline import run_initiate_phase, run_process_until_empty

load_dotenv()


def main() -> None:
    db_path = os.environ.get("LISTINGS_DB", "listings.db").strip() or "listings.db"

    # Step 1: ingest all downloaded snapshots into the DB.
    ingested = ingest_all_downloaded_from_history(db_path=db_path)
    print(f"Ingested {ingested} records from downloaded snapshots.")

    # Step 2: build HTML (first pass).
    build_page()
    print("Built HTML (first pass).")

    # Step 3: run extraction (regex on unprocessed, then Claude queue until empty).
    regex_count = run_initiate_phase(db_path)
    print(f"Ran regex extraction on {regex_count} listings.")
    llm_processed = run_process_until_empty(db_path)
    print(f"Processed {llm_processed} listings with Claude extraction.")

    # Step 4: final HTML from enriched listings.
    build_page()
    print("Built HTML (final).")


if __name__ == "__main__":
    main()

