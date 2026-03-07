# Contributing

Thanks for your interest in the Utah Valley Rental Skimmer. This document explains how to run the project locally and run tests.

## Running locally

1. **Clone the repo** and enter the project directory.

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   Or install in editable mode with dev dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. **Set environment variables.** Copy `.env.example` to `.env` and fill in:
   - `BRIGHTDATA_API_KEY` – required for `scripts/scrape.py` and `scripts/scrape_download.py`
   - `ANTHROPIC_API_KEY` – required for the full pipeline (ingest + extraction + build)

   Do not commit `.env` or any file containing API keys.

5. **Run the pipeline:**
   - Trigger a snapshot: `python scripts/scrape.py`
   - Download snapshot: `python scripts/scrape_download.py`
   - Full pipeline (ingest → extract → build): `python main.py`

   See [README.md](README.md) for the full flow and optional env vars.

## Running tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=uvrental
```

## Data and CI

- **SQLite and snapshot data** (e.g. `listings.db`, `snapshot_history.jsonl`, `snapshots/`) live in a separate private repo used by CI. They are not committed to this public repo.
- For design, module roles, and data flow, see [ARCHITECTURE.md](ARCHITECTURE.md).
