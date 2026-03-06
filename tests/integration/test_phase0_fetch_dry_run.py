from uvrental.db import get_connection
from uvrental.ingest import MOCK_RECORDS, run_fetch_dry_run


def test_run_fetch_dry_run_inserts_mock_listings(tmp_db_path):
    db_path = str(tmp_db_path)

    inserted = run_fetch_dry_run(db_path)
    # Should report inserting all mock records
    assert inserted == len(MOCK_RECORDS)

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT source, source_listing_id, link, first_seen, last_seen "
            "FROM listings"
        ).fetchall()
        # At least the mock records should be present
        assert len(rows) == len(MOCK_RECORDS)

        # No duplicate (source, source_listing_id)
        pairs = {(r["source"], r["source_listing_id"]) for r in rows}
        assert len(pairs) == len(rows)

        # Timestamps populated
        for r in rows:
            assert r["first_seen"]
            assert r["last_seen"]

        # Links use canonical Marketplace item format
        for r in rows:
            assert r["link"].startswith("https://www.facebook.com/marketplace/item/")
    finally:
        conn.close()

