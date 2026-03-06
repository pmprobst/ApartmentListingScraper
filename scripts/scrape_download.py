"""
CLI: Check a Bright Data snapshot status and download when ready.

Usage:
    python scripts/scrape_download.py
    python scripts/scrape_download.py <snapshot_id>
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

from uvrental.brightdata_download import (  # noqa: E402
    SnapshotNotReadyError,
    run_from_env,
)


if __name__ == "__main__":
    snapshot_id_arg = sys.argv[1] if len(sys.argv) == 2 else None
    try:
        run_from_env(snapshot_id_arg)
    except SnapshotNotReadyError:
        sys.exit(0)
    except (ValueError, FileNotFoundError, RuntimeError, Exception) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

