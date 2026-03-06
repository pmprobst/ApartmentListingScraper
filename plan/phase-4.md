# Phase 4: Webpage and observability

Polish the generated webpage: show extracted fields, sorting/filtering, and run status. Ensure GitHub hosting is solid and scripts are runnable locally or via Actions.

---

## Detailed steps

### 1. Listing display with extracted fields

- Update `build_page.py` so the generated HTML displays **Claude-extracted fields** (washer/dryer, renter-paid fees, availability, pet policy, parking, lease length, deposit, amenities, etc.) for each listing when present. Use the **extracted** JSON (or columns) from the listings table.
- Format for readability (e.g. labels, line breaks, or a small table per listing). Handle missing extracted data gracefully (show "—" or hide section).

### 2. Sorting and filtering (optional)

- If config or a simple convention supports it, allow **sorting** (e.g. by price, first_seen, last_seen) and **filtering** (e.g. by price range, source, beds) in the generated page. This can be client-side (JavaScript) or pre-computed in the HTML (e.g. separate sections). Minimum: list all listings; preferred: sort by date or price.

### 3. Run status indicator

- Ensure the **run status** is clearly visible on the page: **last run time** (human-readable), **success/failure**, **total listing count**, and **N new, M updated** (required per [features.md](features.md)). If the last run failed, show "Last run: failed" so the user has observability without checking Actions logs.

### 4. GitHub hosting

- Confirm the workflow **commits and pushes** the generated files to the branch or folder that **GitHub Pages** uses (e.g. `docs/` on main or `gh-pages` branch). No manual push should be required for the site to update after a run.
- Document in README or plan how to enable Pages (Settings → Pages → source branch/folder).

### 5. Scripts and local run

- Document that `python scrape.py`, `python scrape_download.py`, `python ingest_records.py`, and `python build_page.py` can be run **locally** (with env vars for API keys and config pointing to local paths). Same scripts are used in GitHub Actions. Optional: single entry script that runs scrape → download → ingest → extract → build_page for local testing.

### 6. Optional: new-listing alerts

- If desired, add a minimal **alert** (e.g. email or desktop notification) when new listings appear. Not required to pass Phase 4.

### 7. Future extraction improvements

- After the initial deployment, **beef up Claude extraction logic** for:
  - `non_included_utilities_cost` (compute and normalize a single monthly total when possible).
  - `lease_length` (better handling of vague or relative date ranges).
  These should be treated as a follow-up step once the core pipeline and page are stable.

---

## Requirements to pass before moving to Phase 5

- [ ] **Extracted fields** are shown on the webpage for each listing (when available); missing data is handled without errors.
- [ ] **Webpage shows only in-range listings:** Listings outside the configured price range are hidden (not shown); see [features.md](features.md).
- [ ] **Run status** is visible on the page (last run time, success/failure, total count, N new, M updated).
- [ ] **Sorting or filtering** is available (at least one of: sort by price, date, or filter by source/price). Prefer sort by date or price.
- [ ] **GitHub Pages** is configured and the site updates automatically after each workflow run; no manual push needed.
- [ ] **Scripts** are documented for local use (`scrape.py`, `scrape_download.py`, `ingest_records.py`, `build_page.py`, env vars, config).

When all checkboxes are satisfied, proceed to [phase-5.md](phase-5.md).
