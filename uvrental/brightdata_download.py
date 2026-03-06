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
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_HISTORY_PATH = PROJECT_ROOT / "snapshot_history.jsonl"
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
    Return the latest snapshot_id whose most recent status is still pending
    (i.e. not 'downloaded' or 'ingested').

    Raises FileNotFoundError if history file is missing; ValueError if no valid snapshot_id.
    """
    if not SNAPSHOT_HISTORY_PATH.exists():
        raise FileNotFoundError(f"No snapshot history file at {SNAPSHOT_HISTORY_PATH}")
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
        if status in {"downloaded", "ingested"}:
            continue
        return sid
    raise ValueError(f"No valid snapshot_id entries found in {SNAPSHOT_HISTORY_PATH}")


def get_snapshot_status(api_key: str, snapshot_id: str) -> Tuple[str, dict[str, Any]]:
    """
    Query Bright Data's progress endpoint for a snapshot_id.

    Returns (status_string, full_progress_payload).
    Raises RuntimeError if the snapshot is 404/not found; requests.RequestException on network errors.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    proxies = {"http": None, "https": None}
    try:
        resp = requests.get(
            f"{PROGRESS_URL}/{snapshot_id}",
            headers=headers,
            proxies=proxies,
            timeout=REQUEST_TIMEOUT_SEC,
        )
    except requests.RequestException as e:
        log.error("Bright Data progress request failed for %s: %s", snapshot_id, e)
        raise
    if resp.status_code == 404:
        log.error("Snapshot %s not found (404).", snapshot_id)
        raise RuntimeError(f"Snapshot {snapshot_id} not found (404)")
    resp.raise_for_status()
    try:
        prog = resp.json()
    except json.JSONDecodeError as e:
        log.error("Bright Data progress invalid JSON for %s: %s", snapshot_id, e)
        raise
    status = (prog.get("status") or "").lower()
    return status, prog


class SnapshotNotReadyError(Exception):
    """Raised when the snapshot download returns 202 (not ready)."""


def download_snapshot(api_key: str, snapshot_id: str) -> Tuple[Path, int]:
    """
    Download a ready snapshot and write marketplace_snapshot_<id>.json.

    Returns (output_path, record_count). Raises SnapshotNotReadyError on 202.
    Raises requests.RequestException on network/HTTP errors.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    proxies = {"http": None, "https": None}

    try:
        resp = requests.get(
            f"{SNAPSHOT_DOWNLOAD_URL}/{snapshot_id}",
            headers=headers,
            params={"format": "json"},
            proxies=proxies,
            timeout=REQUEST_TIMEOUT_SEC,
        )
    except requests.RequestException as e:
        log.error("Bright Data download request failed for %s: %s", snapshot_id, e)
        raise
    if resp.status_code == 202:
        log.info("Snapshot %s reported 202 (not ready) at download time.", snapshot_id)
        raise SnapshotNotReadyError(f"Snapshot {snapshot_id} not ready (202)")

    resp.raise_for_status()
    try:
        payload = resp.json()
    except json.JSONDecodeError as e:
        log.error("Bright Data download invalid JSON for %s: %s", snapshot_id, e)
        raise
    snapshots_dir = PROJECT_ROOT / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    out_path = snapshots_dir / f"marketplace_snapshot_{snapshot_id}.json"
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
    Raises ValueError for missing/invalid args; SnapshotNotReadyError on 202; RuntimeError on 404.
    """
    api_key = _env("BRIGHTDATA_API_KEY")
    if not api_key:
        raise ValueError("Missing BRIGHTDATA_API_KEY in environment")

    if snapshot_id_arg:
        snapshot_id = snapshot_id_arg.strip()
        if not snapshot_id:
            raise ValueError("Snapshot ID must not be empty")
    else:
        snapshot_id = latest_pending_snapshot_id()
        print(f"Using latest snapshot_id from history: {snapshot_id}")

    log.info("Checking snapshot %s status", snapshot_id)
    status, _prog = get_snapshot_status(api_key, snapshot_id)
    print(f"Status for {snapshot_id}: {status}")

    if status != "ready":
        _append_history(snapshot_id, "running")
        raise SnapshotNotReadyError(f"Snapshot {snapshot_id} status is {status!r}, not ready")

    out_path, count = download_snapshot(api_key, snapshot_id)
    log.info("Downloaded snapshot %s: %d records to %s", snapshot_id, count, out_path)
    print(f"Saved to {out_path} ({count} records)")


if __name__ == "__main__":
    run_from_env(None)

