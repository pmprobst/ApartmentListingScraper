## Architecture Overview

This document describes the **current** state of the Utah Valley Rental Skimmer project: components, data flow, and how the files work together. It is a snapshot of the implementation, not the long‑term roadmap (which lives in `plan/`).

### High‑level goal

- Periodically fetch rental listings for Utah Valley from **Facebook Marketplace via Bright Data**, store them in **SQLite**, and eventually:
  - Enrich new in‑range listings with a Claude API extraction step.
  - Render a static HTML page (served via GitHub Pages) with a run‑status indicator.

Right now the implementation is focused on **Phase 0** (Bright Data → SQLite) plus some **experimental Bright Data scraper utilities**.

**Doc map:** Roadmap, feature list, and phase steps live in **plan/**: [plan/plan.md](plan/plan.md) (overview), [plan/features.md](plan/features.md) (requirements), [plan/reference.md](plan/reference.md) (schema, config, sources), and [plan/phase-*.md](plan/phase-0.md) (steps and checklists).

---

## Components and responsibilities

### `uvrental.db` – SQLite schema and upsert logic

- Defines the **`listings`** table and enforces deduplication within each source.
- Key pieces:
  - `init_schema(conn)`: creates the `listings` table if it does not exist, with:
    - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
    - `source`, `source_listing_id`
    - `normalized_address`, `address_raw`
    - `link`, `title`, `price`, `beds`, `baths`
    - `first_seen`, `last_seen`
    - `extracted` (JSON/text from LLM extraction, nullable)
    - `canonical_listing_id` – set automatically when another row with the same normalized_address and a different source exists (cross‑source dedup).
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

### `uvrental.ingest` – Bright Data snapshots → SQLite (Phase 0 pipeline)

`uvrental.ingest` implements the main data pipeline for **Facebook Marketplace snapshots downloaded from Bright Data**.

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
      - `BRIGHTDATA_LIMIT_PER_INPUT` (default: `100`) – caps how many records are collected per input (e.g. 100 for testing, 1000 for production).
  - Helper `_env(key, default)` ensures env values are stripped and fall back to provided defaults.

- **Bright Data API interaction**
  - `TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"`
  - `PROGRESS_URL = "https://api.brightdata.com/datasets/v3/progress"`
  - `SNAPSHOT_DOWNLOAD_URL = "https://api.brightdata.com/datasets/v3/snapshot"` (same as scrape_download.py)
  - `trigger_collection(api_key, dataset_id, keyword, city, radius_miles=20)`:
    - Calls `POST /datasets/v3/trigger?dataset_id=...&type=discover_new&discover_by=keyword` with JSON:
      - `{"input": [{"keyword": <keyword>, "city": <city>, "radius": <radius_miles>, "date_listed": ""}]}`.
    - Use `city` like `"Provo, UT"` and `radius_miles` so results are restricted to ~20 miles around the city. (API does not accept separate state/country fields.)
    - On success, returns `snapshot_id` (string) or `None` on errors (with logging).
  - `wait_for_ready(api_key, snapshot_id)`:
    - Polls `GET /datasets/v3/progress/{snapshot_id}` every `POLL_INTERVAL_SEC` until:
      - `status == "ready"` → returns `True`.
      - `status == "failed"` → logs error and returns `False`.
      - 404 → logs a warning and returns `True` (allowing download attempt).
      - Timeout after `POLL_TIMEOUT_SEC` → returns `False`.
  - `download_snapshot(api_key, snapshot_id)`:
    - Calls `GET /datasets/v3/snapshot/{snapshot_id}?format=json` (same endpoint as scrape_download.py).
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
    - Triggers a collection (with city and radius for location), waits for the snapshot to be ready, downloads it, normalizes each record, and upserts via `upsert_listing` into the SQLite DB at `db_path`.
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

### `uvrental.build_page` and run_status (Phase 1)

Phase 1 adds **run status** tracking and a **static HTML page** generated from the SQLite DB.

- **run_status table** (`db.py`):
  - Single row (id=1) with: `last_run_ts`, `success`, `scraped`, `thrown`, `duplicate`, `added`, `total_count`, `new_count`, `updated_count`, `llm_processed`, `displayed`.
  - Updated by `fetch.py` after each run (`update_run_status_after_fetch`), by the future LLM step (`update_run_status_after_llm`), and by `build_page.py` after rendering (`update_run_status_after_build_page(conn, displayed=N)`).
  - **K removed** (count of listings phased out by the 30-day window) is **optional** per plan and is **not** stored in `run_status` in the current implementation.

- **build_page.py**:
  - Reads from env: `LISTINGS_DB`, `BUILD_PAGE_OUTPUT` (default `docs`), `PRICE_MAX`, `PRICE_MIN`.
  - Opens the DB, queries listings that are **(a)** within the configured price range and **(b)** within the **30-day window** (see below), and reads `run_status`.
  - Renders static HTML: run-status banner then list of listings (title, link, price, beds, baths, address). Writes `index.html` under the output directory, then calls `update_run_status_after_build_page(conn, displayed=len(listings))`.

**30-day phased removal (view-based):**
- Listings are considered **removed** for display purposes when `last_seen` is older than 30 days. Phase 1 implements this as a **read-time filter** only: no `removed_at` or `status` column is added to the `listings` table. `build_page.py` uses a UTC cutoff `now - 30 days` and includes only rows with `last_seen >= cutoff`. Physical **row deletion** (garbage collection) of very old listings is **deferred** to a later phase or a separate maintenance script.

---

### `uvrental.brightdata` and `uvrental.brightdata_download` – Bright Data helpers

These two modules are used by the CLI scripts under `scripts/` to work with Bright Data’s Dataset API.

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
     - Calls `GET https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}?format=json`.
     - If status 202 → prints a “not ready” message and exits.
     - On success, saves the payload to `marketplace_snapshot_{snapshot_id}.json` and prints the approximate record count (handles both list and common object‑with‑array shapes).

**Separation of concerns:**

- `scrape.py` is **fire‑and‑forget**: trigger a job and log the `snapshot_id` for later.
- `scrape_download.py` is **idempotent** and cheap: check a specific or latest `snapshot_id` once and only download when the job is ready, so you don’t need a long‑running process waiting.

---

## Script‑by‑script reference

This section documents each Python script in the repo and the key functions within it, reflecting the **current** workflow.

### `db.py` – schema, dedup, and run status

#### `normalize_address(raw)`

- Normalize free‑form addresses for deduplication (lowercase, strip punctuation, collapse whitespace, normalize street suffixes like `st → street`, `ave → avenue`).

#### `get_connection(db_path)`

- Open or create the SQLite database at `db_path`, set `row_factory = sqlite3.Row`, ensure tables exist via `init_schema`, and return the connection.

#### `init_schema(conn)`

- Create (idempotently):
  - `listings` table with uniqueness on `(source, source_listing_id)`, normalized address fields, and optional `extracted` and `canonical_listing_id`.
  - `run_status` table with metrics for fetch/ingest, LLM processing, and page builds.

#### `_now_iso()`

- Internal helper that returns the current UTC time as an ISO‑8601 string; used for `first_seen`, `last_seen`, and `run_status.last_run_ts`.

#### `upsert_listing(conn, *, source, source_listing_id, link, ..., extracted=None)`

- Insert or update a row in `listings` by `(source, source_listing_id)`:
  - Computes `normalized_address` from `address_raw` unless explicitly provided.
  - On insert, sets `first_seen` and `last_seen` to now.
  - On update, refreshes most fields and `last_seen` while leaving `first_seen` unchanged.
  - Stores structured `extracted` data as JSON text and uses `COALESCE` so `None` does not erase existing extractions.
  - Performs cross‑source dedup: when `normalized_address` is non‑empty, links to another listing with the same normalized address but a different `source` via `canonical_listing_id`.

#### `update_run_status_after_fetch(conn, *, success, scraped, thrown, duplicate, added, total_count)`

- Upsert the single `run_status` row to record metrics after an ingest run:
  - `scraped`: total records seen from snapshots.
  - `thrown`: invalid/error records skipped.
  - `duplicate`: existing rows updated.
  - `added`: new rows inserted.
  - `total_count`: `COUNT(*)` in `listings` after the run.
- Preserves any existing `llm_processed` and `displayed` values.

#### `update_run_status_after_llm(conn, *, llm_processed)`

- Future‑phase hook for the LLM/Claude extraction step:
  - Ensures a `run_status` row exists.
  - Updates `last_run_ts` and `llm_processed`, leaving fetch metrics and `displayed` unchanged.

#### `update_run_status_after_build_page(conn, *, displayed)`

- Record how many rows were actually rendered into the static HTML page by `build_page.py`:
  - Ensures a `run_status` row exists.
  - Updates `last_run_ts` and `displayed`, preserving fetch and LLM metrics.

#### `get_run_status(conn)`

- Read helper that returns the single `run_status` row (`id = 1`) or `None` if no runs have been recorded yet.

---

### `ingest_records.py` – snapshot ingestion and normalization

This module replaces the older `fetch.py` pipeline. Instead of calling Bright Data directly, it works with **snapshot JSON files** that have been downloaded by `scrape.py` / `scrape_download.py`.

#### Constants and helpers

- **`LISTINGS_DB` / `DEFAULT_DB`**: Env key and default path for the main SQLite file (`"listings.db"`).
- **`SNAPSHOT_HISTORY_PATH`**: Path to `snapshot_history.jsonl`, shared with the `scrape*` scripts.
- **`MARKETPLACE_ITEM_BASE`**: Base URL (`https://www.facebook.com/marketplace/item`) for canonical item links.
- **`MOCK_RECORDS`**: Two mock listings used by `run_fetch_dry_run` and tests.
- **`_env(key, default=None)`**: Simple env helper that reads and strips values, falling back to `default`.

#### `_source_listing_id(record)`

- Compute a stable per‑source ID:
  - Prefer `product_id`, `listing_id`, `id`, then `listingID` if present.
  - Otherwise, hash `link`/`url`/`listing_url` to a 32‑character SHA‑256 prefix.
  - Fall back to hashing `title` as a last resort.

#### `_norm_price(val)` / `_norm_num(val)`

- Normalize numeric inputs:
  - `_norm_price`: strips `$` and commas before parsing; returns `float` or `None`.
  - `_norm_num`: parses generic numeric strings; returns `float` or `None`.

#### `_address_raw(record)`

- Derive a single `address_raw` field from various shapes:
  - If `location` is a string, returns it.
  - If `location` is a dict, joins `city`, `state`, `address`, `street`, `region`.
  - Otherwise tries `address`, `address_raw`, `city`, `location_name` in that order.

#### `_numeric_listing_id(record)`

- Extract a numeric Marketplace id when possible:
  - Scans `listing_id`, `product_id`, `item_id`, `id` for digit‑like values.
  - If not found, tries to parse `/marketplace/item/{id}` or `/item/{id}` from links.

#### `normalize_record(record)`

- Map a raw Bright Data record to the internal listing schema:
  - `source_listing_id`: from `_source_listing_id`.
  - `link`: canonical `MARKETPLACE_ITEM_BASE/{id}/` when `_numeric_listing_id` succeeds, else a best‑effort URL.
  - `title`: from `title` or `name`.
  - `price`: from `price`/`final_price`/`initial_price`/`listing_price` via `_norm_price`.
  - `beds`: from `beds`/`bedrooms`/`bed` via `_norm_num`.
  - `baths`: from `baths`/`bathrooms`/`bath` via `_norm_num`.
  - `address_raw`: from `_address_raw`.

#### `_load_snapshot_payload(payload)`

- Normalize snapshot JSON shapes into a list of dicts:
  - If `payload` is a list → return the list of dicts.
  - If `payload` is a dict → return any list under `data` / `results` / `listings` / `items` / `records`, or wrap the dict as a single‑element list.

#### `load_snapshot_file(path)`

- Load `marketplace_snapshot_*.json` files written by `scrape_download.py`, parse them, call `_load_snapshot_payload`, log the count, and return the list of records.

#### `ingest_records(db_path, records)`

- Core ingestion loop from Bright Data records into SQLite:
  - Uses `get_connection(db_path)` from `db.py`.
  - Counts `scraped` as the total number of input records.
  - Skips “thrown” records:
    - Non‑dict entries.
    - Entries with `error` or `error_code` set.
    - Entries whose normalized `link` is empty or falls back to the generic Marketplace root URL.
  - For each remaining record:
    - Builds `norm = normalize_record(record)`.
    - Checks if a listing with `source="facebook_marketplace"` and the same `source_listing_id` already exists:
      - If yes → increments `duplicate`.
      - If no → increments `added`.
    - Calls `upsert_listing` with the normalized fields.
  - After the loop:
    - Computes `total_count = COUNT(*) FROM listings`.
    - Calls `update_run_status_after_fetch` with `success=True` and the computed counters.
  - Returns the number of processed (non‑thrown) records.

#### `ingest_snapshot_file(db_path, snapshot_path)`

- Convenience wrapper:
  - Loads a single snapshot file via `load_snapshot_file`.
  - Calls `ingest_records` and returns the ingested count.

#### `_append_history(snapshot_id, status)`

- Append a JSON line to `snapshot_history.jsonl` recording the new `status` for a given `snapshot_id` with current UTC timestamps.

#### `_latest_snapshot_states()`

- Build a map of `snapshot_id → latest_state` by reading `snapshot_history.jsonl` and keeping only the last record seen for each id.

#### `ingest_all_downloaded_from_history(db_path=None)`

- End‑to‑end ingestion of all snapshots whose **latest** status is `"downloaded"`:
  - Resolve `db_path` from env if not provided.
  - Read snapshot states via `_latest_snapshot_states()`.
  - For each snapshot with `status == "downloaded"` and an existing `marketplace_snapshot_{snapshot_id}.json` file:
    - Ingest it via `ingest_snapshot_file`.
    - Append a new `"ingested"` status via `_append_history`.
  - Log and return the total number of records ingested across all such snapshots.

#### `run_fetch_dry_run(db_path)`

- Insert `MOCK_RECORDS` into the DB using `normalize_record` and `upsert_listing`, without calling Bright Data.
- Used by the test suite as a fast, deterministic Phase‑0 pipeline check.

#### CLI block (`if __name__ == "__main__":`)

- Resolve `db_path` from `LISTINGS_DB` / `DEFAULT_DB`.
- Call `ingest_all_downloaded_from_history(db_path)` and log how many records were ingested from downloaded snapshots.

---

### `build_page.py` – static HTML generation and Utah‑only filtering

#### `_env(key, default=None)` / `_parse_int_env(key, default)`

- Helpers to read string and integer environment variables with safe defaults for:
  - `LISTINGS_DB`, `BUILD_PAGE_OUTPUT`, `PRICE_MAX`, `PRICE_MIN`.

#### `_thirty_days_ago_iso()`

- Compute the ISO timestamp for “now minus 30 days” in UTC; used as the `last_seen` cutoff for which listings are considered “in range” for display.

#### `_is_clearly_utah(address_raw)`

- Heuristic filter for Utah‑only listings:
  - Returns `True` when the address string clearly includes “utah” or an obvious `UT` state marker.
  - Returns `False` for empty/unknown addresses or clearly non‑Utah strings.

#### `_delete_non_utah_rows(conn)`

- Clean up pass that deletes rows from `listings` whose `address_raw` fails `_is_clearly_utah`.
- Keeps the DB and rendered page focused on Utah Valley.

#### `_format_run_ts(iso_ts)`

- Parse a `run_status.last_run_ts`‑style ISO string and format it as `YYYY-MM-DD HH:MM UTC`, falling back to the raw string or `—` on error.

#### `build_page()`

- Main Phase‑1 function:
  - Resolve DB path and output directory from env (`LISTINGS_DB`, `BUILD_PAGE_OUTPUT`).
  - Parse price limits from env (`PRICE_MIN`, `PRICE_MAX`) with defaults.
  - Compute the 30‑day cutoff timestamp.
  - Open the DB via `get_connection`.
  - Delete clearly non‑Utah listings via `_delete_non_utah_rows`.
  - Query `listings` for rows where:
    - `last_seen >= cutoff`, and
    - `price` is `NULL` **or** `PRICE_MIN <= price <= PRICE_MAX`.
  - Read `run_status` via `get_run_status`.
  - Build an HTML document with:
    - A “Run status” section summarizing the latest ingest.
    - A “Listings” section with each listing’s link, price, beds/baths, and address.
  - Write `index.html` under `BUILD_PAGE_OUTPUT` (defaults to `docs/index.html`).
  - Call `update_run_status_after_build_page(conn, displayed=len(rows))`.

---

### `main.py` – orchestrator and DB inspector

#### `print_listings(db_path)`

- Open the DB via `get_connection`, fetch all rows from `listings` ordered by `id`, and print a human‑readable summary including source, IDs, title, link, price, beds/baths, address, and timestamps.

#### `main()`

- Orchestrate the happy path:
  - Resolve `db_path` from `LISTINGS_DB` / `DEFAULT_DB` via `_env` from `ingest_records.py`.
  - Call `ingest_all_downloaded_from_history(db_path)` to ingest any snapshots whose latest state is `"downloaded"`.
  - Print how many records were ingested.
  - Call `print_listings(db_path)` for a quick DB inspection.
  - Call `build_static_page()` (aliased from `build_page.build_page`) to regenerate the static HTML page.

**CLI:** `python main.py` – assumes you have already run `scrape.py` and `scrape_download.py` to trigger and download snapshots.

---

### `scrape.py` – trigger snapshots and log history

This is a script‑style module (no top‑level functions) that:

- Loads `BRIGHTDATA_API_KEY` from the environment and exits if missing.
- Builds a Bright Data Dataset API `trigger` URL with:
  - `dataset_id=gd_lvt9iwuh6fbcwmx1a`
  - `type=discover_new`, `discover_by=keyword`
  - `limit_per_input` (default 10; adjust for production)
- Sends a POST request with a payload containing one input:
  - `keyword: "Apartment"`
  - `city: "Provo, UT"`
  - `radius: 20`
  - `date_listed: ""`
- On success:
  - Prints the JSON response.
  - Extracts `snapshot_id` / `snapshot_ID`.
  - Appends a line to `snapshot_history.jsonl` with `status: "initiated"` and timestamps.

---

### `scrape_download.py` – check snapshot status and download JSON

#### `_append_history(snapshot_id, status)`

- Append a record to `snapshot_history.jsonl` with `snapshot_id`, `status` (e.g. `"running"`, `"downloaded"`), and timestamps.

#### `_latest_snapshot_id()`

- Read `snapshot_history.jsonl`, scanning from the end to find the latest `snapshot_id` that does **not** already have a `"downloaded"` state.
- Exit with an error message if none can be found.

#### Script flow

- Load `BRIGHTDATA_API_KEY` from env and exit if missing.
- Determine the snapshot id:
  - If an argument is provided: use `sys.argv[1]`.
  - Otherwise: call `_latest_snapshot_id()` and print which snapshot is being used.
- Call `GET {PROGRESS_URL}/{snapshot_id}`:
  - If 404: report and exit with non‑zero code.
  - Otherwise: parse JSON, print status, and:
    - If `status != "ready"`: append `"running"` to history and exit without downloading.
    - If `status == "ready"`: proceed to download.
- Call `GET {SNAPSHOT_DOWNLOAD_URL}/{snapshot_id}?format=json`:
  - If 202: report “not ready at download time” and exit.
  - On success:
    - Save the payload to `marketplace_snapshot_{snapshot_id}.json`.
    - Count approximate records (handles both list and common object‑with‑array shapes) and print the count.
    - Append `"downloaded"` to history via `_append_history`.

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

- `tests/unit/test_build_page.py`
  - Tests `_thirty_days_ago_iso()` cutoff ordering: 31 days ago is before cutoff, 29 days ago is after (guards against off-by-one in the 30-day window).

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

  - `tests/integration/test_phase1_build_page_placeholder.py` – Phase 1: runs `run_fetch_dry_run` then `build_page`, asserts HTML contains run status and listing content and that `displayed` is updated; includes test that listings with `last_seen` older than 30 days are excluded from the page.
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
  - `BRIGHTDATA_DATASET_ID`, `BRIGHTDATA_KEYWORD`, `BRIGHTDATA_CITY`, `BRIGHTDATA_RADIUS_MILES`, `BRIGHTDATA_LIMIT_PER_INPUT` – optional Bright Data parameters for Phase 0.

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

- **Phase 1 (implemented):**
  - run_status table and updates from `fetch.py` and `build_page.py`; static webpage generator `build_page.py` with price filter and **view-based 30-day removal** (filter by `last_seen` at read time; no `removed_at` column; run_status does not track K removed).
- **Planned next steps (per `plan/` docs):**
  - Phase 2+: TOML config loader, Claude API extraction for new in‑range listings only, GitHub Actions workflows, multi‑site support, and robustness improvements.

This document should be updated whenever major architectural changes are made (new phases implemented, new components added, or responsibilities of existing modules change).

