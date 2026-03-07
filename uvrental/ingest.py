"""
Snapshot ingestion and normalization utilities.

This module is responsible for taking JSON snapshots from Bright Data
(downloaded separately by scrape scripts), normalizing records, and
upserting them into the SQLite DB while updating run_status.
"""

import hashlib
import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from .config import get_db_path, get_snapshot_history_path, get_snapshots_dir
from .db import (
    get_connection,
    upsert_listing,
    update_run_status_after_fetch,
    update_run_status_run_start,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Snapshot history and snapshots dir (configurable via paths.data_dir or SNAPSHOT_DATA_DIR).
def _snapshot_history_path():
    return get_snapshot_history_path()


def _snapshots_dir():
    return get_snapshots_dir()


def _source_listing_id(record: dict) -> str:
    """Stable id for dedup: product_id, listing_id, id, or hash(link)."""
    for k in ("product_id", "listing_id", "id", "listingID"):
        if record.get(k) is not None:
            return str(record[k])
    link = record.get("link") or record.get("url") or record.get("listing_url") or ""
    if link:
        return hashlib.sha256(link.encode()).hexdigest()[:32]
    title = record.get("title") or ""
    return hashlib.sha256(title.encode()).hexdigest()[:32]


def _norm_price(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").replace("$", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _norm_num(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).strip())
    except ValueError:
        return None


def _address_raw(record: dict) -> str | None:
    """Single address string from location fields."""
    loc = record.get("location")
    if isinstance(loc, str) and loc.strip():
        return loc.strip()
    if isinstance(loc, dict):
        parts = [
            loc.get("city"),
            loc.get("state"),
            loc.get("address"),
            loc.get("street"),
            loc.get("region"),
        ]
        return ", ".join(p for p in parts if p) or None
    for k in ("address", "address_raw", "city", "location_name"):
        if record.get(k):
            return str(record[k]).strip()
    return None


MARKETPLACE_ITEM_BASE = "https://www.facebook.com/marketplace/item"


def _numeric_listing_id(record: dict) -> str | None:
    """Extract numeric listing/item ID for building canonical Marketplace URL."""
    for key in ("listing_id", "product_id", "item_id", "id"):
        val = record.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if s.isdigit():
            return s
        if s and s.replace("-", "").isdigit():
            return s
    raw = record.get("link") or record.get("url") or record.get("listing_url") or ""
    if not raw:
        return None
    m = re.search(r"/marketplace/item/(\d+)", raw)
    if m:
        return m.group(1)
    m = re.search(r"/item/(\d+)", raw)
    if m:
        return m.group(1)
    return None


def normalize_record(record: dict) -> dict:
    """Map Bright Data / Marketplace record to our listing fields."""
    numeric_id = _numeric_listing_id(record)
    if numeric_id:
        link = f"{MARKETPLACE_ITEM_BASE}/{numeric_id}/"
    else:
        link = (
            record.get("link")
            or record.get("url")
            or record.get("listing_url")
            or record.get("listing_link")
            or ""
        )
        if link and not link.startswith("http"):
            link = f"{MARKETPLACE_ITEM_BASE}/" + link.lstrip("/")
        link = link or "https://www.facebook.com/marketplace"
    listing_date = record.get("listing_date")
    if isinstance(listing_date, str) and listing_date.strip():
        listing_date = listing_date.strip()
    else:
        listing_date = None

    description = (
        str(record.get("seller_description") or record.get("description") or "")
    ).strip() or None

    return {
        "source_listing_id": _source_listing_id(record),
        "link": link,
        "title": (record.get("title") or record.get("name") or "").strip() or None,
        "price": _norm_price(
            record.get("price")
            or record.get("final_price")
            or record.get("initial_price")
            or record.get("listing_price")
        ),
        "beds": _norm_num(record.get("beds") or record.get("bedrooms") or record.get("bed")),
        "baths": _norm_num(record.get("baths") or record.get("bathrooms") or record.get("bath")),
        "address_raw": _address_raw(record),
        "listing_date": listing_date,
        "description": description,
    }


def _load_snapshot_payload(payload: object) -> list[dict]:
    """
    Normalize various Bright Data snapshot shapes into a flat list of records.
    """
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "listings", "items", "records"):
            val = payload.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
        return [payload]
    return []


def load_snapshot_file(path: str | Path) -> list[dict]:
    """
    Load a snapshot JSON file (saved by scrape scripts) and return records.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    records = _load_snapshot_payload(payload)
    log.info("Loaded %d records from %s", len(records), p.name)
    return records


def ingest_records(db_path: str, records: list[dict]) -> int:
    """
    Normalize and upsert records into SQLite, updating run_status.
    """
    if not records:
        log.warning("No records to ingest")
        return 0
    conn = get_connection(db_path)
    try:
        scraped = len(records)
        thrown = 0
        duplicate = 0
        added = 0
        processed = 0
        for rec in records:
            if not isinstance(rec, dict):
                thrown += 1
                continue
            if rec.get("error") is not None or rec.get("error_code") is not None:
                thrown += 1
                continue
            norm = normalize_record(rec)
            if not norm["link"] or norm["link"] == "https://www.facebook.com/marketplace":
                thrown += 1
                continue
            source_listing_id = norm["source_listing_id"]
            exists = conn.execute(
                "SELECT 1 FROM listings WHERE source = ? AND source_listing_id = ?",
                ("facebook_marketplace", source_listing_id),
            ).fetchone()
            if exists:
                duplicate += 1
            else:
                added += 1
            upsert_listing(
                conn,
                source="facebook_marketplace",
                source_listing_id=source_listing_id,
                link=norm["link"],
                title=norm.get("title"),
                price=norm.get("price"),
                beds=norm.get("beds"),
                baths=norm.get("baths"),
                address_raw=norm.get("address_raw"),
                listing_date=norm.get("listing_date"),
                description=norm.get("description"),
            )
            processed += 1
        total_count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        update_run_status_after_fetch(
            conn,
            success=True,
            scraped=scraped,
            thrown=thrown,
            duplicate=duplicate,
            added=added,
            total_count=total_count,
        )
        log.info(
            "Ingested %d records (scraped=%d, thrown=%d, duplicate=%d, added=%d, total=%d)",
            processed,
            scraped,
            thrown,
            duplicate,
            added,
            total_count,
        )
        return processed
    finally:
        conn.close()


def ingest_snapshot_file(db_path: str, snapshot_path: str | Path) -> int:
    """
    Load a snapshot JSON file and ingest its records into the DB.
    """
    records = load_snapshot_file(snapshot_path)
    return ingest_records(db_path, records)


def _append_history(snapshot_id: str, status: str) -> None:
    """Append a status update for a snapshot to snapshot_history.jsonl."""
    from datetime import datetime, timezone

    path = _snapshot_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "timestamp": ts,
        "snapshot_id": snapshot_id,
        "status": status,
        "updated_ts": ts,
    }
    with path.open("a", encoding="utf-8") as f:
        json.dump(record, f)
        f.write("\n")


def _update_run_status_zero_ingest(db_path: str) -> None:
    """Record last run when zero records were ingested (so last_run_ts is still updated)."""
    conn = get_connection(db_path)
    try:
        total_count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        update_run_status_after_fetch(
            conn,
            success=True,
            scraped=0,
            thrown=0,
            duplicate=0,
            added=0,
            total_count=total_count,
        )
    finally:
        conn.close()


def _latest_snapshot_states() -> dict[str, dict]:
    """
    Read snapshot_history.jsonl and return the latest record per snapshot_id.
    """
    states: dict[str, dict] = {}
    path = _snapshot_history_path()
    if not path.exists():
        return states
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = rec.get("snapshot_id")
            if not sid:
                continue
            states[sid] = rec
    return states


def ingest_all_downloaded_from_history(
    db_path: str | None = None, snapshot_id: str | None = None
) -> int:
    """
    Ingest snapshot JSON files into the DB based on snapshot history.
    """
    if db_path is None:
        db_path = get_db_path()

    # Phase 3: set run_start_ts at start so extraction can identify new listings
    conn = get_connection(db_path)
    try:
        update_run_status_run_start(conn)
    finally:
        conn.close()

    states = _latest_snapshot_states()
    if not states:
        log.info("No snapshot history entries found.")
        _update_run_status_zero_ingest(db_path)
        return 0

    if snapshot_id is not None:
        rec = states.get(snapshot_id)
        if not rec:
            log.warning("Snapshot id %s not found in history; nothing to ingest.", snapshot_id)
            _update_run_status_zero_ingest(db_path)
            return 0
        status = (rec.get("status") or "").lower()
        if status != "downloaded":
            log.info(
                "Snapshot %s has latest status '%s' (not 'downloaded'); nothing to ingest.",
                snapshot_id,
                status,
            )
            _update_run_status_zero_ingest(db_path)
            return 0
        snapshot_ids = [snapshot_id]
    else:
        snapshot_ids = [
            sid
            for sid, rec in states.items()
            if (rec.get("status") or "").lower() == "downloaded"
        ]

    total_ingested = 0
    snapshots_dir = _snapshots_dir()
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    for sid in snapshot_ids:
        snapshot_path = snapshots_dir / f"marketplace_snapshot_{sid}.json"
        if not snapshot_path.exists():
            log.warning(
                "Snapshot file %s for id %s not found; skipping.", snapshot_path, sid
            )
            continue
        log.info("Ingesting downloaded snapshot %s from %s", sid, snapshot_path)
        try:
            n = ingest_snapshot_file(db_path, snapshot_path)
            total_ingested += n
            _append_history(sid, "ingested")
        except Exception as e:
            log.exception("Failed to ingest snapshot %s: %s", sid, e)
            raise

    if total_ingested == 0:
        log.info("No downloaded snapshots needed ingestion.")
        _update_run_status_zero_ingest(db_path)
    else:
        log.info("Ingested a total of %d records from downloaded snapshots.", total_ingested)
    return total_ingested


MOCK_RECORDS = [
    {
        "product_id": "1000000000000001",
        "title": "2BR Apartment Near UVU (mock)",
        "url": "https://www.facebook.com/marketplace/item/1000000000000001",
        "price": 1100,
        "location": "Orem, UT",
        "bedrooms": 2,
        "bathrooms": 1,
    },
    {
        "product_id": "1000000000000002",
        "title": "Studio in Provo (mock)",
        "link": "https://www.facebook.com/marketplace/item/1000000000000002",
        "initial_price": "$950",
        "location": "Provo, UT",
    },
]


def run_fetch_dry_run(db_path: str) -> int:
    """Insert mock listings into DB (no API). For Phase 0 Step 4 verification."""
    conn = get_connection(db_path)
    try:
        n = 0
        for rec in MOCK_RECORDS:
            norm = normalize_record(rec)
            upsert_listing(
                conn,
                source="facebook_marketplace",
                source_listing_id=norm["source_listing_id"],
                link=norm["link"],
                title=norm.get("title"),
                price=norm.get("price"),
                beds=norm.get("beds"),
                baths=norm.get("baths"),
                address_raw=norm.get("address_raw"),
            )
            n += 1
        return n
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = get_db_path()
    n = ingest_all_downloaded_from_history(db_path)
    if n == 0:
        log.info("No records ingested (no downloaded snapshots to process).")
    else:
        log.info("Ingested %d records into %s from downloaded snapshots", n, db_path)

