"""
SQLite schema and deduplication for Utah Valley Rental Skimmer.
Phase 0: listings table, address normalization, upsert by (source, source_listing_id).
See plan/reference.md for schema and plan/phase-0.md for steps.
"""

import json
import re
import sqlite3
from datetime import datetime, timezone

# Default street suffix mappings (lowercase key -> normalized form)
SUFFIX_MAP = {
    "st": "street",
    "street": "street",
    "ave": "avenue",
    "avenue": "avenue",
    "av": "avenue",
    "blvd": "boulevard",
    "boulevard": "boulevard",
    "dr": "drive",
    "drive": "drive",
    "ln": "lane",
    "lane": "lane",
    "rd": "road",
    "road": "road",
    "ct": "court",
    "court": "court",
    "pl": "place",
    "place": "place",
    "cir": "circle",
    "circle": "circle",
    "trl": "trail",
    "trail": "trail",
    "pkwy": "parkway",
    "parkway": "parkway",
    "hwy": "highway",
    "highway": "highway",
}


def normalize_address(raw: str | None) -> str:
    """
    Normalize an address for deduplication: lowercase, strip punctuation,
    collapse whitespace, normalize street suffixes (St -> street, Ave -> avenue, etc.).
    Returns empty string if raw is None or blank.
    """
    if not raw or not isinstance(raw, str):
        return ""
    s = raw.strip().lower()
    s = re.sub(r"[^\w\s]", "", s)  # remove punctuation
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    parts = s.split()
    out = []
    for i, part in enumerate(parts):
        # Last token might be a suffix (e.g. "123 main st")
        normalized = SUFFIX_MAP.get(part, part)
        out.append(normalized)
    return " ".join(out)


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open or create SQLite DB and ensure schema exists. Caller should close."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create listings table if it does not exist. Idempotent."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_listing_id TEXT NOT NULL,
            normalized_address TEXT,
            address_raw TEXT,
            link TEXT NOT NULL,
            title TEXT,
            price REAL,
            beds REAL,
            baths REAL,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            extracted TEXT,
            canonical_listing_id INTEGER,
            UNIQUE(source, source_listing_id)
        )
    """)
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_listing(
    conn: sqlite3.Connection,
    *,
    source: str,
    source_listing_id: str,
    link: str,
    address_raw: str | None = None,
    normalized_address: str | None = None,
    title: str | None = None,
    price: float | None = None,
    beds: float | None = None,
    baths: float | None = None,
    extracted: str | dict | list | None = None,
) -> None:
    """
    Insert or update one listing by (source, source_listing_id).
    Sets first_seen on insert, last_seen on every update.
    normalized_address is computed from address_raw if not provided.
    """
    now = _now_iso()
    if normalized_address is None and address_raw:
        normalized_address = normalize_address(address_raw)
    elif normalized_address is None:
        normalized_address = ""

    # Ensure extracted is stored as a JSON string when structured data is provided
    if extracted is None:
        extracted_json = None
    elif isinstance(extracted, str):
        extracted_json = extracted
    else:
        try:
            extracted_json = json.dumps(extracted, ensure_ascii=False, sort_keys=True)
        except TypeError:
            # Fallback: store string representation if value is not JSON-serializable
            extracted_json = str(extracted)

    conn.execute("""
        INSERT INTO listings (
            source, source_listing_id, normalized_address, address_raw, link, title,
            price, beds, baths, first_seen, last_seen, extracted, canonical_listing_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(source, source_listing_id) DO UPDATE SET
            normalized_address = excluded.normalized_address,
            address_raw = excluded.address_raw,
            link = excluded.link,
            title = excluded.title,
            price = excluded.price,
            beds = excluded.beds,
            baths = excluded.baths,
            last_seen = excluded.last_seen,
            extracted = COALESCE(excluded.extracted, listings.extracted)
    """, (
        source,
        source_listing_id,
        normalized_address or None,
        address_raw or None,
        link,
        title,
        price,
        beds,
        baths,
        now,
        now,
        extracted_json,
    ))
    # first_seen is only set on INSERT; DO UPDATE leaves it unchanged
    conn.commit()
