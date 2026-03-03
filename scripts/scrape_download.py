"""
CLI: Check a Bright Data snapshot status and download when ready.

Usage:
    python scripts/scrape_download.py
    python scripts/scrape_download.py <snapshot_id>
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ensure project root (parent of scripts/) is on sys.path for `uvrental` imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uvrental.brightdata_download import run_from_env  # noqa: E402


if __name__ == "__main__":
    snapshot_id_arg = sys.argv[1] if len(sys.argv) == 2 else None
    run_from_env(snapshot_id_arg)

