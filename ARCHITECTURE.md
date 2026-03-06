# Architecture

This document describes the current Utah Valley Rental Skimmer: components, data flow, and how the files work together.

## High-level goal

Fetch rental listings for Utah Valley from Facebook Marketplace via Bright Data, store them in SQLite, enrich with Claude extraction (regex + LLM), and publish a static HTML page (e.g. GitHub Pages).

## Data flow

1. **Trigger snapshot** – `python scripts/scrape.py`  
   Uses `uvrental.brightdata.trigger_from_env()` with `BRIGHTDATA_API_KEY`. On success, appends `snapshot_id` and status `"initiated"` to `snapshot_history.jsonl` at the repo root.

2. **Download snapshot** – `python scripts/scrape_download.py` [optional: `<snapshot_id>`]  
   Uses `uvrental.brightdata_download.run_from_env()`. Reads latest pending snapshot from history, checks Bright Data progress; when status is `"ready"`, downloads JSON to `marketplace_snapshot_<snapshot_id>.json` and appends status `"downloaded"` to history.

3. **Ingest + extraction + build** – `python main.py` (or `python scripts/run_pipeline.py`)  
   Uses `uvrental.pipeline.run_full_pipeline()`:
   - Ingest: reads `snapshot_history.jsonl`, ingests all snapshots with status `"downloaded"` into the DB, appends `"ingested"`.
   - Build page (first pass).
   - Extraction: regex on listings with non-empty description and `llm_extraction_status IS NULL`; rows that need more get `llm_extraction_status = 'pending'`; then Claude processes the pending queue until empty.
   - Build page (final).

## Storage

- **Repo root (runtime):** `snapshot_history.jsonl` (append-only; statuses: initiated → running → downloaded → ingested), `marketplace_snapshot_<snapshot_id>.json`.
- **Database:** `listings.db` (default), overridable via `LISTINGS_DB`.
- **Output:** `docs/index.html` (default), overridable via `BUILD_PAGE_OUTPUT`.

## Core modules

### uvrental.db

- **listings table:** id, source, source_listing_id, normalized_address, link, title, price, beds, baths, first_seen, last_seen, listing_date, description, in_unit_washer_dryer, has_roommates, gender_preference, utilities_included, non_included_utilities_cost, lease_length, llm_extraction_status, canonical_listing_id. `UNIQUE(source, source_listing_id)`.
- **run_status table:** Single row (id=1): last_run_ts, success, scraped, thrown, duplicate, added, total_count, new_count, updated_count, llm_processed, displayed. **last_run_ts and success** are set only by the ingest step (Bright Data download → ingest); LLM and build_page update only llm_processed and displayed.
- **Functions:** normalize_address, get_connection, init_schema, upsert_listing, update_run_status_after_fetch, update_run_status_after_llm, update_run_status_after_build_page, update_listing_extraction, get_run_status.

### uvrental.ingest

- Reads Bright Data snapshot JSON, normalizes records, upserts into listings, updates run_status (via update_run_status_after_fetch). Manages snapshot_history (downloaded → ingested). When zero snapshots are ingested, still updates run_status so last run is recorded.

### uvrental.extraction_pipeline

- Stage 1 (regex): listings with description and llm_extraction_status IS NULL; writes extraction columns and sets llm_extraction_status to `'pending'` or `'done'`.
- Stage 2 (Claude): processes rows with llm_extraction_status = 'pending' in batches, writes results, sets 'done'. Updates run_status.llm_processed (does not change last_run_ts).

### uvrental.extraction_claude

- Calls Anthropic API for single or batch extraction; uses title, description, and regex prefill.

### uvrental.build_page

- Reads listings (price filter, 30-day window, excludes female-only and has-roommates), reads run_status, writes HTML to output dir, updates run_status.displayed (does not change last_run_ts).

### uvrental.brightdata / uvrental.brightdata_download

- Trigger and download Bright Data snapshots; read/write snapshot_history and snapshot JSON files.

## Scripts

- `scripts/scrape.py` – trigger snapshot (calls uvrental.brightdata.trigger_from_env).
- `scripts/scrape_download.py` – check status and download when ready (calls uvrental.brightdata_download.run_from_env).
- `main.py` – full pipeline (calls uvrental.pipeline.run_full_pipeline).
- `scripts/run_pipeline.py` – same as main.py (adds project root to path, then run_full_pipeline).

## Environment variables

- **BRIGHTDATA_API_KEY** – required for scrape and scrape_download.
- **ANTHROPIC_API_KEY** – required for full pipeline (Claude extraction).
- **LISTINGS_DB** – optional; default `listings.db`.
- **BUILD_PAGE_OUTPUT** – optional; default `docs`.
- **PRICE_MIN** / **PRICE_MAX** – optional; default 0 / 2000 (filter for HTML).
- **CLAUDE_MODEL** – optional; default `claude-sonnet-4-20250514`.

Secrets must not be committed; use `.env` locally and GitHub Secrets (or equivalent) in CI.
