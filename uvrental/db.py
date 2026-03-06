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
    for part in parts:
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
    """Create core tables if they do not exist and ensure schema is up to date."""
    conn.execute(
        """
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
            washer_dryer TEXT,
            renter_paid_fees TEXT,
            availability TEXT,
            pet_policy TEXT,
            roommates TEXT,
            listing_date TEXT,
            description TEXT,
            in_unit_washer_dryer INTEGER,
            has_roommates INTEGER,
            gender_preference TEXT,
            utilities_included TEXT,
            non_included_utilities_cost TEXT,
            lease_length TEXT,
            llm_extraction_status TEXT,
            canonical_listing_id INTEGER,
            UNIQUE(source, source_listing_id)
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_status (
            id INTEGER PRIMARY KEY,
            last_run_ts TEXT NOT NULL,
            success INTEGER NOT NULL,
            scraped INTEGER NOT NULL,
            thrown INTEGER NOT NULL,
            duplicate INTEGER NOT NULL,
            added INTEGER NOT NULL,
            total_count INTEGER NOT NULL,
            new_count INTEGER NOT NULL,
            updated_count INTEGER NOT NULL,
            llm_processed INTEGER NOT NULL,
            displayed INTEGER NOT NULL
        )
    """
    )

    # Backfill newly added LLM-derived columns on existing databases.
    cur = conn.execute("PRAGMA table_info(listings)")
    existing_cols = {row[1] for row in cur.fetchall()}
    llm_columns = {
        "washer_dryer": "TEXT",
        "renter_paid_fees": "TEXT",
        "availability": "TEXT",
        "pet_policy": "TEXT",
        "roommates": "TEXT",
    }
    for col_name, col_type in llm_columns.items():
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {col_name} {col_type}")

    if "listing_date" not in existing_cols:
        conn.execute("ALTER TABLE listings ADD COLUMN listing_date TEXT")
    for col, ctype in [
        ("description", "TEXT"),
        ("in_unit_washer_dryer", "INTEGER"),
        ("has_roommates", "INTEGER"),
        ("gender_preference", "TEXT"),
        ("utilities_included", "TEXT"),
        ("non_included_utilities_cost", "TEXT"),
        ("lease_length", "TEXT"),
        ("llm_extraction_status", "TEXT"),
    ]:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {ctype}")

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
    listing_date: str | None = None,
    description: str | None = None,
) -> None:
    """
    Insert or update one listing by (source, source_listing_id).
    Sets first_seen on insert, last_seen on every update.
    normalized_address is computed from address_raw if not provided.
    When normalized_address is non-empty, if another row exists with the same
    normalized_address and a different source, this row's canonical_listing_id
    is set to that row's id (cross-source deduplication).
    """
    now = _now_iso()
    if normalized_address is None and address_raw:
        normalized_address = normalize_address(address_raw)
    elif normalized_address is None:
        normalized_address = ""

    conn.execute(
        """
        INSERT INTO listings (
            source, source_listing_id, normalized_address, address_raw, link, title,
            price, beds, baths, first_seen, last_seen, listing_date, description, canonical_listing_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(source, source_listing_id) DO UPDATE SET
            normalized_address = excluded.normalized_address,
            address_raw = excluded.address_raw,
            link = excluded.link,
            title = excluded.title,
            price = excluded.price,
            beds = excluded.beds,
            baths = excluded.baths,
            last_seen = excluded.last_seen,
            listing_date = COALESCE(excluded.listing_date, listings.listing_date),
            description = COALESCE(excluded.description, listings.description)
    """,
        (
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
            listing_date,
            description,
        ),
    )

    norm = (normalized_address or "").strip()
    if norm:
        row = conn.execute(
            "SELECT id FROM listings WHERE source = ? AND source_listing_id = ?",
            (source, source_listing_id),
        ).fetchone()
        if row:
            our_id = row[0]
            other = conn.execute(
                """
                SELECT id FROM listings
                WHERE normalized_address = ?
                  AND source != ?
                  AND normalized_address IS NOT NULL
                  AND normalized_address != ''
                ORDER BY id LIMIT 1
                """,
                (norm, source),
            ).fetchone()
            if other:
                conn.execute(
                    "UPDATE listings SET canonical_listing_id = ? WHERE id = ?",
                    (other[0], our_id),
                )
    conn.commit()


def update_listing_extraction(
    conn: sqlite3.Connection,
    listing_id: int,
    *,
    beds: float | None = None,
    baths: float | None = None,
    in_unit_washer_dryer: int | None = None,
    has_roommates: int | None = None,
    gender_preference: str | None = None,
    utilities_included: str | None = None,
    non_included_utilities_cost: str | None = None,
    lease_length: str | None = None,
    llm_extraction_status: str | None = None,
) -> None:
    """Update extraction fields and/or llm_extraction_status for one listing."""
    updates = []
    params: list[object] = []
    if beds is not None:
        updates.append("beds = ?")
        params.append(beds)
    if baths is not None:
        updates.append("baths = ?")
        params.append(baths)
    if in_unit_washer_dryer is not None:
        updates.append("in_unit_washer_dryer = ?")
        params.append(in_unit_washer_dryer)
    if has_roommates is not None:
        updates.append("has_roommates = ?")
        params.append(has_roommates)
    if gender_preference is not None:
        updates.append("gender_preference = ?")
        params.append(gender_preference)
    if utilities_included is not None:
        updates.append("utilities_included = ?")
        params.append(utilities_included)
    if non_included_utilities_cost is not None:
        updates.append("non_included_utilities_cost = ?")
        params.append(non_included_utilities_cost)
    if lease_length is not None:
        updates.append("lease_length = ?")
        params.append(lease_length)
    if llm_extraction_status is not None:
        updates.append("llm_extraction_status = ?")
        params.append(llm_extraction_status)
    if not updates:
        return
    params.append(listing_id)
    conn.execute(
        f"UPDATE listings SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()


def update_run_status_after_fetch(
    conn: sqlite3.Connection,
    *,
    success: bool,
    scraped: int,
    thrown: int,
    duplicate: int,
    added: int,
    total_count: int,
) -> None:
    """
    Update run_status after fetch has completed.
    """
    now = _now_iso()
    row = conn.execute(
        "SELECT id, llm_processed, displayed FROM run_status WHERE id = 1"
    ).fetchone()
    llm_processed = int(row["llm_processed"]) if row is not None else 0
    displayed = int(row["displayed"]) if row is not None else 0

    new_count = int(added)
    updated_count = int(duplicate)
    if row is None:
        conn.execute(
            """
            INSERT INTO run_status (
                id, last_run_ts, success,
                scraped, thrown, duplicate, added,
                total_count, new_count, updated_count,
                llm_processed, displayed
            ) VALUES (
                1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                now,
                1 if success else 0,
                int(scraped),
                int(thrown),
                int(duplicate),
                int(added),
                int(total_count),
                new_count,
                updated_count,
                llm_processed,
                displayed,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE run_status
            SET
                last_run_ts = ?,
                success = ?,
                scraped = ?,
                thrown = ?,
                duplicate = ?,
                added = ?,
                total_count = ?,
                new_count = ?,
                updated_count = ?
            WHERE id = 1
            """,
            (
                now,
                1 if success else 0,
                int(scraped),
                int(thrown),
                int(duplicate),
                int(added),
                int(total_count),
                new_count,
                updated_count,
            ),
        )
    conn.commit()


def update_run_status_after_llm(
    conn: sqlite3.Connection,
    *,
    llm_processed: int,
) -> None:
    """
    Update run_status after the Claude/LLM extraction step.
    """
    now = _now_iso()
    row = conn.execute("SELECT id FROM run_status WHERE id = 1").fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO run_status (
                id, last_run_ts, success,
                scraped, thrown, duplicate, added,
                total_count, new_count, updated_count,
                llm_processed, displayed
            ) VALUES (
                1, ?, 0, 0, 0, 0, 0, 0, 0, 0, ?, 0
            )
            """,
            (now, int(llm_processed)),
        )
    else:
        conn.execute(
            """
            UPDATE run_status
            SET last_run_ts = ?, llm_processed = ?
            WHERE id = 1
            """,
            (now, int(llm_processed)),
        )
    conn.commit()


def update_run_status_after_build_page(
    conn: sqlite3.Connection,
    *,
    displayed: int,
) -> None:
    """
    Update run_status after build_page has rendered the HTML.
    """
    now = _now_iso()
    row = conn.execute("SELECT id FROM run_status WHERE id = 1").fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO run_status (
                id, last_run_ts, success,
                scraped, thrown, duplicate, added,
                total_count, new_count, updated_count,
                llm_processed, displayed
            ) VALUES (
                1, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?
            )
            """,
            (now, int(displayed)),
        )
    else:
        conn.execute(
            """
            UPDATE run_status
            SET last_run_ts = ?, displayed = ?
            WHERE id = 1
            """,
            (now, int(displayed)),
        )
    conn.commit()


def get_run_status(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """
    Return the single run_status row (or None if no runs recorded yet).
    """
    return conn.execute("SELECT * FROM run_status WHERE id = 1").fetchone()

