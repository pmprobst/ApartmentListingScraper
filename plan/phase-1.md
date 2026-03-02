# Phase 1: Run status and static webpage

Add run status tracking and webpage generation. Build on Phase 0: fetch.py will now update run_status; build_page.py reads listings and run_status and generates the static HTML.

---

## Detailed steps

### 1. Run status

- Add a **run_status** table or small status store (e.g. in the same SQLite DB: table with last run timestamp, success/failure, listing count). After each run of `fetch.py`, record: **last run timestamp**, **success/failure**, **listing count** (or similar). This will be read by `build_page.py` for the webpage indicator.
- Update **fetch.py** from Phase 0 so it writes to **run_status** after each run (timestamp, success, count).

### 2. Webpage generation (`build_page.py`)

- Implement `build_page.py` that:
  - Reads DB path (and optional output path) from env or minimal config.
  - Opens the SQLite DB, reads **listings** (e.g. all rows or those with last_seen in last N days) and **run_status**.
  - Generates **static HTML** (and optional CSS/JS) that lists the listings (title, link, price, beds, baths, address, etc.) and displays the **run status** (last run time, success/failure, listing count).
  - Writes output to the configured directory (e.g. `docs/` for GitHub Pages).
- Output must be static (no server-side logic) so GitHub Pages can serve it.

### 3. Local test

- Run `fetch.py`, then `build_page.py`. Verify: run_status is updated after fetch; generated page shows listings and run status.

---

## Requirements to pass before moving to Phase 2

- [ ] **run_status** is stored (SQLite table or file) and updated by fetch.py after each run (timestamp, success/failure, listing count).
- [ ] **build_page.py** reads SQLite (listings + run_status) and generates static HTML with listing list and run status indicator.
- [ ] **End-to-end** (fetch → build_page) runs locally and produces a valid HTML page with at least one listing and run status visible.

When all checkboxes are satisfied, proceed to [phase-2.md](phase-2.md).
