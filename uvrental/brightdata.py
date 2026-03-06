"""
Bright Data snapshot trigger utilities (Facebook Marketplace dataset).

This module encapsulates the logic for:
- Triggering a Bright Data dataset snapshot.
- Recording the snapshot_id in snapshot_history.jsonl.

The CLI entrypoint for this lives in scripts/scrape.py.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

# History file lives at the project root (shared with uvrental.ingest).
SNAPSHOT_HISTORY_PATH = Path(__file__).resolve().parents[1] / "snapshot_history.jsonl"

# Default dataset and query parameters (can be overridden by env or CLI).
DEFAULT_DATASET_ID = "gd_lvt9iwuh6fbcwmx1a"
DEFAULT_KEYWORD = "Apartment"
DEFAULT_CITY = "Provo, UT"
DEFAULT_RADIUS_MILES = 20
DEFAULT_LIMIT_PER_INPUT = 10

TRIGGER_BASE_URL = "https://api.brightdata.com/datasets/v3/trigger"


def _env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default or "")
    return val.strip() if isinstance(val, str) else ""


def build_trigger_url(dataset_id: str, limit_per_input: int) -> str:
    return (
        f"{TRIGGER_BASE_URL}"
        f"?dataset_id={dataset_id}"
        "&notify=false"
        "&include_errors=true"
        "&type=discover_new"
        "&discover_by=keyword"
        f"&limit_per_input={limit_per_input}"
    )


def trigger_snapshot(
    api_key: str,
    *,
    dataset_id: str,
    keyword: str,
    city: str,
    radius_miles: int,
    limit_per_input: int,
    timeout_sec: int = 60,
) -> dict[str, Any]:
    """
    Call Bright Data's trigger endpoint for the Facebook Marketplace dataset.

    Returns the parsed JSON response. Raises for non-2xx responses.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "input": [
            {
                "keyword": keyword,
                "city": city,
                "radius": radius_miles,
                "date_listed": "",
            }
        ],
    }
    url = build_trigger_url(dataset_id, limit_per_input)
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
    if not resp.ok:
        try:
            err: Any = resp.json()
        except Exception:
            err = resp.text[:500] if resp.text else "(empty)"
        # Let the caller decide how to surface the error; we raise after logging.
        print("API error:", resp.status_code, err, file=__import__("sys").stderr)
        resp.raise_for_status()
    return resp.json()


def extract_snapshot_id(response: dict[str, Any]) -> str | None:
    """
    Extract snapshot_id from a Bright Data trigger response.
    """
    return response.get("snapshot_id") or response.get("snapshot_ID")


def record_snapshot_history(snapshot_id: str, status: str = "initiated") -> None:
    """
    Append a snapshot history record to snapshot_history.jsonl.

    This matches the shape used by the ingest module:
    {timestamp, snapshot_id, status, updated_ts}.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "timestamp": ts,
        "snapshot_id": snapshot_id,
        "status": status,
        "updated_ts": ts,
    }
    SNAPSHOT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SNAPSHOT_HISTORY_PATH.open("a", encoding="utf-8") as f:
        json.dump(record, f)
        f.write("\n")


def trigger_from_env() -> None:
    """
    Convenience function used by the CLI:
    - Reads API key and basic params from environment.
    - Triggers a snapshot.
    - Prints the response and records snapshot_id in history.
    """
    api_key = _env("BRIGHTDATA_API_KEY")
    if not api_key:
        raise SystemExit("Missing BRIGHTDATA_API_KEY in environment")

    dataset_id = _env("BRIGHTDATA_DATASET_ID", DEFAULT_DATASET_ID)
    keyword = _env("BRIGHTDATA_KEYWORD", DEFAULT_KEYWORD)
    city = _env("BRIGHTDATA_CITY", DEFAULT_CITY)
    radius = int(_env("BRIGHTDATA_RADIUS_MILES", str(DEFAULT_RADIUS_MILES)))
    limit_per_input = int(
        _env("BRIGHTDATA_LIMIT_PER_INPUT", str(DEFAULT_LIMIT_PER_INPUT))
    )

    data = trigger_snapshot(
        api_key,
        dataset_id=dataset_id,
        keyword=keyword,
        city=city,
        radius_miles=radius,
        limit_per_input=limit_per_input,
    )
    print(data)
    snapshot_id = extract_snapshot_id(data)
    if snapshot_id:
        record_snapshot_history(snapshot_id, status="initiated")
        print(f"Recorded snapshot_id={snapshot_id} in {SNAPSHOT_HISTORY_PATH.name}")
    else:
        print("Warning: trigger response did not include snapshot_id")


if __name__ == "__main__":
    trigger_from_env()

