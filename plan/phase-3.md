# Phase 3: Claude API extraction for new listings only, then expand sites and GitHub Actions

Add Claude extraction (only for new listings within price filter), then add GitHub Actions and optional additional sites. SQLite is stored in a **separate private repo** (not in the public repo); see workflow steps below.

---

## Detailed steps

### 1. Config loading (required)

- Refactor `fetch.py` and `build_page.py` to use the full **config from Phase 2** (TOML). **This is required.** Pipeline scripts must read paths, search (price_max, price_min, location, etc.), bright_data, run_status, and claude settings from the TOML config. API keys (Bright Data, Claude) remain in **env / GitHub Secrets** only; do not put secrets in config.

### 2. Price filter (already in Phase 1)

- **Price filter** is already implemented in Phase 1 (build_page shows only in-range listings). In Phase 3, ensure the **Claude extraction** step uses the same config: only consider listings that are **new** (first_seen = this run) and **within price** (price_min ≤ price ≤ price_max from config). Listings outside the range must not be sent to Claude (see [features.md](features.md)).

### 3. Claude extraction step

- Implement a step (script or function) that:
  - Reads from SQLite: listings where **first_seen** equals the current run (or “new” flag) and **price** <= config price_max.
  - For each such listing, sends **title + description/text** (and any other text fields) to the **Claude API** using the prompt and schema validated in Phase 2.
  - Parses the response and writes the extracted fields into the listing row (e.g. **extracted** JSON column or separate columns).
- Use Claude API key from env (e.g. `ANTHROPIC_API_KEY`). Reuse model and timeout from config.
- Do **not** re-run extraction for listings that already have extracted data from a previous run (only new listings in this run).

### 4. Wire into pipeline

- After `fetch.py` runs (and upserts new/updated listings), run the **Claude extraction** step for new listings only, then run `build_page.py`. Pipeline order: fetch → extract (new only) → build_page.

### 5. GitHub Actions workflow (separate private repo for DB)

- Add `.github/workflows/run-pipeline.yml` (or similar) that:
  - Triggers on **schedule** (every 6–24 hours per [features.md](features.md)) and optionally on push to main.
  - **Checks out** the **public repo** (this repo: code only). Uses a **secret** (e.g. PAT or deploy key) with access to a **separate private repo** that holds **only the SQLite DB** (and any run_status files).
  - **Fetches the DB from the private repo** (e.g. clone the private repo into a subdir or download the DB file via API) so the workflow has the current SQLite file in the workspace.
  - Sets up **Python**, installs dependencies (e.g. from requirements.txt).
  - Runs **fetch.py** (config points to the DB path in the workspace).
  - Runs the **Claude extraction** step for new listings.
  - Runs **build_page.py**.
  - **Commits and pushes** the updated SQLite file (and any run_status) **back to the private repo** (not to the public repo).
  - **Commits and pushes** the generated static site (e.g. `docs/` or `gh-pages` branch) to the **public repo** so GitHub Pages serves it.
- Store **Bright Data API key**, **Claude API key**, and **private-repo access token** in **GitHub Secrets**; pass them as env vars. The **SQLite DB never appears in the public repo**; only code and the generated HTML are public.

### 6. New vs updated tagging

- Ensure the pipeline correctly tags listings as **new** (first_seen = this run) vs **updated** (existing row, last_seen updated). Use this so Claude runs only on new listings and the webpage can show “new” badge if desired.

### 7. Optional: add another site (Zillow, KSL, or Apartments.com)

- If time permits, add a second source (Bright Data if available, or direct scraping). Reuse the same SQLite schema and upsert logic; use a different **source** value (e.g. `zillow`). Ensure (source, source_listing_id) and normalized_address are set so dedup still works. Not required to pass Phase 3 if the rest is done.

---

## Requirements to pass before moving to Phase 4

- [ ] **Pipeline scripts read from TOML config:** fetch.py and build_page.py read paths, search, bright_data, run_status, and claude from config; API keys from env only.
- [ ] **Price filter** (from Phase 1) is respected by Claude step: only listings within price_max/price_min (and new) are sent to Claude.
- [ ] **Claude extraction** runs only for **new** listings (first_seen = current run) within price; extracted data is stored in SQLite (extracted column or equivalent).
- [ ] **Pipeline order** is correct: fetch → Claude for new listings → build_page.
- [ ] **GitHub Actions** workflow exists, runs on schedule, **fetches DB from a separate private repo**, runs fetch → extract → build_page, **pushes DB updates back to the private repo**, and pushes generated site to the public repo (e.g. docs/ or gh-pages). SQLite is **never** committed to the public repo.
- [ ] **Secrets** (Bright Data, Claude API, private-repo token) are stored in GitHub Secrets and used as env vars in the workflow.
- [ ] At least one successful full run via GitHub Actions (or documented manual equivalent) that updates the private DB repo and the live page.

When all checkboxes are satisfied, proceed to [phase-4.md](phase-4.md).
