# Phase 1: Run status and static webpage

Add run status tracking, **price filter**, **30-day phased removal**, and webpage generation. Build on Phase 0: fetch.py will now update run_status and apply removal logic; build_page.py reads listings (within price range and within 30-day window) and run_status and generates the static HTML.

---

## Detailed steps

### 1. Run status

- Add a **run_status** table or small status store (e.g. in the same SQLite DB: table with last run timestamp, success/failure, total listing count, **N new**, **M updated**, and optionally **K removed**). After each run of `fetch.py`, record these values. They will be read by `build_page.py` for the webpage indicator (see [features.md](features.md) §8).
- Update **fetch.py** from Phase 0 so it writes to **run_status** after each run (timestamp, success, count).

### 2. Price filter (Phase 1)

- Apply a **configurable price filter** using at least **price_max** (and optionally **price_min**). Read from env or minimal config (e.g. `PRICE_MAX`, `PRICE_MIN`); full TOML config comes in Phase 2.
- **build_page.py** must **only include listings within the configured price range** on the webpage. Listings outside the range are hidden (not shown at all). From Phase 1 onward, the generated page shows only in-range listings.

### 3. 30-day phased removal

- Listings are **phased out 30 days after last being seen** (see [features.md](features.md) and [reference.md](reference.md)#new-vs-updated-vs-removed). Implemented as a **view-based** approach (no schema change):
  - "Removed" is a **filter at read time**: `build_page.py` excludes listings with `last_seen` &lt; now − 30 days (UTC). No `removed_at` or `status` column is added.
  - **build_page.py** only includes listings that are **within the 30-day window** (and within price range). **K removed** in run_status is optional per plan and is **not** implemented in the current code.

### 4. Webpage generation (`build_page.py`)

- Implement `build_page.py` that:
  - Reads DB path, output path, and **price_max** / **price_min** (and optional 30-day cutoff) from env or minimal config.
  - Opens the SQLite DB, reads **listings** that are **(a)** within the configured price range and **(b)** within the 30-day window (last_seen &gt;= cutoff), and **run_status**.
  - Generates **static HTML** (and optional CSS/JS) that lists those listings (title, link, price, beds, baths, address, etc.) and displays the **run status** (last run time, success/failure, total count, N new, M updated, and optionally K removed per [features.md](features.md)).
  - Writes output to the configured directory (e.g. `docs/` for GitHub Pages).
- Output must be static (no server-side logic) so GitHub Pages can serve it.

### 5. Local test

- Run `fetch.py`, then `build_page.py`. Verify: run_status is updated after fetch; generated page shows only in-range and within-30-day listings and run status. Optionally verify that DB rows with `last_seen` older than 30 days do **not** appear on the generated page (integration tests cover this).

---

## Requirements to pass before moving to Phase 2

- [ ] **run_status** is stored (SQLite table or file) and updated by fetch.py after each run (timestamp, success/failure, total count, N new, M updated; optionally K removed).
- [ ] **Price filter** is applied: build_page.py only includes listings within configured price_max (and optional price_min).
- [x] **30-day phased removal** is implemented: listings with last_seen older than 30 days are excluded at read time (view-based); build_page shows only listings within the 30-day window (and price range). K removed in run_status is optional and not implemented.
- [ ] **build_page.py** reads SQLite (listings + run_status) and generates static HTML with listing list (filtered by price and 30-day window) and run status indicator.
- [ ] **End-to-end** (fetch → build_page) runs locally and produces a valid HTML page with at least one listing and run status visible.

When all checkboxes are satisfied, proceed to [phase-2.md](phase-2.md).
