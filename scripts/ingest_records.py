"""
CLI: Ingest downloaded Bright Data snapshots into SQLite.

Usage:
    python scripts/ingest_records.py
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Ensure project root (parent of scripts/) is on sys.path for `uvrental` imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uvrental.ingest import ingest_all_downloaded_from_history  # noqa: E402


if __name__ == "__main__":
    n = ingest_all_downloaded_from_history()
    if n == 0:
        print("No records ingested (no downloaded snapshots to process).")
    else:
        print(f"Ingested {n} records from downloaded snapshots.")
