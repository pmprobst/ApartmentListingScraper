## Architecture Overview

This document describes the **current** state of the Utah Valley Rental Skimmer project: components, data flow, and how the files work together. It is a snapshot of the implementation, not the long‑term roadmap (which lives in `plan/`).

### High‑level goal

- Periodically fetch rental listings for Utah Valley from **Facebook Marketplace via Bright Data**, store them in **SQLite**, and eventually:
  - Enrich new in‑range listings with a Claude API extraction step.
  - Render a static HTML page (served via GitHub Pages) with a run‑status indicator.

Right now the implementation is focused on **Phase 0** (Bright Data → SQLite) plus some **experimental Bright Data scraper utilities**.

---

## Components and responsibilities

### `db.py` – SQLite schema and upsert logic

- Defines the **`listings`** table and enforces deduplication within each source.
- Key pieces:
  - `init_schema(conn)`: creates the `listings` table if it does not exist, with:
    - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
    - `source`, `source_listing_id`
    - `normalized_address`, `address_raw`
    - `link`, `title`, `price`, `beds`, `baths`
    - `first_seen`, `last_seen`
    - `extracted` (JSON/text from LLM extraction, nullable)
    - `canonical_listing_id` (for future cross‑source merge)
    - `UNIQUE(source, source_listing_id)` – one row per listing per source.
  - `normalize_address(raw)`: normalizes addresses (lowercase, strip punctuation, collapse whitespace, standardize street suffixes such as `st → street`, `ave → avenue`, etc.). Used for deduplication.
  - `upsert_listing(conn, ...)`:
    - Computes `normalized_address` (unless explicitly provided).
    - Inserts a new row or updates the existing row matching `(source, source_listing_id)`.
    - Sets `first_seen` on insert; updates `last_seen` on every upsert.
    - Uses `COALESCE(excluded.extracted, listings.extracted)` so a `None` `extracted` value does **not** overwrite existing extracted data.
  - `get_connection(db_path)`: opens/creates the SQLite database at `db_path`, sets `row_factory` to `sqlite3.Row`, and ensures the schema exists via `init_schema`.

**Data contract:** All fetchers for any source must eventually call `upsert_listing` with a normalized listing record; higher‑level code should not manually manipulate the schema.

---

### `fetch.py` – Bright Data → SQLite (Phase 0 pipeline)

`fetch.py` implements the main data pipeline for **Facebook Marketplace via Bright Data’s Dataset / Web Scraper API**.

- **Environment and defaults**
  - Uses `python-dotenv` to load `.env`.
  - Reads env keys (constants exported for reuse by `main.py`):
    - `BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY` (preferred) or `BRIGHTDATA_API_KEY` – Bright Data API key.
    - `LISTINGS_DB` – path to SQLite DB (default: `listings.db`).
    - Optional Bright Data parameters:
      - `BRIGHTDATA_DATASET_ID` (default: `gd_lvt9iwuh6fbcwmx1a`)
      - `BRIGHTDATA_KEYWORD` (default: `"Apartment"`)
      - `BRIGHTDATA_CITY` (default: `"Provo, UT"`)
      - `BRIGHTDATA_RADIUS_MILES` (default: `20`) – restricts listings to ~20 miles around the city to save tokens.
  - Helper `_env(key, default)` ensures env values are stripped and fall back to provided defaults.

- **Bright Data API interaction**
  - `TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"`
  - `PROGRESS_URL = "https://api.brightdata.com/datasets/v3/progress"`
  - `SNAPSHOT_DOWNLOAD_URL = "https://api.brightdata.com/datasets/snapshots"`
  - `trigger_collection(api_key, dataset_id, keyword, city, radius_miles=20)`:
    - Calls `POST /datasets/v3/trigger?dataset_id=...&type=discover_new&discover_by=keyword` with JSON:
      - `{"input": [{"keyword": <keyword>, "city": <city>, "radius": <radius_miles>, "date_listed": "", "state": "UT", "country": "US"}]}`.
    - Use `city` like `"Provo, UT"` and `radius_miles` so results are restricted to ~20 miles around Provo, UT (and US-only).
    - On success, returns `snapshot_id` (string) or `None` on errors (with logging).
  - `wait_for_ready(api_key, snapshot_id)`:
    - Polls `GET /datasets/v3/progress/{snapshot_id}` every `POLL_INTERVAL_SEC` until:
      - `status == "ready"` → returns `True`.
      - `status == "failed"` → logs error and returns `False`.
      - 404 → logs a warning and returns `True` (allowing download attempt).
      - Timeout after `POLL_TIMEOUT_SEC` → returns `False`.
  - `download_snapshot(api_key, snapshot_id)`:
    - Calls `GET /datasets/snapshots/{snapshot_id}/download?format=json`.
    - Handles response shapes:
      - Top‑level list → returned as‑is.
      - Object with array fields like `data`, `results`, `listings`, `items`, `records` → returns that array.
      - Single object → wrapped as a one‑element list.

- **Record normalization**
  - `_source_listing_id(record)`:
    - Tries `product_id`, `listing_id`, `id`, `listingID` in that order.
    - Falls back to a **stable SHA‑256 hash** of `link`/`url`/`listing_url` (or of `title` as worst case).
  - `_numeric_listing_id(record)`:
    - Extracts a numeric Marketplace item id from known fields or from URLs like `/marketplace/item/{id}`.
  - `normalize_record(record)`:
    - Constructs a **canonical Facebook Marketplace URL**:
      - If a numeric id is available: `https://www.facebook.com/marketplace/item/{id}/`.
      - Else: chooses from `link` / `url` / `listing_url` / `listing_link`, prefixing the Marketplace base if needed.
    - Maps:
      - `title` / `name` → listing title.
      - `price` / `final_price` / `initial_price` / `listing_price` → `price` (float or `None`).
      - `beds` / `bedrooms` / `bed` → `beds` (float or `None`).
      - `baths` / `bathrooms` / `bath` → `baths` (float or `None`).
      - `location` (string or dict) / `address` / `address_raw` / `city` / `location_name` → single `address_raw` string.

- **Pipeline orchestration**
  - `run_fetch(db_path, api_key, dataset_id, keyword, city, radius_miles=20) -> int`:
    - Triggers a collection (with radius and state/country for Provo, UT), waits for the snapshot to be ready, downloads it, normalizes each record, and upserts via `upsert_listing` into the SQLite DB at `db_path`.
    - Returns the count of successfully upserted listings.
  - `run_fetch_dry_run(db_path) -> int`:
    - Uses static `MOCK_RECORDS` (with realistic long Marketplace item ids) and runs only the normalize+upsert steps (no API calls).
    - Used by tests and “Phase 0 Step 4” verification.
  - `main()`:
    - If `--dry-run` is passed, runs `run_fetch_dry_run` with DB path from env/defaults.
    - Otherwise, resolves `api_key`, dataset id, keyword, city, radius_miles from env and calls `run_fetch`.

**Role:** `fetch.py` is the canonical Bright Data → SQLite pipeline. Other scripts (e.g. `main.py`, future schedulers, GitHub Actions workflows) should call its `run_fetch` / `run_fetch_dry_run` functions rather than re‑implementing the logic.

---

### `main.py` – Test harness and DB inspector

`main.py` is the **human‑friendly entrypoint** used during development to run fetches and inspect what’s in the DB.

- Loads `.env` and ensures the project root is on `sys.path` so `db` and `fetch` are importable.
- Key functions:
  - `run_fetch_step(dry_run: bool) -> str`:
    - Resolves `db_path` from `LISTINGS_DB` or default.
    - For `dry_run=True`: calls `run_fetch_dry_run(db_path)`.
    - For `dry_run=False`: validates that an API key exists, reads Bright Data params (including `BRIGHTDATA_RADIUS_MILES`), and calls `run_fetch(db_path, api_key, dataset_id, keyword, city, radius_miles)`.
    - Returns the DB path used.
  - `print_listings(db_path: str, dry_run: bool)`:
    - Opens the DB via `get_connection`.
    - SELECTs all rows from `listings` ordered by `id`.
    - Prints a human‑readable summary for each listing (`id`, `source`, `source_listing_id`, `title`, `link`, `price`, `beds`, `baths`, `address_raw`, `first_seen`, `last_seen`).
    - Annotates whether the data came from a dry run (mock listings/fake IDs) or from a real Bright Data run.
  - `main()`:
    - Determines `dry_run` from `--dry-run` in `sys.argv`.
    - Prints what it’s about to do (“Running fetch (dry‑run)…” vs “Running fetch (Bright Data API)…”).
    - Calls `run_fetch_step`, then `print_listings`.

**Usage:** During Phase 0, developers typically run:

```bash
python main.py --dry-run   # quick DB + printing with mock data
python main.py             # real Bright Data fetch, then print listings
```

---

### `scrape.py` and `scrape_download.py` – Experimental Scraper API helpers

These two scripts are **standalone helpers** for working directly with Bright Data’s **Scraper API / Crawl API** separate from the main `fetch.py` Dataset pipeline. They are useful for ad‑hoc experiments and for debugging Bright Data behavior.

#### `scrape.py` – trigger + history log

- Uses `BRIGHT_DATA_API_KEY` from `.env` and posts to:

  ```text
  POST https://api.brightdata.com/datasets/v3/trigger
      ?dataset_id=gd_lvt9iwuh6fbcwmx1a
      &notify=false
      &include_errors=true
      &type=discover_new
      &discover_by=keyword
      &limit_per_input=1000
  ```

  with JSON body:

  ```json
  {
    "input": [
      {"keyword": "Apartment", "city": "Provo", "radius": 20, "date_listed": ""}
    ]
  }
  ```

- On success:
  - Prints the full JSON response.
  - Extracts `snapshot_id` (or `snapshot_ID`) and appends a line to `snapshot_history.jsonl` in the project root:

    ```json
    {"timestamp": "2026-02-24T12:34:56Z", "snapshot_id": "sd_..."}
    ```

  - Prints a confirmation like: `Recorded snapshot_id=sd_... in snapshot_history.jsonl`.

#### `scrape_download.py` – status check + conditional download

- Also uses `BRIGHT_DATA_API_KEY` from `.env`.
- Supports two modes:
  - **Explicit id:** `python scrape_download.py <snapshot_id>`
  - **Latest from history:** `python scrape_download.py`
    - Reads `snapshot_history.jsonl`, scans from the end for the most recent valid JSON record with a `snapshot_id`, and uses that id.

- Workflow:
  1. Calls `GET https://api.brightdata.com/datasets/v3/progress/{snapshot_id}`.
     - If 404 → prints a message and exits with error.
     - Otherwise parses JSON and prints `Status for {snapshot_id}: <status>`.
  2. If `status != "ready"` → exits **without** requesting the snapshot content.
  3. If `status == "ready"`:
     - Calls `GET https://api.brightdata.com/datasets/snapshots/{snapshot_id}/download?format=json`.
     - If status 202 → prints a “not ready” message and exits.
     - On success, saves the payload to `marketplace_snapshot_{snapshot_id}.json` and prints the approximate record count (handles both list and common object‑with‑array shapes).

**Separation of concerns:**

- `scrape.py` is **fire‑and‑forget**: trigger a job and log the `snapshot_id` for later.
- `scrape_download.py` is **idempotent** and cheap: check a specific or latest `snapshot_id` once and only download when the job is ready, so you don’t need a long‑running process waiting.

---

### Test suite (`tests/`)

The project uses **pytest** with a modest but focused test suite aligned with the Phase 0 plan.

- `tests/conftest.py`
  - Ensures the project root is on `sys.path` so imports like `db`, `fetch` work.
  - Fixtures:
    - `tmp_db_path`: returns a unique temporary DB path per test.
    - `tmp_db_conn`: opens a connection with schema initialized, yielding it to the test.
    - `env_vars`: sets safe test env vars (`LISTINGS_DB`, Bright Data API keys) via `monkeypatch` so tests don’t touch the real DB or credentials.

- `tests/unit/test_db.py`
  - Validates `init_schema` creates the correct columns and uniqueness constraint.
  - Exercises `normalize_address` for common patterns and edge cases.
  - Verifies `upsert_listing` behavior for:
    - insert vs update (`first_seen` preservation, `last_seen` update),
    - `normalized_address` derivation,
    - `extracted` COALESCE logic.

- `tests/unit/test_fetch_utils.py`
  - Covers `_source_listing_id`, `_numeric_listing_id`, `_norm_price`, `_norm_num`, `_address_raw`, and `normalize_record`, ensuring stable ids and canonical Marketplace URLs.

- `tests/integration/test_phase0_fetch_dry_run.py`
  - Runs `run_fetch_dry_run` against a temp DB.
  - Confirms:
    - correct number of rows,
    - no duplicate `(source, source_listing_id)` pairs,
    - timestamps populated,
    - canonical Marketplace URLs.

- `tests/integration/test_phase0_main_dry_run.py`
  - Invokes `python main.py --dry-run` via `subprocess` with a temp `LISTINGS_DB`.
  - Verifies:
    - exit code 0,
    - DB has rows,
    - output contains the listing summary header.

- Placeholder tests:
  - `tests/integration/test_phase1_build_page_placeholder.py` – module‑level skipped until `build_page.py` and run‑status storage exist.
  - `tests/acceptance/test_pipeline_future_placeholder.py` – module‑level skipped; reserved for future full‑pipeline/multi‑site/robustness tests.

---

## Configuration and environment

- **Configuration style (current):**
  - All runtime configuration is via **environment variables** (often loaded from `.env` in local development).
  - The planned TOML config schema is defined in `plan/` but not yet wired into code.

- **Key env vars in use now:**
  - `BRIGHT_DATA_API_KEY` – required by `scrape.py` / `scrape_download.py`.
  - `BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY` and/or `BRIGHTDATA_API_KEY` – required by `fetch.py` / `main.py` for the Dataset pipeline.
  - `LISTINGS_DB` – optional DB path override; defaults to `listings.db`.
  - `BRIGHTDATA_DATASET_ID`, `BRIGHTDATA_KEYWORD`, `BRIGHTDATA_CITY` – optional Bright Data parameters for Phase 0.

**Security note:** `.env` is gitignored; API keys and secrets should never be committed. In CI (e.g. GitHub Actions), these values will be provided via **GitHub Secrets**.

---

## Current status and intended evolution

- **Implemented:**
  - Phase 0 core:
    - SQLite schema and dedup (`db.py`).
    - Bright Data Dataset integration and normalization (`fetch.py`).
    - Developer entrypoint for running fetches and inspecting DB (`main.py`).
    - Basic pytest suite (unit + integration) aligned with Phase 0.
  - Experimental:
    - Scraper API helpers (`scrape.py`, `scrape_download.py`) plus `snapshot_history.jsonl`.

- **Planned next steps (per `plan/` docs, not yet in code):**
  - Phase 1: run‑status persistence and static webpage generator (`build_page.py`), including a run‑status banner on the page.
  - Phase 2+: TOML config loader, Claude API extraction for new in‑range listings only, GitHub Actions workflows, multi‑site support, and robustness improvements.

This document should be updated whenever major architectural changes are made (new phases implemented, new components added, or responsibilities of existing modules change).

