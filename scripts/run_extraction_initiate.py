#!/usr/bin/env python3
"""
Option B initiate: ingest snapshots, build HTML #1, run regex on unprocessed
listings and enqueue those that need LLM, then build HTML #2.

Run after snapshots are downloaded. Then run run_extraction_process.py
repeatedly until the LLM queue is empty.

Usage:
    python scripts/run_extraction_initiate.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uvrental.db import get_connection
from uvrental.build_page import build_page
from uvrental.ingest import ingest_all_downloaded_from_history, _env, LISTINGS_DB, DEFAULT_DB
from uvrental.extraction_pipeline import (
    get_listings_needing_regex,
    run_regex_and_update,
)


def main() -> None:
    db_path = _env(LISTINGS_DB, DEFAULT_DB)
    print("Step 1: Ingesting downloaded snapshots into DB...")
    n = ingest_all_downloaded_from_history(db_path=db_path)
    print(f"Ingested {n} records.\n")

    print("Step 2: Building HTML (first time, after ingest)...")
    build_page()
    print("HTML built (docs/index.html).\n")

    conn = get_connection(db_path)
    try:
        rows = get_listings_needing_regex(conn)
        if not rows:
            print("Step 3: No listings need regex extraction (all processed or no description).")
            return
        print(f"Step 3: Running regex extraction on {len(rows)} listings...")
        for r in rows:
            run_regex_and_update(
                conn,
                r["id"],
                r["title"] or "",
                r["description"] or "",
            )
        print("Regex extraction done.")
    finally:
        conn.close()

    print("\nStep 4: Building HTML (second time, after regex)...")
    build_page()
    print("HTML built. Run scripts/run_extraction_process.py to process the LLM queue.")


if __name__ == "__main__":
    main()
