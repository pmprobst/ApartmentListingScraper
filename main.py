"""
Pipeline orchestrator for Utah Valley Rental Skimmer.

High-level flow:
1. Ingest downloaded Bright Data snapshots into SQLite.
2. Run Claude/LLM extraction over listings that need enrichment.
3. Build the static HTML page from the enriched listings.

This script is designed to be run locally or from GitHub Actions.
See CLAUDE.md for additional context and commands.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from uvrental.build_page import build_page
from uvrental.ingest import ingest_all_downloaded_from_history
from uvrental.llm_pipeline import run_llm_extraction_pass

load_dotenv()


def main() -> None:
    # Step 1: ingest all downloaded snapshots into the DB.
    db_path = os.environ.get("LISTINGS_DB", "listings.db").strip() or "listings.db"
    ingested = ingest_all_downloaded_from_history(db_path=db_path)
    print(f"Ingested {ingested} records from downloaded snapshots.")

    # Step 2: run LLM extraction over listings that need enrichment.
    # Limit can be controlled via env if desired in the future.
    llm_processed = run_llm_extraction_pass(db_path=db_path)
    print(f"Processed {llm_processed} listings with LLM extraction.")

    # Step 3: build the static HTML page from the enriched listings.
    build_page()


if __name__ == "__main__":
    main()

