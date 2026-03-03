from uvrental.ingest import (
    MARKETPLACE_ITEM_BASE,
    _address_raw,
    _norm_num,
    _norm_price,
    _numeric_listing_id,
    _source_listing_id,
    normalize_record,
)


def test_source_listing_id_prefers_known_id_fields():
    rec = {"product_id": "12345", "listing_id": "ignored", "id": "ignored"}
    assert _source_listing_id(rec) == "12345"

    rec2 = {"listing_id": 987, "id": "also_ignored"}
    assert _source_listing_id(rec2) == "987"


def test_source_listing_id_falls_back_to_link_hash_and_is_stable():
    rec = {"title": "Some listing", "link": "https://example.com/one"}
    sid1 = _source_listing_id(rec)
    sid2 = _source_listing_id(rec)
    assert isinstance(sid1, str)
    assert len(sid1) == 32  # truncated SHA-256 hex
    assert sid1 == sid2

    rec_other = {"title": "Some listing", "link": "https://example.com/two"}
    sid_other = _source_listing_id(rec_other)
    assert sid_other != sid1


def test_numeric_listing_id_from_fields_and_url():
    rec = {"product_id": "111222333444555"}
    assert _numeric_listing_id(rec) == "111222333444555"

    rec2 = {
        "url": "https://www.facebook.com/marketplace/item/999888777666555/",
    }
    assert _numeric_listing_id(rec2) == "999888777666555"

    rec3 = {"link": "https://example.com/no-id-here"}
    assert _numeric_listing_id(rec3) is None


def test_norm_price_handles_various_formats():
    assert _norm_price(None) is None
    assert _norm_price(1000) == 1000.0
    assert _norm_price(1000.5) == 1000.5
    assert _norm_price("$1,234") == 1234.0
    assert _norm_price("  ") is None
    assert _norm_price("not a number") is None


def test_norm_num_handles_numbers_and_strings():
    assert _norm_num(None) is None
    assert _norm_num(3) == 3.0
    assert _norm_num(2.5) == 2.5
    assert _norm_num(" 4 ") == 4.0
    assert _norm_num("abc") is None


def test_address_raw_from_location_variants():
    rec_str = {"location": "Provo, UT"}
    assert _address_raw(rec_str) == "Provo, UT"

    rec_dict = {"location": {"city": "Provo", "state": "UT"}}
    assert _address_raw(rec_dict) == "Provo, UT"

    rec_fallback = {"city": "Orem", "address_raw": "Orem, UT"}
    # address_raw key wins before city
    assert _address_raw(rec_fallback) == "Orem, UT"


def test_normalize_record_builds_canonical_marketplace_url():
    rec = {
        "product_id": "1000000000000001",
        "title": "2BR Apartment Near UVU",
        "price": "$1,100",
        "location": "Orem, UT",
        "bedrooms": 2,
        "bathrooms": 1,
    }
    norm = normalize_record(rec)
    assert norm["source_listing_id"] == "1000000000000001"
    assert norm["link"] == f"{MARKETPLACE_ITEM_BASE}/1000000000000001/"
    assert norm["title"] == "2BR Apartment Near UVU"
    assert norm["price"] == 1100.0
    assert norm["beds"] == 2.0
    assert norm["baths"] == 1.0
    assert norm["address_raw"] == "Orem, UT"


def test_normalize_record_uses_fallback_title_and_url():
    rec = {
        "product_id": "2000000000000002",
        "name": "Listing name field",
        "listing_url": "/marketplace/item/2000000000000002/",
        "initial_price": "950",
    }
    norm = normalize_record(rec)
    # When a numeric ID is present, canonical URL wins
    assert norm["link"] == f"{MARKETPLACE_ITEM_BASE}/2000000000000002/"
    assert norm["title"] == "Listing name field"
    assert norm["price"] == 950.0

