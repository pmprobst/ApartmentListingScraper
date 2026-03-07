"""
CLI: Run Claude extraction for new listings only (within price range).

Usage:
    python scripts/extract_new.py
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

from uvrental.extraction_pipeline import run_initiate_phase, run_process_until_empty  # noqa: E402
from uvrental.config import get_db_path  # noqa: E402


if __name__ == "__main__":
    db_path = get_db_path()
    regex_count = run_initiate_phase(db_path)
    print(f"Ran regex extraction on {regex_count} listings.")
    llm_processed = run_process_until_empty(db_path)
    print(f"Processed {llm_processed} listings with Claude extraction.")
