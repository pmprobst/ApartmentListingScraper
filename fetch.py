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

from db import (
    get_connection,
    upsert_listing,
    update_run_status_after_fetch,
)

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
BRIGHTDATA_RADIUS_MILES = "BRIGHTDATA_RADIUS_MILES"
BRIGHTDATA_LIMIT_PER_INPUT = "BRIGHTDATA_LIMIT_PER_INPUT"
# Optional dataset-level filters (used with Filter Dataset API)
BRIGHTDATA_FILTER_COUNTRY = "BRIGHTDATA_FILTER_COUNTRY"
BRIGHTDATA_FILTER_LOCATION_INCLUDES = "BRIGHTDATA_FILTER_LOCATION_INCLUDES"

DEFAULT_DATASET_ID = "gd_lvt9iwuh6fbcwmx1a"
DEFAULT_KEYWORD = "Apartment"
DEFAULT_CITY = "Provo, UT"
DEFAULT_RADIUS_MILES = 20
# Bright Data may enforce a minimum (e.g. 100). Use 100 for testing; increase for production (e.g. 1000).
DEFAULT_LIMIT_PER_INPUT = 100
DEFAULT_DB = "listings.db"

# Defaults for dataset-side filtering (Filter Dataset API)
DEFAULT_FILTER_COUNTRY = "US"
DEFAULT_FILTER_LOCATION_INCLUDES = "Utah"

TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"
PROGRESS_URL = "https://api.brightdata.com/datasets/v3/progress"
# Match scrape_download.py: GET /datasets/v3/snapshot/{id}?format=json (no /download path)
SNAPSHOT_DOWNLOAD_URL = "https://api.brightdata.com/datasets/v3/snapshot"
FILTER_DATASET_URL = "https://api.brightdata.com/datasets/filter"

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


def trigger_collection(
    api_key: str,
    dataset_id: str,
    keyword: str,
    city: str,
    radius_miles: int = DEFAULT_RADIUS_MILES,
    limit_per_input: int = DEFAULT_LIMIT_PER_INPUT,
) -> str | None:
    """Start Bright Data collection; return snapshot_id or None on failure.
    Use city like 'Provo, UT' and radius_miles to restrict to ~20 miles around the city.
    limit_per_input caps how many records are collected per input (e.g. 100 for testing, 1000 for production).
    """
    url = (
        f"{TRIGGER_URL}?dataset_id={dataset_id}&notify=false&include_errors=true"
        f"&type=discover_new&discover_by=keyword&limit_per_input={limit_per_input}"
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    input_item: dict[str, object] = {
        "keyword": keyword,
        "city": city,
        "radius": radius_miles,
        "date_listed": "",
    }
    payload = {"input": [input_item]}
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
    """Download snapshot content; return list of records (empty on failure).
    Uses same endpoint as scrape_download.py: GET /datasets/v3/snapshot/{id}?format=json.
    """
    url = f"{SNAPSHOT_DOWNLOAD_URL}/{snapshot_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"format": "json"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT_SEC)
        if r.status_code == 202:
            log.warning("Snapshot not ready (202); try again later")
            return []
        if not r.ok:
            try:
                err_body = r.json()
            except Exception:
                err_body = r.text[:500] if r.text else "(empty)"
            log.error("Download %s: %s %s", snapshot_id, r.status_code, err_body)
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


def _build_dataset_filter(
    country: str | None, location_includes: str | None
) -> dict | None:
    """
    Build a DatasetFilter JSON object for the Filter Dataset API.

    Uses documented operators from:
    https://docs.brightdata.com/api-reference/marketplace-dataset-api/filter-dataset
    """
    filters: list[dict] = []
    if country:
        filters.append(
            {
                "name": "country_code",
                "operator": "=",
                "value": country,
            }
        )
    if location_includes:
        filters.append(
            {
                "name": "location",
                "operator": "includes",
                "value": location_includes,
            }
        )
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"operator": "and", "filters": filters}


def filter_dataset_snapshot(
    api_key: str,
    dataset_id: str,
    filter_def: dict,
    records_limit: int | None = None,
) -> str | None:
    """
    Call Bright Data's Filter Dataset API to create a filtered snapshot.

    Returns snapshot_id on success, or None on failure.
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: dict[str, object] = {
        "dataset_id": dataset_id,
        "filter": filter_def,
    }
    if records_limit is not None:
        payload["records_limit"] = int(records_limit)
    try:
        r = requests.post(
            FILTER_DATASET_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SEC
        )
        if not r.ok:
            try:
                err_body = r.json()
            except Exception:
                err_body = r.text[:500] if r.text else "(empty)"
            log.error("Filter dataset %s: %s", r.status_code, err_body)
            return None
        data = r.json()
        sid = data.get("snapshot_id")
        if sid:
            return str(sid)
        log.error("Filter dataset response missing snapshot_id: %s", data)
        return None
    except requests.RequestException as e:
        log.exception("Filter dataset request failed: %s", e)
        return None
    except json.JSONDecodeError as e:
        log.error("Filter dataset response not JSON: %s", e)
        return None


def run_fetch(
    db_path: str,
    api_key: str,
    dataset_id: str,
    keyword: str,
    city: str,
    radius_miles: int = DEFAULT_RADIUS_MILES,
    limit_per_input: int = DEFAULT_LIMIT_PER_INPUT,
) -> int:
    """
    Create a filtered snapshot (country/location) when possible, wait for ready,
    download, and upsert into SQLite. Returns count of listings upserted.
    """
    # Prefer dataset-side filtering (country + location) to reduce non-Utah noise.
    filter_country = _env(BRIGHTDATA_FILTER_COUNTRY, DEFAULT_FILTER_COUNTRY) or None
    filter_location = _env(
        BRIGHTDATA_FILTER_LOCATION_INCLUDES, DEFAULT_FILTER_LOCATION_INCLUDES
    ) or None
    filter_def = _build_dataset_filter(filter_country, filter_location)

    snapshot_id: str | None = None
    if filter_def is not None:
        log.info(
            "Requesting filtered snapshot via Filter Dataset API "
            "(country=%r, location includes=%r)",
            filter_country,
            filter_location,
        )
        snapshot_id = filter_dataset_snapshot(
            api_key,
            dataset_id,
            filter_def,
            records_limit=limit_per_input,
        )

    # Fallback: if filter API failed or filters are disabled, use trigger_collection.
    if not snapshot_id:
        log.info(
            "Falling back to trigger_collection (keyword=%r, city=%r, radius_miles=%r)",
            keyword,
            city,
            radius_miles,
        )
        snapshot_id = trigger_collection(
            api_key,
            dataset_id,
            keyword,
            city,
            radius_miles=radius_miles,
            limit_per_input=limit_per_input,
        )
        if not snapshot_id:
            return 0

    log.info("Using snapshot_id=%s", snapshot_id)
    if not wait_for_ready(api_key, snapshot_id):
        return 0
    records = download_snapshot(api_key, snapshot_id)
    if not records:
        log.warning("No records in snapshot")
        return 0
    log.info("Downloaded %d records", len(records))
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
            # Skip Bright Data error entries (e.g. "Redirect to login page", bad_input)
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
            )
            processed += 1
        # Total listings after this run
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
        return processed
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
    radius_str = _env(BRIGHTDATA_RADIUS_MILES, str(DEFAULT_RADIUS_MILES))
    try:
        radius_miles = int(radius_str)
    except ValueError:
        radius_miles = DEFAULT_RADIUS_MILES
    limit_str = _env(BRIGHTDATA_LIMIT_PER_INPUT, str(DEFAULT_LIMIT_PER_INPUT))
    try:
        limit_per_input = int(limit_str)
    except ValueError:
        limit_per_input = DEFAULT_LIMIT_PER_INPUT

    n = run_fetch(
        db_path, api_key, dataset_id, keyword, city, radius_miles, limit_per_input
    )
    log.info("Upserted %d listings into %s", n, db_path)


if __name__ == "__main__":
    main()
