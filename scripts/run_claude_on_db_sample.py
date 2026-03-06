"""
CLI: Run Claude extraction on up to N listings from the SQLite DB.

Usage:
    python scripts/run_claude_on_db_sample.py [limit]

- Reads DB path from LISTINGS_DB (default: listings.db).
- Selects the most recent listings by last_seen (default limit: 3).
- Uses the extraction pipeline's Claude API (extraction_claude) with
  title, description, and optional pre-fill from existing DB columns.
- Prints extracted fields and latency for manual inspection.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from uvrental.db import get_connection  # noqa: E402
from uvrental.extraction_claude import call_claude  # noqa: E402
from uvrental.extraction_pipeline import row_to_stage1_prefill  # noqa: E402


def main(argv: list[str]) -> None:
    try:
        limit = int(argv[0]) if argv else 3
    except ValueError:
        print("Invalid limit; must be an integer.", file=sys.stderr)
        raise SystemExit(1)

    db_path = os.environ.get("LISTINGS_DB", "listings.db").strip() or "listings.db"
    print(f"Using DB: {db_path}")
    print(f"Max listings to process: {limit}")

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, title, description, beds, baths, in_unit_washer_dryer,
                   has_roommates, gender_preference, utilities_included,
                   non_included_utilities_cost, lease_length
            FROM listings
            ORDER BY last_seen DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("No listings found in DB.")
        return

    for idx, r in enumerate(rows, start=1):
        print("\n" + "=" * 60)
        print(f"Listing {idx}/{len(rows)} (id={r['id']}):")
        print(f"  title: {r['title']!r}")
        raw_desc = r["description"] or ""
        desc = raw_desc[:80] + ("..." if len(raw_desc) > 80 else "")
        print(f"  description: {desc!r}")
        stage1 = row_to_stage1_prefill(r)
        t0 = time.perf_counter()
        try:
            extracted = call_claude(
                r["title"] or "",
                r["description"] or "",
                stage1,
            )
            latency = time.perf_counter() - t0
        except Exception as e:
            print(f"Claude error: {e}")
            continue
        print(f"Claude latency: {latency:.2f}s")
        print("Extracted fields:")
        print(json.dumps(extracted, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
