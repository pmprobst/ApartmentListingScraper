"""
CLI entrypoint: run the ingestion + build pipeline.

Usage:
    python scripts/run_pipeline.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ensure project root (parent of scripts/) is on sys.path for `uvrental` imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uvrental.pipeline import run_pipeline  # noqa: E402


if __name__ == "__main__":
    run_pipeline()

