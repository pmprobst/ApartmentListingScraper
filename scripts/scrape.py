"""
CLI: Trigger a Bright Data Facebook Marketplace snapshot and record snapshot_id.

Usage:
    python scripts/scrape.py
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

from uvrental.brightdata import trigger_from_env  # noqa: E402


if __name__ == "__main__":
    try:
        trigger_from_env()
    except (ValueError, Exception) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

