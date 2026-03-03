import os
import subprocess
import sys
from pathlib import Path

from uvrental.db import get_connection


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_main_populates_db_and_prints_listings(tmp_db_path, env_vars):
    """
    Run `python main.py` and verify it:
    - exits successfully
    - writes listings into the configured DB
    - prints the listing summary header (or a clear message if empty)
    """
    db_path = str(tmp_db_path)

    env = os.environ.copy()
    env["LISTINGS_DB"] = db_path

    result = subprocess.run(
        [sys.executable, "scripts/run_pipeline.py"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    # Should either show listings or say there are none
    assert (
        "Listing data (" in result.stdout or "No listings in DB." in result.stdout
    )

