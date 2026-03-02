# Utah Valley Rental Skimmer

Skims online rental markets in Utah Valley (Bright Data → SQLite → webpage). Listings are stored in SQLite, enriched by Claude API for new listings, and published as a static page on GitHub Pages.

## Setup

- **Python**: 3.x
- Create a virtual environment (recommended):
  ```bash
  python -m venv .venv
  source .venv/bin/activate   # Windows: .venv\Scripts\activate
  ```
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

## Environment variables

- **`BRIGHT_DATA_API_KEY`** (required for fetch): Your Bright Data API key for Facebook Marketplace. Do not commit this; use a `.env` file locally or GitHub Secrets in CI. The script also accepts 
- **`LISTINGS_DB`** (optional): Path to the SQLite database file. Default: `listings.db`.
- **`BRIGHTDATA_DATASET_ID`**, **`BRIGHTDATA_KEYWORD`**, **`BRIGHTDATA_CITY`**, **`BRIGHTDATA_RADIUS_MILES`** (optional): Bright Data Facebook Marketplace params. Defaults: dataset `gd_lvt9iwuh6fbcwmx1a`, keyword `Apartment`, city `Provo, UT`, radius `20` miles. Used by `fetch.py` to restrict listings to ~20 miles around Provo, UT (and US-only).

**Do not commit `.env` or any file containing API keys.** The `.env` file is gitignored.

## Phase 0 (Bright Data → SQLite)

- **Fetch:** `python fetch.py` (requires `BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY` or `BRIGHTDATA_API_KEY` in `.env`). Optional: `python fetch.py --dry-run` to insert mock listings without calling the API.
- **Run tests / see listing data:** `python main.py` runs fetch then prints all listings from the DB. Use `python main.py --dry-run` to skip the API and print mock data.
- **Verify:** After a fetch, run `python scripts/verify_phase0_step4.py [path_to_listings.db]` to confirm the DB has listings with no duplicates and `first_seen`/`last_seen` set. Default DB path: `listings.db` or `LISTINGS_DB` env.

## Plan

See the [plan/](plan/) directory for phases, features, and reference (schema, config, deliverables).
