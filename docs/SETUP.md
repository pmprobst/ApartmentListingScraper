# Setup Guide

This document explains how to configure the Utah Valley Rental Skimmer for local use and GitHub Actions.

## Local Development

### Prerequisites

- Python 3.9+
- API keys (Bright Data, Anthropic)

### Configuration

1. Copy `config.toml` from the repo root (or use `plan/config_schema.toml` as reference).
2. Edit `config.toml` to set paths, search criteria, and Claude settings.
3. Create a `.env` file with secrets (never commit this):

   ```
   BRIGHTDATA_API_KEY=your_bright_data_api_key
   ANTHROPIC_API_KEY=your_anthropic_api_key
   ```

4. Optional env overrides for local testing:
   - `LISTINGS_DB` – SQLite path (overrides `paths.db`)
   - `BUILD_PAGE_OUTPUT` – output directory (overrides `paths.output`)
   - `SNAPSHOT_DATA_DIR` – directory for `snapshot_history.jsonl` and `snapshots/` (overrides default: project root)
   - `PRICE_MIN` / `PRICE_MAX` – override config price filter (e.g. for CI or local testing)
   - `DISPLAY_DAYS` – show listings with last_seen within this many days (default 30; e.g. 90 for older data)
   - `CONFIG_FILE` – path to config (overrides default)
   - `CLAUDE_MODEL` – Claude model name (overrides `claude.model`)

### Running the Pipeline

```bash
# Trigger Bright Data snapshot
python scripts/scrape.py

# Download when ready (check status)
python scripts/scrape_download.py

# Ingest, extract (new only), build page
python scripts/ingest_records.py
python scripts/extract_new.py
python scripts/build_page.py

# Or run full pipeline at once
python scripts/run_pipeline.py
```

---

## GitHub Actions (CI)

The pipeline runs on a schedule (every 12 hours) and optionally on push to `main`. The SQLite database is stored in a **separate private repo** so it never appears in the public codebase.

### 1. Create a Private Repo for the Database

1. Create a new **private** repository (e.g. `apartment-listings-db`).
2. Initialize it (can be empty or with a placeholder `listings.db`).
3. Note the full repo name: `owner/repo-name`.

### 2. Create a Personal Access Token (PAT)

1. GitHub → Settings → Developer settings → Personal access tokens.
2. Generate a token with `repo` scope (full control of private repositories).
3. Copy the token; you will add it as a secret.

### 3. Add GitHub Secrets

In your **public** repo (this repo): Settings → Secrets and variables → Actions.

Add these secrets:

| Secret | Description |
|--------|-------------|
| `BRIGHTDATA_API_KEY` | Bright Data API key |
| `ANTHROPIC_API_KEY` | Anthropic (Claude) API key |
| `PRIVATE_DB_REPO_TOKEN` | PAT with access to the private DB repo |
| `PRIVATE_DB_REPO` | (Optional) Private repo name, e.g. `owner/apartment-listings-db`. Default: `{owner}/apartment-listings-db` |

### 4. Workflow Behavior

- **Checkout** – public repo (code only)
- **Clone** – private DB repo into `db_repo/` (can contain `listings.db`, `snapshot_history.jsonl`, `snapshots/`)
- **Run** – scrape → download → ingest → extract → build_page (all use `db_repo/` for DB and snapshot data via `SNAPSHOT_DATA_DIR`)
- **Push to private repo** – updated `listings.db`, `snapshot_history.jsonl`, and `snapshots/` in `db_repo/` are committed and pushed
- **Push site** – generated `docs/` to the public repo (GitHub Pages)

The SQLite database and snapshot data are never committed to the public repo.

### 5. GitHub Pages

Enable GitHub Pages for the public repo (Settings → Pages → Source: Deploy from branch → main → /docs).
