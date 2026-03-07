"""
CLI: Generate static HTML from SQLite listings and run_status.

Usage:
    python scripts/build_page.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ensure project root (parent of scripts/) is on sys.path for `uvrental` imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uvrental.build_page import build_page  # noqa: E402


if __name__ == "__main__":
    build_page()
    print("Built HTML.")
