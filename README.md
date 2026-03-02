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

- **`BRIGHTDATA_API_KEY`** (required for fetch): Your Bright Data API key. Do not commit this; use a `.env` file locally or GitHub Secrets in CI.
- **`LISTINGS_DB`** (optional): Path to the SQLite database file. Default can be `listings.db` in the current directory if unset.

**Do not commit `.env` or any file containing API keys.** The `.env` file is gitignored.

## Plan

See the [plan/](plan/) directory for phases, features, and reference (schema, config, deliverables).
