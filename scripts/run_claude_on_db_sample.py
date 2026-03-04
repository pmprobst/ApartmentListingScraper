"""
CLI: Run Claude extraction on up to N listings from the SQLite DB.

Usage:
    python scripts/run_claude_on_db_sample.py [limit]

- Reads DB path from LISTINGS_DB (default: listings.db).
- Selects the most recent listings by last_seen (default limit: 3).
- Calls the Claude API for each listing using `uvrental.claude_client`.
- Prints extracted fields and latency for manual inspection.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from uvrental.db import get_connection  # noqa: E402
from uvrental.claude_client import extract_from_text  # noqa: E402


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
            SELECT id, title, price, beds, baths, address_raw
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
        print(f"  price: {r['price']!r}")
        print(f"  beds:  {r['beds']!r}")
        print(f"  baths: {r['baths']!r}")
        print(f"  addr:  {r['address_raw']!r}")

        extracted, latency = extract_from_text(
            title=r["title"] or "",
            # NOTE: description is not stored in the DB today, so we pass an
            # empty string here. For best-quality extraction in the future,
            # we will call Claude during snapshot ingestion when full text is available.
            description="",
            price=r["price"],
            beds=r["beds"],
            baths=r["baths"],
            address_raw=r["address_raw"],
        )

        print(f"Claude latency: {latency:.2f}s")
        if extracted is None:
            print("Extraction failed (no JSON parsed).")
        else:
            import json as _json

            print("Extracted fields:")
            print(_json.dumps(extracted, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])

