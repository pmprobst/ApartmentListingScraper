import os
import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure project root is importable (for uvrental, etc.)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uvrental.db import get_connection


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """
    Temporary SQLite DB path for tests.
    The file is created lazily by get_connection/init_schema.
    """
    return tmp_path / "test_listings.db"


@pytest.fixture
def tmp_db_conn(tmp_db_path: Path):
    """
    Convenience fixture that returns an open SQLite connection
    with the listings schema initialized. Closes after use.
    """
    # Reuse project helper to ensure identical schema
    conn = get_connection(str(tmp_db_path))
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def env_vars(monkeypatch, tmp_db_path: Path):
    """
    Set minimal env vars used by the app for tests.
    Ensures we never accidentally read/write the real DB.
    """
    monkeypatch.setenv("LISTINGS_DB", str(tmp_db_path))
    # Safe dummy keys; tests that need real API behavior should mock requests.
    monkeypatch.setenv("BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY", "test-key")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "test-key")
    yield
