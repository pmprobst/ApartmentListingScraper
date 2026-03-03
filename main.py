"""
Main entry point for ingesting the latest snapshot into the DB and building HTML.
Usage: python main.py
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_connection
from build_page import build_page as build_static_page
from ingest_records import LISTINGS_DB, DEFAULT_DB, _env, ingest_all_downloaded_from_history


def print_listings(db_path: str) -> None:
    """Print all listings from the DB in a readable format."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, source, source_listing_id, title, link, price, beds, baths, address_raw, first_seen, last_seen FROM listings ORDER BY id"
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
            print(f"  address_raw:         {r['address_raw']}")
            print(f"  first_seen:          {r['first_seen']}")
            print(f"  last_seen:           {r['last_seen']}")
            print()
    finally:
        conn.close()


def main() -> None:
    print("Ingesting all downloaded snapshots into DB...\n")
    db_path = _env(LISTINGS_DB, DEFAULT_DB)
    n = ingest_all_downloaded_from_history(db_path)
    print(f"\nIngested {n} records into {db_path}.\n")
    print("\nListing data from DB:\n")
    print_listings(db_path)

    print("\nBuilding static HTML page...\n")
    build_static_page()
    print("Static page build complete (see docs/index.html by default).")


if __name__ == "__main__":
    main()
