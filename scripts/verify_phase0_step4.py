"""
Phase 0 Step 4 verification: after running fetch.py, checks that the DB has
listings with no duplicate (source, source_listing_id) and first_seen/last_seen set.
Run: python scripts/verify_phase0_step4.py [path_to_listings.db]
"""
import os
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from db import get_connection

load_dotenv()

DEFAULT_DB = os.environ.get("LISTINGS_DB", "listings.db").strip() or "listings.db"


def verify(db_path: str) -> bool:
    if not os.path.exists(db_path):
        print(f"FAIL: DB not found: {db_path}")
        return False
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "SELECT source, source_listing_id, first_seen, last_seen FROM listings"
        )
        rows = cur.fetchall()
        if not rows:
            print("FAIL: No listings in DB")
            return False
        # Check duplicates
        keys = [(r["source"], r["source_listing_id"]) for r in rows]
        if len(keys) != len(set(keys)):
            print("FAIL: Duplicate (source, source_listing_id) found")
            return False
        # Check timestamps
        for r in rows:
            if not r["first_seen"] or not r["last_seen"]:
                print("FAIL: Row missing first_seen or last_seen:", dict(r))
                return False
        print(f"OK: {len(rows)} listing(s), no duplicates, first_seen/last_seen set")
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    ok = verify(path)
    sys.exit(0 if ok else 1)
