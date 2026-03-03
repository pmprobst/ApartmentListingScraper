from datetime import datetime, timezone

import sqlite3

from db import (
    get_connection,
    init_schema,
    normalize_address,
    upsert_listing,
    update_run_status_after_build_page,
    update_run_status_after_fetch,
    update_run_status_after_llm,
    get_run_status,
)


def test_init_schema_creates_listings_table(tmp_path):
    db_path = tmp_path / "schema_test.db"
    conn = get_connection(str(db_path))
    try:
        cur = conn.execute(
            "PRAGMA table_info(listings)"
        )
        cols = {row[1] for row in cur.fetchall()}
        # Core columns from reference.md
        expected = {
            "id",
            "source",
            "source_listing_id",
            "normalized_address",
            "address_raw",
            "link",
            "title",
            "price",
            "beds",
            "baths",
            "first_seen",
            "last_seen",
            "extracted",
            "canonical_listing_id",
        }
        assert expected.issubset(cols)

        # UNIQUE(source, source_listing_id) exists
        cur = conn.execute("PRAGMA index_list(listings)")
        index_info = cur.fetchall()
        index_names = [row[1] for row in index_info]
        # There will be an auto-created unique index for the UNIQUE constraint
        assert any("source_listing_id" in name or "listings" in name for name in index_names)
    finally:
        conn.close()


def test_normalize_address_basic_cases():
    # Lowercasing, punctuation removal, whitespace collapse
    assert normalize_address(" 123 Main St. ") == "123 main street"
    assert normalize_address("456  NORTH  AVE, Provo, UT") == "456 north avenue provo ut"
    # Unknown suffix unchanged
    assert normalize_address("789 Canyon View Plz") == "789 canyon view plz"
    # None / empty -> empty string
    assert normalize_address(None) == ""
    assert normalize_address("   ") == ""


def _fetch_single_listing(conn: sqlite3.Connection):
    cur = conn.execute(
        "SELECT source, source_listing_id, normalized_address, address_raw, link, "
        "title, price, beds, baths, first_seen, last_seen, extracted "
        "FROM listings"
    )
    return cur.fetchone()


def _fetch_listing_ids(conn: sqlite3.Connection):
    """Fetch id and canonical_listing_id for all listings (for cross-source tests)."""
    cur = conn.execute("SELECT id, source, canonical_listing_id FROM listings ORDER BY id")
    return cur.fetchall()


def test_upsert_listing_inserts_and_updates(tmp_path):
    db_path = tmp_path / "upsert_test.db"
    conn = get_connection(str(db_path))
    try:
        # First insert
        upsert_listing(
            conn,
            source="facebook_marketplace",
            source_listing_id="abc123",
            link="https://example.com/abc123",
            address_raw="123 Main St, Provo UT",
            title="Nice apartment",
            price=1000.0,
            beds=2,
            baths=1,
        )
        row1 = _fetch_single_listing(conn)
        assert row1 is not None
        first_seen_1 = row1["first_seen"]
        last_seen_1 = row1["last_seen"]
        assert first_seen_1 == last_seen_1
        assert row1["normalized_address"] == normalize_address("123 Main St, Provo UT")

        # Second upsert with changed fields; first_seen should be preserved, last_seen updated
        upsert_listing(
            conn,
            source="facebook_marketplace",
            source_listing_id="abc123",
            link="https://example.com/abc123",
            address_raw="123 Main Street, Provo UT",
            title="Updated apartment",
            price=1100.0,
            beds=3,
            baths=2,
        )
        row2 = _fetch_single_listing(conn)
        assert row2 is not None
        assert row2["first_seen"] == first_seen_1
        assert row2["last_seen"] >= last_seen_1
        assert row2["title"] == "Updated apartment"
        assert row2["price"] == 1100.0
        assert row2["beds"] == 3
        assert row2["baths"] == 2

    finally:
        conn.close()


def test_upsert_listing_coalesces_extracted(tmp_path):
    db_path = tmp_path / "upsert_extracted.db"
    conn = get_connection(str(db_path))
    try:
        upsert_listing(
            conn,
            source="facebook_marketplace",
            source_listing_id="xyz789",
            link="https://example.com/xyz789",
            address_raw="1 Test St, Orem UT",
            title="Listing",
            extracted='{"foo": "bar"}',
        )
        row1 = _fetch_single_listing(conn)
        assert row1["extracted"] == '{"foo": "bar"}'

        # Second upsert with extracted=None should preserve previous extracted value
        upsert_listing(
            conn,
            source="facebook_marketplace",
            source_listing_id="xyz789",
            link="https://example.com/xyz789",
            address_raw="1 Test St, Orem UT",
            title="Listing updated",
            extracted=None,
        )
        row2 = _fetch_single_listing(conn)
        assert row2["extracted"] == '{"foo": "bar"}'
    finally:
        conn.close()


def test_run_status_helpers_insert_and_update(tmp_path):
    db_path = tmp_path / "run_status.db"
    conn = get_connection(str(db_path))
    try:
        # After fetch
        update_run_status_after_fetch(
            conn,
            success=True,
            scraped=10,
            thrown=2,
            duplicate=3,
            added=5,
            total_count=8,
        )
        row1 = get_run_status(conn)
        assert row1 is not None
        assert row1["success"] == 1
        assert row1["scraped"] == 10
        assert row1["thrown"] == 2
        assert row1["duplicate"] == 3
        assert row1["added"] == 5
        assert row1["total_count"] == 8
        assert row1["new_count"] == 5
        assert row1["updated_count"] == 3
        assert row1["llm_processed"] == 0
        assert row1["displayed"] == 0
        assert isinstance(row1["last_run_ts"], str) and row1["last_run_ts"].endswith("Z")

        # After LLM processing
        update_run_status_after_llm(conn, llm_processed=7)
        row2 = get_run_status(conn)
        assert row2["llm_processed"] == 7
        # Fetch-derived counts unchanged
        assert row2["scraped"] == 10
        assert row2["added"] == 5

        # After build_page
        update_run_status_after_build_page(conn, displayed=4)
        row3 = get_run_status(conn)
        assert row3["displayed"] == 4
        # Still single row
        cur = conn.execute("SELECT COUNT(*) FROM run_status")
        assert cur.fetchone()[0] == 1
    finally:
        conn.close()


def test_upsert_listing_sets_canonical_listing_id_when_same_address_different_source(tmp_path):
    """Cross-source dedup: same normalized_address, different source -> link via canonical_listing_id."""
    db_path = tmp_path / "cross_source.db"
    conn = get_connection(str(db_path))
    try:
        # First listing (Facebook) - same address will normalize to "123 main street provo ut"
        upsert_listing(
            conn,
            source="facebook_marketplace",
            source_listing_id="fb1",
            link="https://facebook.com/marketplace/item/1",
            address_raw="123 Main St, Provo UT",
            title="Apartment",
        )
        rows = _fetch_listing_ids(conn)
        assert len(rows) == 1
        fb_id = rows[0]["id"]
        assert rows[0]["canonical_listing_id"] is None

        # Second listing (Zillow) - same normalized address, different source
        upsert_listing(
            conn,
            source="zillow",
            source_listing_id="z1",
            link="https://zillow.com/listing/1",
            address_raw="123 Main Street, Provo UT",
            title="Same place on Zillow",
        )
        rows = _fetch_listing_ids(conn)
        assert len(rows) == 2
        # Facebook row still has no canonical (it was first). Zillow row should point to Facebook's id.
        by_source = {r["source"]: r for r in rows}
        assert by_source["facebook_marketplace"]["canonical_listing_id"] is None
        assert by_source["zillow"]["canonical_listing_id"] == fb_id
    finally:
        conn.close()

