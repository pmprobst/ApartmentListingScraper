"""
CLI: Trigger a Bright Data Facebook Marketplace snapshot and record snapshot_id.

Usage:
    python scripts/scrape.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ensure project root (parent of scripts/) is on sys.path for `uvrental` imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uvrental.brightdata import trigger_from_env  # noqa: E402


if __name__ == "__main__":
    trigger_from_env()

