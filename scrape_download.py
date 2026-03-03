"""
Check the status of a Bright Data snapshot and,
if it is ready, download the JSON snapshot and save it locally.

Usage:
    python scrape_download.py            # uses latest snapshot from snapshot_history.jsonl
    python scrape_download.py <snapshot_id>  # check/download specific snapshot

Behavior:
- If status is \"ready\": download JSON and exit.
- If status is anything else (e.g. \"running\", \"starting\"): print status and exit without downloading.
"""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("BRIGHTDATA_API_KEY", "").strip()
if not api_key:
    raise SystemExit("Missing BRIGHTDATA_API_KEY in .env")

SNAPSHOT_HISTORY_PATH = Path(__file__).with_name("snapshot_history.jsonl")


def _append_history(snapshot_id: str, status: str) -> None:
    """Append a status update for a snapshot to snapshot_history.jsonl."""
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "timestamp": ts,
        "snapshot_id": snapshot_id,
        "status": status,
        "updated_ts": ts,
    }
    with SNAPSHOT_HISTORY_PATH.open("a", encoding="utf-8") as f:
        json.dump(record, f)
        f.write("\n")


def _latest_snapshot_id() -> str:
    if not SNAPSHOT_HISTORY_PATH.exists():
        raise SystemExit(f"No snapshot history file found at {SNAPSHOT_HISTORY_PATH}")
    # Read lines and scan from the end, considering only the latest state per snapshot_id.
    with SNAPSHOT_HISTORY_PATH.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    seen_ids: set[str] = set()
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = rec.get("snapshot_id")
        if not sid or sid in seen_ids:
            continue
        seen_ids.add(sid)
        status = (rec.get("status") or "").lower()
        # Skip snapshots whose latest state is 'downloaded'
        if status == "downloaded":
            continue
        return sid
    raise SystemExit(f"No valid snapshot_id entries found in {SNAPSHOT_HISTORY_PATH}")


if len(sys.argv) == 2:
    snapshot_id = sys.argv[1].strip()
    if not snapshot_id:
        raise SystemExit("Snapshot ID must not be empty")
else:
    snapshot_id = _latest_snapshot_id()
    print(f"Using latest snapshot_id from history: {snapshot_id}")

PROGRESS_URL = "https://api.brightdata.com/datasets/v3/progress"
SNAPSHOT_DOWNLOAD_URL = "https://api.brightdata.com/datasets/v3/snapshot"

REQUEST_TIMEOUT_SEC = 60

headers = {
    "Authorization": f"Bearer {api_key}",
}

# Bypass proxy for Bright Data API
proxies = {"http": None, "https": None}

# 1. Check snapshot status once
resp = requests.get(
    f"{PROGRESS_URL}/{snapshot_id}",
    headers=headers,
    proxies=proxies,
    timeout=REQUEST_TIMEOUT_SEC,
)
if resp.status_code == 404:
    print(f"Snapshot {snapshot_id} not found (404).")
    raise SystemExit(1)

resp.raise_for_status()
prog = resp.json()
status = (prog.get("status") or "").lower()
print(f"Status for {snapshot_id}: {status}")

if status != "ready":
    # Not ready yet (running/starting/etc.) – record 'running' state and exit.
    _append_history(snapshot_id, "running")
    raise SystemExit(0)

# 2. Download snapshot now that it's ready
download_resp = requests.get(
    f"{SNAPSHOT_DOWNLOAD_URL}/{snapshot_id}",
    headers=headers,
    params={"format": "json"},
    proxies=proxies,
    timeout=REQUEST_TIMEOUT_SEC,
)
if download_resp.status_code == 202:
    print(f"Snapshot {snapshot_id} reported 202 (not ready) at download time.")
    raise SystemExit(0)

download_resp.raise_for_status()
payload = download_resp.json()

# 3. Save to file
out_path = f"marketplace_snapshot_{snapshot_id}.json"
with open(out_path, "w") as f:
    json.dump(payload, f, indent=2)

# Count records if array or nested
count = 0
if isinstance(payload, list):
    count = len(payload)
elif isinstance(payload, dict):
    for key in ("data", "results", "listings", "items", "records"):
        if isinstance(payload.get(key), list):
            count = len(payload[key])
            break

print(f"Saved to {out_path} ({count} records)")
_append_history(snapshot_id, "downloaded")
