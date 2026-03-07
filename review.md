# Review checklist

Checklist of every script and module for code review, testing, or onboarding.

## Scripts (entry points)

- [ ] **main.py** – Full pipeline entry point (ingest → extract → build page)
- [x] **scripts/scrape.py** – Trigger Bright Data snapshot
- [x] **scripts/scrape_download.py** – Download snapshot JSON (optional snapshot_id arg)
- [ ] **scripts/run_pipeline.py** – Same as main.py (adds project root to path)
- [ ] **scripts/ingest_records.py** – Ingest only
- [ ] **scripts/extract_new.py** – Extraction only (regex + Claude)
- [ ] **scripts/build_page.py** – Build HTML page only

## Modules (uvrental package)

- [ ] **uvrental/__init__.py** – Package init, lazy-loaded submodules
- [ ] **uvrental/config.py** – TOML + env config loader
- [ ] **uvrental/db.py** – SQLite schema, dedup, run_status
- [ ] **uvrental/ingest.py** – Bright Data snapshot ingestion and normalization
- [ ] **uvrental/pipeline.py** – run_full_pipeline() orchestration
- [ ] **uvrental/build_page.py** – Static HTML generation from DB
- [x] **uvrental/brightdata.py** – Trigger Bright Data snapshot API
- [x] **uvrental/brightdata_download.py** – Poll and download snapshot JSON
- [ ] **uvrental/extraction_regex.py** – Regex-based field extraction (Stage 1)
- [ ] **uvrental/extraction_claude.py** – Claude API extraction (Stage 2)
- [ ] **uvrental/extraction_pipeline.py** – DB-backed extraction pipeline (regex + LLM queue)
