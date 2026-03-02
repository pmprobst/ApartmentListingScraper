"""
Copy of scrape.py that triggers a collection, polls until ready,
downloads the JSON snapshot, and saves it to a local file.
"""

import json
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("BRIGHT_DATA_API_KEY", "").strip()
if not api_key:
    raise SystemExit("Missing BRIGHT_DATA_API_KEY in .env")

TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"
PROGRESS_URL = "https://api.brightdata.com/datasets/v3/progress"
SNAPSHOT_DOWNLOAD_URL = "https://api.brightdata.com/datasets/snapshots"

POLL_INTERVAL_SEC = 15
POLL_TIMEOUT_SEC = 300
REQUEST_TIMEOUT_SEC = 60

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

# Bypass proxy for Bright Data API
proxies = {"http": None, "https": None}

# 1. Trigger collection
data = {
    "input": [
        {"keyword": "Apartment", "city": "Provo", "radius": 20, "date_listed": ""}
    ],
}
response = requests.post(
    "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lvt9iwuh6fbcwmx1a&notify=false&include_errors=true&type=discover_new&discover_by=keyword&limit_per_input=2",
    headers=headers,
    json=data,
    proxies=proxies,
    timeout=REQUEST_TIMEOUT_SEC,
)
response.raise_for_status()
trigger_data = response.json()
snapshot_id = trigger_data.get("snapshot_id") or trigger_data.get("snapshot_ID")
if not snapshot_id:
    raise SystemExit(f"No snapshot_id in response: {trigger_data}")

print(f"Triggered snapshot_id={snapshot_id}")

# 2. Poll until ready
deadline = time.monotonic() + POLL_TIMEOUT_SEC
while time.monotonic() < deadline:
    r = requests.get(
        f"{PROGRESS_URL}/{snapshot_id}",
        headers={"Authorization": headers["Authorization"]},
        proxies=proxies,
        timeout=REQUEST_TIMEOUT_SEC,
    )
    if r.status_code == 404:
        print("Progress 404; trying download anyway")
        break
    r.raise_for_status()
    prog = r.json()
    status = (prog.get("status") or "").lower()
    if status == "ready":
        break
    if status == "failed":
        raise SystemExit(f"Snapshot failed: {prog}")
    print(f"Status: {status}")
    time.sleep(POLL_INTERVAL_SEC)
else:
    raise SystemExit("Timeout waiting for snapshot")

# 3. Download snapshot
r = requests.get(
    f"{SNAPSHOT_DOWNLOAD_URL}/{snapshot_id}/download",
    headers={"Authorization": headers["Authorization"]},
    params={"format": "json"},
    proxies=proxies,
    timeout=REQUEST_TIMEOUT_SEC,
)
if r.status_code == 202:
    raise SystemExit("Snapshot not ready (202); try again later")
r.raise_for_status()
payload = r.json()

# 4. Save to file
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
