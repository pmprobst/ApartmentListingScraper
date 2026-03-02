# Phase 5: Robustness and polish

Harden the pipeline: error handling, logging, and optional reporting. No new features required for MVP.

---

## Detailed steps

### 1. Error handling and logging

- In **fetch.py**: catch API errors (timeouts, non-2xx responses, invalid JSON). Log failures with site/source name and error message; do not crash the entire run if one source fails. Optional: **retry with backoff** (e.g. 1 retry after 5 seconds) for transient errors.
- In **Claude extraction** step: catch API errors and timeouts; log which listing failed; skip that listing or mark "extraction failed" so the pipeline can continue. Do not lose existing SQLite data.
- Ensure **run_status** can record "partial" or "failed" (e.g. fetch failed, or extract failed) so the webpage still shows last run and outcome.

### 2. Logging

- Add structured or simple **logging** (e.g. Python `logging` module) for: start/end of fetch per source, number of listings fetched, number of new vs updated, Claude extraction start/end and count, build_page start/end, any errors. Log to stdout so GitHub Actions captures it in the workflow log.

### 3. Legal and compliance

- **Document** in README or docs: we use Bright Data for Facebook Marketplace (they handle compliance); for any direct scraping added later, we will honor robots.txt and rate limits. No implementation required for Bright Data–only setup.

### 4. Optional: listing diff report

- If useful, add a **lightweight report** (e.g. markdown or text file) per run: "N new, M updated, K removed" or a short list of new/updated listing titles. This can be written to the repo (e.g. on the data branch) or only to logs. Optional for Phase 5 pass.

### 5. Documentation

- README (or plan docs) should describe: how to run locally, how to set GitHub Secrets, what the workflow does, where the SQLite file lives (data branch), and how to enable GitHub Pages.

---

## Requirements to pass before considering Phase 5 complete

- [ ] **Error handling** in fetch: API errors are caught and logged; pipeline does not lose existing DB data when a source fails. At least one retry or clear failure path is implemented.
- [ ] **Error handling** in Claude step: failures are caught and logged; pipeline continues (skip listing or mark failed); run_status can reflect failure.
- [ ] **Logging** is in place for fetch, extract, and build_page (start/end, counts, errors); visible in GitHub Actions logs when run in CI.
- [ ] **Documentation** covers: local run, GitHub Secrets, workflow behavior, data branch, and GitHub Pages setup.
- [ ] **Run status on failure:** If any step fails, the workflow still updates run_status (e.g. "last run: failed") and optionally runs build_page with existing data so the page shows current state and observability.

When all checkboxes are satisfied, Phase 5 is complete. The MVP is done; future work (more sites, alerts, drive-time feature) can follow from [reference.md](reference.md) and [features.md](features.md).
