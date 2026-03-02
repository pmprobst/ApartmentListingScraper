# Phase 2: Claude API extraction for new listings only, then expand sites and GitHub Actions

Add Claude extraction (only for new listings within price filter), then add GitHub Actions and optional additional sites. SQLite stays on **data/** branch.

---

## Detailed steps

### 1. Price filter

- Apply **price filter** from config (e.g. `price_max`): when reading listings for display or for Claude, exclude (or tag) listings above the max. When deciding “which listings get Claude extraction,” only consider listings that are **new** (first_seen = this run) and **within price** (price <= price_max).

### 2. Claude extraction step

- Implement a step (script or function) that:
  - Reads from SQLite: listings where **first_seen** equals the current run (or “new” flag) and **price** <= config price_max.
  - For each such listing, sends **title + description/text** (and any other text fields) to the **Claude API** using the prompt and schema validated in Phase 0.
  - Parses the response and writes the extracted fields into the listing row (e.g. **extracted** JSON column or separate columns).
- Use Claude API key from env (e.g. `ANTHROPIC_API_KEY`). Reuse model and timeout from config.
- Do **not** re-run extraction for listings that already have extracted data from a previous run (only new listings in this run).

### 3. Wire into pipeline

- After `fetch.py` runs (and upserts new/updated listings), run the **Claude extraction** step for new listings only, then run `build_page.py`. Pipeline order: fetch → extract (new only) → build_page.

### 4. GitHub Actions workflow

- Add `.github/workflows/run-pipeline.yml` (or similar) that:
  - Triggers on **schedule** (e.g. every 12 hours) and optionally on push to main.
  - **Checks out** the repo and the **data/** branch (or a step that fetches the data branch and places the SQLite file in the workspace).
  - Sets up **Python**, installs dependencies (e.g. from requirements.txt).
  - Runs **fetch.py** (config must point to the SQLite file path used on the data branch).
  - Runs the **Claude extraction** step for new listings.
  - Runs **build_page.py**.
  - **Commits and pushes** the updated SQLite file (and any run_status) back to the **data/** branch.
  - **Commits and pushes** the generated static site (e.g. `docs/` or `gh-pages` branch) so GitHub Pages serves it.
- Store **Bright Data API key** and **Claude API key** in **GitHub Secrets**; pass them as env vars in the workflow. Do **not** commit the SQLite file to **main**; only to the data branch.

### 5. New vs updated tagging

- Ensure the pipeline correctly tags listings as **new** (first_seen = this run) vs **updated** (existing row, last_seen updated). Use this so Claude runs only on new listings and the webpage can show “new” badge if desired.

### 6. Optional: add another site (Zillow, KSL, or Apartments.com)

- If time permits, add a second source (Bright Data if available, or direct scraping). Reuse the same SQLite schema and upsert logic; use a different **source** value (e.g. `zillow`). Ensure (source, source_listing_id) and normalized_address are set so dedup still works. Not required to pass Phase 2 if the rest is done.

---

## Requirements to pass before moving to Phase 3

- [ ] **Price filter** is applied from config; only listings within price_max (and new) are sent to Claude.
- [ ] **Claude extraction** runs only for **new** listings (first_seen = current run) within price; extracted data is stored in SQLite (extracted column or equivalent).
- [ ] **Pipeline order** is correct: fetch → Claude for new listings → build_page.
- [ ] **GitHub Actions** workflow exists, runs on schedule, checks out or uses **data/** branch for SQLite, runs fetch → extract → build_page, pushes DB updates to **data/** and site to Pages branch/folder. SQLite is **not** committed to main.
- [ ] **Secrets** (Bright Data, Claude API) are stored in GitHub Secrets and used as env vars in the workflow.
- [ ] At least one successful full run via GitHub Actions (or documented manual equivalent) that updates the data branch and the live page.

When all checkboxes are satisfied, proceed to [phase-3.md](phase-3.md).
