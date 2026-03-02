import os
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("BRIGHT_DATA_API_KEY", "").strip()
if not api_key:
    raise SystemExit("Missing BRIGHT_DATA_API_KEY in .env")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

payload = {
    "input": [
        {"keyword": "Apartment", "city": "Provo", "radius": 20, "date_listed": ""}
    ],
}

# Where we keep a history of snapshot_ids
SNAPSHOT_HISTORY_PATH = Path(__file__).with_name("snapshot_history.jsonl")

response = requests.post(
    "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lvt9iwuh6fbcwmx1a&notify=false&include_errors=true&type=discover_new&discover_by=keyword&limit_per_input=1000",
    headers=headers,
    json=payload,
    timeout=60,
)
response.raise_for_status()

data = response.json()
print(data)

snapshot_id = data.get("snapshot_id") or data.get("snapshot_ID")
if snapshot_id:
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_id": snapshot_id,
    }
    with SNAPSHOT_HISTORY_PATH.open("a", encoding="utf-8") as f:
        json.dump(record, f)
        f.write("\n")
    print(f"Recorded snapshot_id={snapshot_id} in {SNAPSHOT_HISTORY_PATH.name}")
else:
    print("Warning: trigger response did not include snapshot_id")