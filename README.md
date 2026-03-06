# Utah Valley Rental Skimmer

Fetches rental listings for Utah Valley from Facebook Marketplace (via Bright Data), stores them in SQLite, enriches them with Claude extraction, and publishes a static HTML page (e.g. GitHub Pages).

## Setup

- **Python:** 3.x
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

- **BRIGHTDATA_API_KEY** – required for `scripts/scrape.py` and `scripts/scrape_download.py`. Do not commit; use `.env` locally or GitHub Secrets in CI.
- **ANTHROPIC_API_KEY** – required for the full pipeline (ingest + extraction + build). Used when running `main.py` or `scripts/run_pipeline.py`.
- **LISTINGS_DB** (optional) – path to the SQLite database. Default: `listings.db`.

Do not commit `.env` or any file containing API keys. The `.env` file is gitignored.

## End-to-end flow

1. **Trigger a snapshot:** `python scripts/scrape.py`  
   Calls Bright Data and records a `snapshot_id` with status `"initiated"` in `snapshot_history.jsonl`.

2. **Download snapshot JSON:** `python scripts/scrape_download.py`  
   Polls Bright Data; when the snapshot is ready, saves `snapshots/marketplace_snapshot_<snapshot_id>.json` and updates history to `"downloaded"`.

3. **Ingest, extract, and build page:** `python main.py`  
   Ingests all downloaded snapshots into the DB, runs regex + Claude extraction on listings with descriptions, and builds `docs/index.html`. You can also run `python scripts/run_pipeline.py` for the same pipeline (with project root on path).

Output: `listings.db` and `docs/index.html` (by default). The HTML shows listings within the configured price range and 30-day window; female-only, has-roommates, and summer-only (no renewal option) listings are excluded from the page.

## Plan

See the [plan/](plan/) directory for phases, features, and reference.
