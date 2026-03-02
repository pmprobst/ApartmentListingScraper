import os
import subprocess
import sys
from pathlib import Path

from db import get_connection


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_main_dry_run_populates_db_and_prints_listings(tmp_db_path, env_vars):
    """
    Run `python main.py --dry-run` and verify it:
    - exits successfully
    - writes listings into the configured DB
    - prints the listing summary header
    """
    db_path = str(tmp_db_path)

    env = os.environ.copy()
    env["LISTINGS_DB"] = db_path

    result = subprocess.run(
        [sys.executable, "main.py", "--dry-run"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    # Should print the summary header from main.print_listings
    assert "Listing data (" in result.stdout

    # DB should contain at least the mock listings
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, source, source_listing_id, link FROM listings"
        ).fetchall()
        assert len(rows) >= 1
    finally:
        conn.close()

