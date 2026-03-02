"""
Main entry point for running tests during the build.
Runs fetch (optionally --dry-run), then prints listing data from the DB.
Usage: python main.py [--dry-run]
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_connection
from fetch import (
    BRIGHTDATA_API_KEY,
    BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY,
    DEFAULT_CITY,
    DEFAULT_DATASET_ID,
    DEFAULT_DB,
    DEFAULT_KEYWORD,
    DEFAULT_RADIUS_MILES,
    LISTINGS_DB,
    run_fetch,
    run_fetch_dry_run,
)


def _env(key: str, default: str | None = None) -> str:
    v = os.environ.get(key, default or "")
    return v.strip() if isinstance(v, str) else ""


def run_fetch_step(dry_run: bool) -> str:
    """Run fetch (real or dry-run). Returns DB path used."""
    db_path = _env(LISTINGS_DB, DEFAULT_DB)
    if dry_run:
        run_fetch_dry_run(db_path)
    else:
        api_key = _env(BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY) or _env(BRIGHTDATA_API_KEY)
        if not api_key:
            print("ERROR: Missing BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY (or BRIGHTDATA_API_KEY)", file=sys.stderr)
            sys.exit(1)
        dataset_id = _env("BRIGHTDATA_DATASET_ID", DEFAULT_DATASET_ID)
        keyword = _env("BRIGHTDATA_KEYWORD", DEFAULT_KEYWORD)
        city = _env("BRIGHTDATA_CITY", DEFAULT_CITY)
        radius_str = _env("BRIGHTDATA_RADIUS_MILES", str(DEFAULT_RADIUS_MILES))
        try:
            radius_miles = int(radius_str)
        except ValueError:
            radius_miles = DEFAULT_RADIUS_MILES
        run_fetch(db_path, api_key, dataset_id, keyword, city, radius_miles)
    return db_path


def print_listings(db_path: str, dry_run: bool = False) -> None:
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
        if dry_run:
            print("(Dry-run: these are mock listings with fake IDs; links will not open real Marketplace pages.)")
        else:
            print("(Note: Marketplace links may show \"Not available\" if the listing was removed or sold since fetch.)")
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
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("Running fetch (dry-run)...\n")
    else:
        print("Running fetch (Bright Data API)...\n")
    db_path = run_fetch_step(dry_run)
    print("\nFetched listing data from DB:\n")
    print_listings(db_path, dry_run=dry_run)


if __name__ == "__main__":
    main()
