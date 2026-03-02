"""
Phase 0: Fetch Facebook Marketplace listings from Bright Data API and upsert into SQLite.
Reads DB path and API params from env. No run_status in this phase.
See plan/phase-0.md and plan/reference.md.
"""

import hashlib
import json
import logging
import os
import re
import time
from dotenv import load_dotenv
import requests

from db import get_connection, upsert_listing

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Env: required (try Facebook Marketplace key first, then generic)
BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY = "BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY"
BRIGHTDATA_API_KEY = "BRIGHTDATA_API_KEY"
LISTINGS_DB = "LISTINGS_DB"

# Env: optional (Bright Data params)
BRIGHTDATA_DATASET_ID = "BRIGHTDATA_DATASET_ID"
BRIGHTDATA_KEYWORD = "BRIGHTDATA_KEYWORD"
BRIGHTDATA_CITY = "BRIGHTDATA_CITY"

DEFAULT_DATASET_ID = "gd_lvt9iwuh6fbcwmx1a"
DEFAULT_KEYWORD = "Apartment"
DEFAULT_CITY = "Provo"
DEFAULT_DB = "listings.db"

TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"
PROGRESS_URL = "https://api.brightdata.com/datasets/v3/progress"
SNAPSHOT_DOWNLOAD_URL = "https://api.brightdata.com/datasets/snapshots"

POLL_INTERVAL_SEC = 15
POLL_TIMEOUT_SEC = 300  # 5 min
REQUEST_TIMEOUT_SEC = 60


def _env(key: str, default: str | None = None) -> str:
    v = os.environ.get(key, default or "")
    return v.strip() if isinstance(v, str) else ""


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


# Canonical Marketplace URL format (Facebook expects this for item pages)
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
        # Sometimes ID is in a sub-dict or has prefix
        if s and s.replace("-", "").isdigit():
            return s
    # Try to parse from URL (e.g. .../marketplace/item/123456 or .../item/123)
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
    # Prefer canonical URL built from numeric ID (Facebook expects marketplace/item/ID)
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
    }


def trigger_collection(api_key: str, dataset_id: str, keyword: str, city: str) -> str | None:
    """Start Bright Data collection; return snapshot_id or None on failure."""
    url = f"{TRIGGER_URL}?dataset_id={dataset_id}&notify=false&include_errors=true&type=discover_new&discover_by=keyword"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"input": [{"keyword": keyword, "city": city, "date_listed": ""}]}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SEC)
        if not r.ok:
            try:
                err_body = r.json()
            except Exception:
                err_body = r.text[:500] if r.text else "(empty)"
            log.error("Trigger %s: %s", r.status_code, err_body)
            return None
        data = r.json()
        sid = data.get("snapshot_id") or data.get("snapshot_ID")
        if sid:
            return str(sid)
        log.error("Trigger response missing snapshot_id: %s", data)
        return None
    except requests.RequestException as e:
        log.exception("Trigger request failed: %s", e)
        return None
    except json.JSONDecodeError as e:
        log.error("Trigger response not JSON: %s", e)
        return None


def wait_for_ready(api_key: str, snapshot_id: str) -> bool:
    """Poll progress until status is ready or timeout."""
    url = f"{PROGRESS_URL}/{snapshot_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.monotonic() + POLL_TIMEOUT_SEC
    while time.monotonic() < deadline:
        try:
            r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
            if r.status_code == 404:
                log.warning("Progress 404 for %s; will try download anyway", snapshot_id)
                return True
            r.raise_for_status()
            data = r.json()
            status = (data.get("status") or "").lower()
            if status == "ready":
                return True
            if status == "failed":
                log.error("Snapshot %s failed: %s", snapshot_id, data)
                return False
            log.info("Snapshot %s status: %s", snapshot_id, status)
        except requests.RequestException as e:
            log.warning("Progress request failed: %s", e)
        time.sleep(POLL_INTERVAL_SEC)
    log.error("Timeout waiting for snapshot %s", snapshot_id)
    return False


def download_snapshot(api_key: str, snapshot_id: str) -> list[dict]:
    """Download snapshot content; return list of records (empty on failure)."""
    # API: GET /datasets/snapshots/{id}/download?format=json
    url = f"{SNAPSHOT_DOWNLOAD_URL}/{snapshot_id}/download"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"format": "json"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT_SEC)
        if r.status_code == 202:
            log.warning("Snapshot not ready (202); try again later")
            return []
        r.raise_for_status()
        data = r.json()
        # Response can be array or object with array inside
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "results", "listings", "items", "records"):
                if isinstance(data.get(key), list):
                    return data[key]
            # Single object as one record
            return [data]
        return []
    except requests.RequestException as e:
        log.exception("Download failed: %s", e)
        return []
    except json.JSONDecodeError as e:
        log.error("Download response not JSON: %s", e)
        return []


def run_fetch(
    db_path: str,
    api_key: str,
    dataset_id: str,
    keyword: str,
    city: str,
) -> int:
    """Trigger collection, wait for ready, download, upsert. Returns count of listings upserted."""
    snapshot_id = trigger_collection(api_key, dataset_id, keyword, city)
    if not snapshot_id:
        return 0
    log.info("Triggered snapshot_id=%s", snapshot_id)
    if not wait_for_ready(api_key, snapshot_id):
        return 0
    records = download_snapshot(api_key, snapshot_id)
    if not records:
        log.warning("No records in snapshot")
        return 0
    log.info("Downloaded %d records", len(records))
    conn = get_connection(db_path)
    try:
        n = 0
        for rec in records:
            if not isinstance(rec, dict):
                continue
            norm = normalize_record(rec)
            if not norm["link"]:
                continue
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


# Placeholder listings for --dry-run only. Links use fake IDs; real API returns long numeric listing IDs (e.g. 1234567890123456).
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


def main() -> None:
    import sys
    dry_run = "--dry-run" in sys.argv
    db_path = _env(LISTINGS_DB, DEFAULT_DB)

    if dry_run:
        log.info("Dry run: inserting %d mock listings into %s", len(MOCK_RECORDS), db_path)
        n = run_fetch_dry_run(db_path)
        log.info("Upserted %d listings (dry run)", n)
        return

    api_key = _env(BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY) or _env(BRIGHTDATA_API_KEY)
    if not api_key:
        log.error("Missing %s (or %s)", BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY, BRIGHTDATA_API_KEY)
        raise SystemExit(1)
    dataset_id = _env(BRIGHTDATA_DATASET_ID, DEFAULT_DATASET_ID)
    keyword = _env(BRIGHTDATA_KEYWORD, DEFAULT_KEYWORD)
    city = _env(BRIGHTDATA_CITY, DEFAULT_CITY)

    n = run_fetch(db_path, api_key, dataset_id, keyword, city)
    log.info("Upserted %d listings into %s", n, db_path)


if __name__ == "__main__":
    main()
