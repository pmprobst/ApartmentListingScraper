# Phase 0: Bright Data → SQLite (foundation)

Build the data pipeline: Bright Data Facebook Marketplace API → SQLite with deduplication. Single source only; no run status or webpage yet.

---

## Detailed steps

### 1. Project setup

- Python project with dependency list (e.g. `requirements.txt`: `requests`, stdlib `sqlite3`). For this phase, use **env vars** and a **minimal config** (e.g. DB path, optional search/location params); the full config schema (TOML) is defined in [phase-2.md](phase-2.md).
- Ensure `.env` and secrets are not committed; document that Bright Data API key comes from env (e.g. `BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY` or `BRIGHTDATA_API_KEY`).

### 2. SQLite schema and deduplication

- Create the **listings** table per [reference.md#deduplication-and-sqlite-schema](reference.md#deduplication-and-sqlite-schema): `id`, `source`, `source_listing_id`, `normalized_address`, `address_raw`, `link`, `title`, `price`, `beds`, `baths`, `first_seen`, `last_seen`, `extracted` (TEXT/JSON), optional `canonical_listing_id`. UNIQUE constraint on `(source, source_listing_id)`.
- Implement **address normalization** (lowercase, strip punctuation, normalize street suffixes) and **upsert logic**: for each listing from the API, compute `source_listing_id` (from product_id or hash of link) and `normalized_address`; INSERT or REPLACE / ON CONFLICT DO UPDATE so one row per (source, source_listing_id). Set `first_seen` on insert, `last_seen` on every update.
- **Cross-source deduplication (Phase 0):** When a new row has the same non-empty `normalized_address` as an existing row from a different **source**, link them via **canonical_listing_id** (or merge) so the webpage can later show one listing with “Also on Zillow, KSL.” Implement the schema and logic in Phase 0 so adding new sources does not require schema changes.

### 3. Bright Data integration (`scripts/scrape.py`, `scripts/scrape_download.py`, `uvrental.ingest`)

- Implement **`scripts/scrape.py`** to:
  - Read Bright Data params from env or a minimal config (location, category/keyword, etc.).
  - Call the **Bright Data Facebook Marketplace Dataset API** to trigger a snapshot.
  - On success, record `snapshot_id` with status `"initiated"` and a timestamp in `snapshot_history.jsonl`.
- Implement **`scripts/scrape_download.py`** to:
  - Read `snapshot_history.jsonl`, find snapshots whose latest status is not `"downloaded"` or `"ingested"`.
  - For each, call the Bright Data **progress** and **snapshot** endpoints:
    - If not ready, record `"running"` and exit.
    - If ready, download JSON to `marketplace_snapshot_<snapshot_id>.json` and record `"downloaded"`.
- Implement **`uvrental.ingest`** to:
  - Read DB path from env (`LISTINGS_DB`) or minimal config.
  - Load downloaded `marketplace_snapshot_*.json` files and normalize each listing to the common schema (title, link, price, beds, baths, address_raw, source = `facebook_marketplace`, product_id or link hash for source_listing_id).
  - Compute `normalized_address` for each listing and upsert into **listings** only (no run_status in this phase).
  - Update `snapshot_history.jsonl` with `"ingested"` status when a snapshot has been successfully ingested.
- Handle API errors and timeouts in the scraper scripts; log failures.

### 4. Local test

- Run the full pipeline:
  - `python scrape.py`
  - `python scrape_download.py`
  - `python main.py`
  Verify: DB contains listings with no duplicate (source, source_listing_id); first_seen and last_seen are set correctly.

---

## Requirements to pass before moving to Phase 1

- [ ] **SQLite schema** is created with listings table (id, source, source_listing_id, normalized_address, address_raw, link, title, price, beds, baths, first_seen, last_seen, extracted, optional canonical_listing_id per [reference.md](reference.md)) and UNIQUE(source, source_listing_id).
- [ ] **Upsert** ensures one row per (source, source_listing_id); first_seen and last_seen are set correctly; normalized_address is populated when address is available.
- [ ] **Cross-source deduplication:** When the same normalized_address appears for a different source, rows are linked via canonical_listing_id (or merged) per reference.md.
- [ ] **scrape.py** successfully triggers Bright Data (Facebook Marketplace) and records snapshot_ids in `snapshot_history.jsonl`.
- [ ] **scrape_download.py** successfully checks progress and downloads ready snapshots to `marketplace_snapshot_*.json`, recording `"downloaded"` in history.
- [ ] **ingest_records.py** successfully normalizes snapshot JSON and upserts into SQLite only.
- [ ] **End-to-end** (scrape → download → ingest) runs locally and produces a populated SQLite DB with at least one listing.

When all checkboxes are satisfied, proceed to [phase-1.md](phase-1.md).
