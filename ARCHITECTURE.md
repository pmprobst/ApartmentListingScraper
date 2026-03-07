# Architecture

This document describes the Utah Valley Rental Skimmer: components, data flow, and how the files work together. See [README.md](README.md) for setup and [plan/](plan/) for phases and features.

## High-level goal

Fetch rental listings for Utah Valley from Facebook Marketplace via Bright Data, store them in SQLite, enrich with Claude extraction (regex + LLM), and publish a static HTML page (e.g. GitHub Pages).

## Data flow

1. **Trigger snapshot** – `python scripts/scrape.py`  
   Uses `uvrental.brightdata.trigger_from_env()` with `BRIGHTDATA_API_KEY`. Calls Bright Data trigger API (with one retry on timeout or 5xx). On success, appends `snapshot_id` and status `"initiated"` to `snapshot_history.jsonl`. Paths come from config (e.g. `config.toml`) or env; in CI, history lives in the private DB repo.

2. **Download snapshot** – `python scripts/scrape_download.py` [optional: `<snapshot_id>`]  
   Uses `uvrental.brightdata_download.run_from_env()`. Reads **all** pending snapshots from history (oldest first), checks Bright Data progress for each; when status is `"ready"`, downloads JSON to `snapshots/marketplace_snapshot_<snapshot_id>.json` and appends status `"downloaded"`. Retries once on timeout or 5xx per request.

3. **Ingest + extraction + build** – `python main.py` (or `python scripts/run_pipeline.py`)  
   Uses `uvrental.pipeline.run_full_pipeline()`:
   - **Ingest:** reads `snapshot_history.jsonl`, ingests all snapshots with status `"downloaded"` into the DB, appends `"ingested"`, updates `run_status` (last_run_ts, success, counts).
   - **Extraction:** regex on listings with non-empty description and `llm_extraction_status IS NULL`; rows that need more get `llm_extraction_status = 'pending'`; then Claude processes the pending queue until empty. Updates `run_status.llm_processed`.
   - **Build page:** reads listings (price filter, 30-day window, exclusions), run_status, writes HTML; updates `run_status.displayed`.

   On any exception, the pipeline updates `run_status` with `success=False`, runs build_page with existing data so the site shows "last run: failed", then re-raises.

## Storage

Paths are configurable via `config.toml` (see `config_schema.toml`) or env. Locally, defaults are under the project root; in CI, the DB and snapshot data live in a **separate private repo**.

- **snapshot_history.jsonl** – append-only; statuses: initiated → running → downloaded → ingested. Location: `paths.data_dir` or repo root.
- **snapshots/** – `marketplace_snapshot_<snapshot_id>.json` (downloaded Bright Data payloads). Same parent as history.
- **Database** – `listings.db` (default), overridable via `LISTINGS_DB` or `paths.db`.
- **Output** – `docs/index.html` (default), overridable via `BUILD_PAGE_OUTPUT` or `paths.output`.

## Core modules

### uvrental.db

- **listings table:** id, source, source_listing_id, normalized_address, link, title, price, beds, baths, first_seen, last_seen, listing_date, description, in_unit_washer_dryer, has_roommates, gender_preference, utilities_included, non_included_utilities_cost, lease_length, llm_extraction_status, canonical_listing_id. `UNIQUE(source, source_listing_id)`.
- **run_status table:** Single row (id=1): last_run_ts, success, scraped, thrown, duplicate, added, total_count, new_count, updated_count, llm_processed, displayed, run_start_ts. **last_run_ts and success** are set only by the ingest step (Bright Data download → ingest); ingest also sets **run_start_ts** at run start (for new-vs-updated tagging). LLM and build_page update only llm_processed and displayed.
- **Functions:** normalize_address, get_connection, init_schema, upsert_listing, update_run_status_after_fetch, update_run_status_after_llm, update_run_status_after_build_page, update_listing_extraction, get_run_status.

### uvrental.ingest

- Reads Bright Data snapshot JSON, normalizes records, upserts into listings, updates run_status (via update_run_status_after_fetch). Manages snapshot_history (downloaded → ingested). When zero snapshots are ingested, still updates run_status so last run is recorded.

### uvrental.extraction_pipeline

- Stage 1 (regex): listings with description and llm_extraction_status IS NULL; writes extraction columns and sets llm_extraction_status to `'pending'` or `'done'`.
- Stage 2 (Claude): processes rows with llm_extraction_status = 'pending' in batches, writes results, sets 'done'. Updates run_status.llm_processed (does not change last_run_ts).

### uvrental.extraction_claude

- Calls Anthropic API for single or batch extraction; uses title, description, and regex prefill.

### uvrental.build_page

- Reads listings (price filter, 30-day window; excludes female-only, has-roommates, and summer-only leases), reads run_status, writes HTML to output dir, updates run_status.displayed (does not change last_run_ts).

### uvrental.brightdata / uvrental.brightdata_download

- Trigger and download Bright Data snapshots; read/write snapshot_history and snapshot JSON files. Trigger and download both retry once (5s delay) on timeout or 5xx. Download processes all pending snapshots oldest-first.

### uvrental.config

- Loads TOML config from `config.toml` (or `config_schema.toml` if that is missing); `CONFIG_FILE` env overrides the path. Other env vars override config (e.g. `LISTINGS_DB`, `BUILD_PAGE_OUTPUT`, `SNAPSHOT_DATA_DIR`). Provides get_db_path, get_snapshot_history_path, get_snapshots_dir, get_price_min, get_price_max, get_output_dir, get_display_days, get_claude_model, get_claude_timeout, get_dataset_id, get_location, get_category, etc.

## Scripts

- `scripts/scrape.py` – trigger snapshot only (calls uvrental.brightdata.trigger_from_env).
- `scripts/scrape_download.py` – check status and download all ready pending snapshots (calls uvrental.brightdata_download.run_from_env). Optional arg: single `snapshot_id`.
- `main.py` – full pipeline: ingest → extract → build_page (calls uvrental.pipeline.run_full_pipeline).
- `scripts/run_pipeline.py` – same as main.py (adds project root to path).
- `scripts/ingest_records.py` – ingest only (for ad-hoc use).
- `scripts/extract_new.py` – extraction only (regex + Claude).
- `scripts/build_page.py` – build HTML only.

## GitHub Actions

Two workflows run on a daily schedule (and via manual dispatch):

- **Trigger Snapshot** (`run-pipeline-trigger.yml`): 9am UTC. Checkout, clone private DB repo, run `scripts/scrape.py`, push updated snapshot_history to private repo. No download or pipeline.
- **Run Pipeline** (`run-pipeline.yml`): 10am UTC (1 hour after trigger). Clone private DB repo, wait for snapshot and download (retries), run `main.py`, push DB/snapshots to private repo and `docs/` to public repo. SQLite and snapshot data stay in the private repo only.

## Environment variables

- **BRIGHTDATA_API_KEY** – required for scrape and scrape_download.
- **ANTHROPIC_API_KEY** – required for full pipeline (Claude extraction).
- **LISTINGS_DB** – optional; overrides config `paths.db`; default `listings.db`.
- **BUILD_PAGE_OUTPUT** – optional; overrides config `paths.output`; default `docs`.
- **SNAPSHOT_DATA_DIR** – optional; overrides config `paths.data_dir`; directory for snapshot_history.jsonl and snapshots/.
- **CONFIG_FILE** – optional; path to TOML config.
- **PRICE_MIN** / **PRICE_MAX** – optional; override config search.price_min / price_max.
- **CLAUDE_MODEL** – optional; override config claude.model.

Secrets must not be committed; use `.env` locally and GitHub Secrets in CI.
