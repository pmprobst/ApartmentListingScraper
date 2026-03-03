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

- **`BRIGHTDATA_API_KEY`** – required by `scripts/scrape.py` / `scripts/scrape_download.py` to trigger and download Bright Data snapshots. Do not commit; use `.env` locally or GitHub Secrets in CI.
- **`LISTINGS_DB`** (optional) – path to the SQLite database file. Default: `listings.db`.

**Do not commit `.env` or any file containing API keys.** The `.env` file is gitignored.

## Phase 0 (Bright Data → SQLite)

End-to-end flow for Phase 0 is:

1. **Trigger snapshot:** `python scripts/scrape.py`  
   - Uses `uvrental.brightdata` to call Bright Data’s Dataset API and records a `snapshot_id` with status `"initiated"` in `snapshot_history.jsonl` at the repo root.
2. **Download snapshot JSON:** `python scripts/scrape_download.py`  
   - Uses `uvrental.brightdata_download` to check snapshot status; when `ready`, saves `marketplace_snapshot_<snapshot_id>.json` (currently at the repo root) and records status `"downloaded"` in `snapshot_history.jsonl`.
3. **Ingest into SQLite and build page:** `python scripts/run_pipeline.py`  
   - Uses `uvrental.ingest` to ingest all snapshots whose latest status is `"downloaded"` into `LISTINGS_DB`, marking them `"ingested"` in `snapshot_history.jsonl`.
   - Prints a summary of listings from the DB and regenerates `docs/index.html` via `uvrental.build_page`.

At the end of Phase 0, `listings.db` contains normalized, deduplicated listings from Facebook Marketplace.

## Plan

See the [plan/](plan/) directory for phases, features, and reference (schema, config, deliverables).
