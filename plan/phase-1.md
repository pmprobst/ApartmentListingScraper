# Phase 1: Facebook Marketplace via Bright Data (foundation)

Build end-to-end: Bright Data → SQLite (with dedup) → run status → static webpage. Single source (Facebook Marketplace) only.

---

## Detailed steps

### 1. Project setup

- Python project with dependency list (e.g. `requirements.txt`: `requests`, `toml` or `tomlkit` for config, stdlib `sqlite3`). Use config schema from Phase 0; implement **config loading** from TOML (e.g. `config.toml` or path from env).
- Ensure `.env` and secrets are not committed; document that Bright Data API key comes from env (e.g. `BRIGHTDATA_API_KEY`).

### 2. SQLite schema and deduplication

- Create the **listings** table per [reference.md#deduplication-and-sqlite-schema](reference.md#deduplication-and-sqlite-schema): `id`, `source`, `source_listing_id`, `normalized_address`, `address_raw`, `link`, `title`, `price`, `beds`, `baths`, `first_seen`, `last_seen`, `extracted` (TEXT/JSON), optional `canonical_listing_id`. UNIQUE constraint on `(source, source_listing_id)`.
- Implement **address normalization** (lowercase, strip punctuation, normalize street suffixes) and **upsert logic**: for each listing from the API, compute `source_listing_id` (from product_id or hash of link) and `normalized_address`; INSERT or REPLACE / ON CONFLICT DO UPDATE so one row per (source, source_listing_id). Set `first_seen` on insert, `last_seen` on every update.
- Optional for Phase 1: cross-source merge (canonical_listing_id); at minimum, no duplicate rows for the same (source, source_listing_id).

### 3. Run status

- Add a **run_status** table or small status store (per config: SQLite table or file). After each run of the pipeline, record: **last run timestamp**, **success/failure**, **listing count** (or similar). This will be read by `build_page.py` for the webpage indicator.

### 4. Bright Data integration (`fetch.py`)

- Implement `fetch.py` that:
  - Loads config (search, bright_data, paths).
  - Calls the **Bright Data Facebook Marketplace Scraper API** with parameters from config (location, category/keyword, etc.).
  - Normalizes each listing to the common schema (title, link, price, beds, baths, address_raw, source = `facebook_marketplace`, product_id or link hash for source_listing_id).
  - Computes `normalized_address` for each listing.
  - Opens or creates the SQLite DB (path from config), runs upserts into **listings**, and updates **run_status** (timestamp, success, count).
- Handle API errors and timeouts; log failures. On success, run status should reflect “last run: success” and listing count.

### 5. Webpage generation (`build_page.py`)

- Implement `build_page.py` that:
  - Loads config (paths).
  - Opens the SQLite DB, reads **listings** (e.g. all rows or those with last_seen in last N days) and **run_status**.
  - Generates **static HTML** (and optional CSS/JS) that lists the listings (title, link, price, beds, baths, address, etc.) and displays the **run status** (last run time, success/failure, listing count).
  - Writes output to the configured directory (e.g. `docs/` for GitHub Pages).
- Output must be static (no server-side logic) so GitHub Pages can serve it.

### 6. Local test

- Run `fetch.py` (with valid Bright Data API key and config pointing to a local SQLite file), then `build_page.py`. Verify: DB contains listings with no duplicate (source, source_listing_id); run status is updated; generated page shows listings and run status.

---

## Requirements to pass before moving to Phase 2

- [ ] **Config loading** works from TOML; all needed keys (search, bright_data, paths, run_status, dedup) are read and used.
- [ ] **SQLite schema** is created with listings table (id, source, source_listing_id, normalized_address, address_raw, link, title, price, beds, baths, first_seen, last_seen, extracted) and UNIQUE(source, source_listing_id).
- [ ] **Upsert** ensures one row per (source, source_listing_id); first_seen and last_seen are set correctly; normalized_address is populated when address is available.
- [ ] **fetch.py** successfully calls Bright Data API (Facebook Marketplace), normalizes response, and upserts into SQLite; run_status is updated after the run.
- [ ] **build_page.py** reads SQLite and run_status and generates static HTML with listing list and run status indicator.
- [ ] **End-to-end** (fetch → build_page) runs locally and produces a valid HTML page with at least one listing and run status visible.

When all checkboxes are satisfied, proceed to [phase-2.md](phase-2.md).
