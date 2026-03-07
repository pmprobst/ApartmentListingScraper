# Apartment Listing Skimmer

Fetches rental listings from Facebook Marketplace (via Bright Data), stores them in SQLite, enriches them with Claude extraction, and publishes a static HTML page (e.g. GitHub Pages).

For architecture, data flow, and module details see [ARCHITECTURE.md](ARCHITECTURE.md).

## Setup

- **Python:** 3.x
- Create a virtual environment (recommended):
  ```bash
  python -m venv .venv
  source .venv/bin/activate   # Windows: .venv\Scripts\activate
  ```
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

## Environment variables

- **BRIGHTDATA_API_KEY** – required for `scripts/scrape.py` and `scripts/scrape_download.py`.
- **ANTHROPIC_API_KEY** – required for the full pipeline (ingest + extraction + build).
- **LISTINGS_DB** (optional) – path to the SQLite database. Default: `listings.db`.
- **BUILD_PAGE_OUTPUT** (optional) – output directory for generated HTML. Default: `docs`.
- **SNAPSHOT_DATA_DIR** (optional) – directory for `snapshot_history.jsonl` and `snapshots/`. Default: project root. In CI this points at the cloned private DB repo.
- **CONFIG_FILE** (optional) – path to TOML config; otherwise `config.toml` or `config_schema.toml` is used.

Do not commit `.env` or any file containing API keys. Use `.env` locally and GitHub Secrets in CI. The `.env` file is gitignored.

## End-to-end flow

1. **Trigger a snapshot:** `python scripts/scrape.py`
  Calls Bright Data and records a `snapshot_id` with status `"initiated"` in `snapshot_history.jsonl`.
2. **Download snapshot JSON:** `python scripts/scrape_download.py` [optional: `<snapshot_id>`]
  Checks all pending snapshots (oldest first); when ready, saves `snapshots/marketplace_snapshot_<snapshot_id>.json` and updates history to `"downloaded"`.
3. **Ingest, extract, and build page:** `python main.py`
  Ingests all downloaded snapshots into the DB, runs regex + Claude extraction on listings with descriptions, and builds `docs/index.html`. You can also run `python scripts/run_pipeline.py` for the same pipeline (with project root on path). The same pipeline (ingest → extract → build_page) runs in CI via `main.py`.

Output: `listings.db` and `docs/index.html` (by default). The HTML shows listings within the configured price range and 30-day window; female-only, has-roommates, and summer-only (no renewal option) listings are excluded from the page.

## GitHub Actions

Two workflows run on a daily schedule (and can be triggered manually):

- **Trigger Snapshot** (`.github/workflows/run-pipeline-trigger.yml`): Runs at **9am UTC** daily. Triggers a Bright Data snapshot and pushes the updated `snapshot_history.jsonl` to the private repo so the pipeline run can find the new snapshot.
- **Run Pipeline** (`.github/workflows/run-pipeline.yml`): Runs at **10am UTC** daily (1 hour later). It:

1. Clones a **separate private repo** that holds the SQLite DB and snapshot data (`snapshot_history.jsonl`, `snapshots/`).
2. Waits for the snapshot to be ready and downloads it (with retries).
3. Runs the pipeline (`python main.py`): ingest → extract (new listings only) → build page.
4. Pushes the updated DB and snapshot data back to the private repo.
5. Pushes the generated `docs/` to the **public repo** so GitHub Pages can serve the site.

You can also run either workflow manually from **Actions** → select the workflow → **Run workflow**.

**SQLite and snapshot data live only in the private repo**; they are never committed to this public repo.

### GitHub Secrets

Configure these under **Settings → Secrets and variables → Actions**:


| Secret                  | Required | Description                                                                          |
| ----------------------- | -------- | ------------------------------------------------------------------------------------ |
| `BRIGHTDATA_API_KEY`    | Yes      | Bright Data API key for trigger and download.                                        |
| `ANTHROPIC_API_KEY`     | Yes      | Claude API key for extraction.                                                       |
| `PRIVATE_DB_REPO_TOKEN` | Yes      | PAT or token with access to the private DB repo (for clone and push).                |
| `PRIVATE_DB_REPO`       | No       | Default: `{owner}/apartment-listings-db`. Set if your private repo has another name. |


### GitHub Pages

Enable the site under **Settings → Pages**: set **Source** to branch `main` and folder `/docs`. The workflow updates `docs/` after each run, so the site refreshes automatically.

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** – components, data flow, storage, scripts, and env vars.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** – how to run locally and run tests.
- **docs/** – Generated static site (GitHub Pages); produced by the build_page step. For setup and architecture see README and ARCHITECTURE.md above.

