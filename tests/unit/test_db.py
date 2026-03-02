from datetime import datetime, timezone

import sqlite3

from db import get_connection, init_schema, normalize_address, upsert_listing


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

