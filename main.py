"""
Pipeline orchestrator for Utah Valley Rental Skimmer.

Runs the full pipeline: ingest downloaded Bright Data snapshots into SQLite,
run extraction (regex then Claude until queue empty), then build the static HTML page.
Designed to be run locally or from GitHub Actions.
"""

from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from uvrental.pipeline import run_full_pipeline

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)


def main() -> None:
    try:
        run_full_pipeline()
    except Exception as e:
        print(f"Pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

