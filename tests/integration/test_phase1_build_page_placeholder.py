"""
Phase 1 integration tests: build_page.py generates static HTML from listings and run_status.
"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from uvrental.db import get_connection, get_run_status
from uvrental.ingest import run_fetch_dry_run, MOCK_RECORDS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

# Import after path is set
from uvrental import build_page as build_page_module


def test_build_page_generates_html_with_listings_and_run_status(tmp_path, env_vars):
    """
    Run fetch (dry-run) to populate DB and run_status, then build_page.
    Assert index.html exists and contains run status and listing content.
    """
    db_path = tmp_path / "listings.db"
    output_dir = tmp_path / "out"
    os.environ["LISTINGS_DB"] = str(db_path)
    os.environ["BUILD_PAGE_OUTPUT"] = str(output_dir)
    try:
        run_fetch_dry_run(str(db_path))
        build_page_module.build_page()
    finally:
        if "LISTINGS_DB" in os.environ and str(db_path) == os.environ["LISTINGS_DB"]:
            del os.environ["LISTINGS_DB"]
        if "BUILD_PAGE_OUTPUT" in os.environ:
            del os.environ["BUILD_PAGE_OUTPUT"]

    index_html = output_dir / "index.html"
    assert index_html.exists(), "build_page should write index.html"
    content = index_html.read_text(encoding="utf-8")

    assert "Run status" in content
    assert "Last run" in content or "No run recorded" in content
    assert "Scraped:" in content or "run status" in content.lower()
    # At least one mock listing title should appear
    assert any(m["title"] in content for m in MOCK_RECORDS)

    conn = get_connection(str(db_path))
    try:
        run = get_run_status(conn)
        assert run is not None
        assert run["displayed"] == len(MOCK_RECORDS), "displayed should match in-range listing count"
    finally:
        conn.close()


def test_build_page_updates_displayed_count(tmp_path, env_vars):
    """build_page updates run_status.displayed to the number of listings rendered."""
    db_path = tmp_path / "listings.db"
    output_dir = tmp_path / "out2"
    os.environ["LISTINGS_DB"] = str(db_path)
    os.environ["BUILD_PAGE_OUTPUT"] = str(output_dir)
    try:
        run_fetch_dry_run(str(db_path))
        build_page_module.build_page()
        conn = get_connection(str(db_path))
        run = get_run_status(conn)
        conn.close()
        assert run is not None
        assert run["displayed"] == len(MOCK_RECORDS)
    finally:
        for key in ("LISTINGS_DB", "BUILD_PAGE_OUTPUT"):
            if key in os.environ:
                del os.environ[key]


def test_build_page_excludes_listings_older_than_30_days(tmp_path, env_vars):
    """
    Seed DB with two listings; set one's last_seen to 40 days ago.
    build_page must exclude the old listing from index.html (30-day window).
    """
    db_path = tmp_path / "listings.db"
    output_dir = tmp_path / "out_30day"
    os.environ["LISTINGS_DB"] = str(db_path)
    os.environ["BUILD_PAGE_OUTPUT"] = str(output_dir)
    try:
        run_fetch_dry_run(str(db_path))
        conn = get_connection(str(db_path))
        try:
            rows = conn.execute(
                "SELECT id, title FROM listings ORDER BY id"
            ).fetchall()
            assert len(rows) >= 2, "need at least 2 mock listings"
            # Set the first listing's last_seen to 40 days ago (UTC)
            old_cutoff = (datetime.now(timezone.utc) - timedelta(days=40)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            conn.execute(
                "UPDATE listings SET last_seen = ? WHERE id = ?",
                (old_cutoff, rows[0]["id"]),
            )
            conn.commit()
            old_title = rows[0]["title"]
            recent_title = rows[1]["title"]
        finally:
            conn.close()

        build_page_module.build_page()

        content = (output_dir / "index.html").read_text(encoding="utf-8")
        assert old_title not in content, "listing with last_seen 40 days ago must be excluded"
        assert recent_title in content, "recent listing must appear on page"

        conn = get_connection(str(db_path))
        try:
            run = get_run_status(conn)
            assert run is not None
            assert run["displayed"] == 1, "only the recent listing should be displayed"
        finally:
            conn.close()
    finally:
        for key in ("LISTINGS_DB", "BUILD_PAGE_OUTPUT"):
            if key in os.environ:
                del os.environ[key]


def test_build_page_does_not_filter_by_location(tmp_path, env_vars):
    """
    build_page no longer deletes or filters listings based on location;
    both Utah and non-Utah listings should remain in the DB and appear
    on the rendered page (subject only to date/price filters).
    """
    db_path = tmp_path / "listings.db"
    output_dir = tmp_path / "out_non_utah"
    os.environ["LISTINGS_DB"] = str(db_path)
    os.environ["BUILD_PAGE_OUTPUT"] = str(output_dir)
    try:
        run_fetch_dry_run(str(db_path))
        conn = get_connection(str(db_path))
        try:
            rows = conn.execute(
                "SELECT id, title FROM listings ORDER BY id"
            ).fetchall()
            assert len(rows) >= 2, "need at least 2 mock listings"
            # Mark first as clearly non-Utah; second as clearly Utah
            conn.execute(
                "UPDATE listings SET address_raw = ?, title = ? WHERE id = ?",
                ("Boise, ID", "Non-Utah listing", rows[0]["id"]),
            )
            conn.execute(
                "UPDATE listings SET address_raw = ?, title = ? WHERE id = ?",
                ("Provo, UT", "Utah listing", rows[1]["id"]),
            )
            conn.commit()
        finally:
            conn.close()

        build_page_module.build_page()

        content = (output_dir / "index.html").read_text(encoding="utf-8")
        assert "Non-Utah listing" in content
        assert "Utah listing" in content

        conn = get_connection(str(db_path))
        try:
            # Both rows should remain in the DB regardless of location.
            rows = conn.execute(
                "SELECT title FROM listings ORDER BY id"
            ).fetchall()
            titles = {r["title"] for r in rows}
            assert "Non-Utah listing" in titles
            assert "Utah listing" in titles
        finally:
            conn.close()
    finally:
        for key in ("LISTINGS_DB", "BUILD_PAGE_OUTPUT"):
            if key in os.environ:
                del os.environ[key]

