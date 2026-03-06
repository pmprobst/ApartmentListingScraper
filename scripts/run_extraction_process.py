#!/usr/bin/env python3
"""
Option B process: take next batch of listings from LLM queue, call Claude,
write results to DB, build HTML #3.

Run repeatedly after run_extraction_initiate.py until no more pending listings.
Exit code 0 and "Queue empty" when nothing left to process.

Usage:
    python scripts/run_extraction_process.py [batch_size]

Default batch_size: 5
"""

import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uvrental.db import get_connection
from uvrental.build_page import build_page
from uvrental.ingest import _env, LISTINGS_DB, DEFAULT_DB
from uvrental.extraction_pipeline import (
    get_listings_pending_llm,
    row_to_stage1_prefill,
    llm_result_to_db_values,
)
from uvrental.extraction_claude import call_claude_batch, call_claude
from uvrental.db import update_listing_extraction


def main() -> None:
    batch_size = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    db_path = _env(LISTINGS_DB, DEFAULT_DB)

    conn = get_connection(db_path)
    try:
        rows = get_listings_pending_llm(conn, limit=batch_size)
        if not rows:
            print("Queue empty. Nothing to process.")
            return
    finally:
        conn.close()

    # Build batch for Claude: list of {"title", "description", "stage1"}
    batch = []
    for r in rows:
        batch.append({
            "title": r["title"] or "",
            "description": r["description"] or "",
            "stage1": row_to_stage1_prefill(r),
        })

    print(f"Processing {len(batch)} listings with Claude...")
    try:
        llm_results = call_claude_batch(batch)
    except Exception as e:
        print(f"Batch failed: {e}. Falling back to single calls.")
        llm_results = []
        for item in batch:
            try:
                out = call_claude(
                    item["title"], item["description"], item["stage1"]
                )
                llm_results.append(out)
            except Exception as e2:
                print(f"  Single call failed: {e2}")
                llm_results.append({})  # placeholder so indices match

    conn = get_connection(db_path)
    try:
        for i, (row, llm_out) in enumerate(zip(rows, llm_results)):
            if not llm_out:
                continue
            values = llm_result_to_db_values(llm_out)
            update_listing_extraction(conn, row["id"], **values)
        print(f"Updated {len(llm_results)} listings in DB.")
    finally:
        conn.close()

    print("Building HTML (after LLM batch)...")
    build_page()
    print("Done. Run again to process more, or stop when queue is empty.")
    time.sleep(0.5)


if __name__ == "__main__":
    main()
