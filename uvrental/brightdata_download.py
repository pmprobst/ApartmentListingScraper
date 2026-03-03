"""
Bright Data snapshot status + download utilities.

This module encapsulates the logic for:
- Finding the latest pending snapshot_id from snapshot_history.jsonl.
- Checking snapshot status.
- Downloading a ready snapshot payload to marketplace_snapshot_<id>.json.

The CLI entrypoint for this lives in scripts/scrape_download.py.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

SNAPSHOT_HISTORY_PATH = Path(__file__).resolve().parents[1] / "snapshot_history.jsonl"
PROGRESS_URL = "https://api.brightdata.com/datasets/v3/progress"
SNAPSHOT_DOWNLOAD_URL = "https://api.brightdata.com/datasets/v3/snapshot"
REQUEST_TIMEOUT_SEC = 60


def _env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default or "")
    return val.strip() if isinstance(val, str) else ""


def _append_history(snapshot_id: str, status: str) -> None:
    """Append a status update for a snapshot to snapshot_history.jsonl."""
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


def latest_pending_snapshot_id() -> str:
    """
    Return the latest snapshot_id whose most recent status is not 'downloaded'.
    """
    if not SNAPSHOT_HISTORY_PATH.exists():
        raise SystemExit(f"No snapshot history file found at {SNAPSHOT_HISTORY_PATH}")
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
        if status == "downloaded":
            continue
        return sid
    raise SystemExit(f"No valid snapshot_id entries found in {SNAPSHOT_HISTORY_PATH}")


def get_snapshot_status(api_key: str, snapshot_id: str) -> Tuple[str, dict[str, Any]]:
    """
    Query Bright Data's progress endpoint for a snapshot_id.

    Returns (status_string, full_progress_payload).
    Raises SystemExit(1) if the snapshot is 404/not found.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    proxies = {"http": None, "https": None}
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
    return status, prog


def download_snapshot(api_key: str, snapshot_id: str) -> Tuple[Path, int]:
    """
    Download a ready snapshot and write marketplace_snapshot_<id>.json.

    Returns (output_path, record_count). Raises for non-2xx/non-202.
    If the server returns 202 (not ready), exits with code 0 after printing.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    proxies = {"http": None, "https": None}

    resp = requests.get(
        f"{SNAPSHOT_DOWNLOAD_URL}/{snapshot_id}",
        headers=headers,
        params={"format": "json"},
        proxies=proxies,
        timeout=REQUEST_TIMEOUT_SEC,
    )
    if resp.status_code == 202:
        print(f"Snapshot {snapshot_id} reported 202 (not ready) at download time.")
        raise SystemExit(0)

    resp.raise_for_status()
    payload = resp.json()

    out_path = Path(__file__).resolve().parents[1] / f"marketplace_snapshot_{snapshot_id}.json"
    with out_path.open("w") as f:
        json.dump(payload, f, indent=2)

    count = 0
    if isinstance(payload, list):
        count = len(payload)
    elif isinstance(payload, dict):
        for key in ("data", "results", "listings", "items", "records"):
            if isinstance(payload.get(key), list):
                count = len(payload[key])
                break

    _append_history(snapshot_id, "downloaded")
    return out_path, count


def run_from_env(snapshot_id_arg: str | None = None) -> None:
    """
    Convenience function used by the CLI:
    - Reads API key from env.
    - Determines snapshot_id (CLI arg or latest pending).
    - Prints status and downloads snapshot when ready.
    """
    api_key = _env("BRIGHTDATA_API_KEY")
    if not api_key:
        raise SystemExit("Missing BRIGHTDATA_API_KEY in environment")

    if snapshot_id_arg:
        snapshot_id = snapshot_id_arg.strip()
        if not snapshot_id:
            raise SystemExit("Snapshot ID must not be empty")
    else:
        snapshot_id = latest_pending_snapshot_id()
        print(f"Using latest snapshot_id from history: {snapshot_id}")

    status, _prog = get_snapshot_status(api_key, snapshot_id)
    print(f"Status for {snapshot_id}: {status}")

    if status != "ready":
        _append_history(snapshot_id, "running")
        raise SystemExit(0)

    out_path, count = download_snapshot(api_key, snapshot_id)
    print(f"Saved to {out_path} ({count} records)")


if __name__ == "__main__":
    run_from_env(None)

