"""
Bright Data snapshot status + download utilities.

This module encapsulates the logic for:
- Finding pending snapshot_ids from snapshot_history.jsonl (all pending, oldest first).
- Checking snapshot status via the progress API.
- Downloading ready snapshot payloads to marketplace_snapshot_<id>.json.

The CLI entrypoint for this lives in scripts/scrape_download.py.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

PROGRESS_URL = "https://api.brightdata.com/datasets/v3/progress"
SNAPSHOT_DOWNLOAD_URL = "https://api.brightdata.com/datasets/v3/snapshot"
REQUEST_TIMEOUT_SEC = 60
DOWNLOAD_RETRY_DELAY_SEC = 5
DOWNLOAD_MAX_ATTEMPTS = 2

_snapshot_history_path_cache: Path | None = None
_snapshots_dir_cache: Path | None = None


def _snapshot_history_path() -> Path:
    global _snapshot_history_path_cache
    if _snapshot_history_path_cache is None:
        from .config import get_snapshot_history_path
        _snapshot_history_path_cache = get_snapshot_history_path()
    return _snapshot_history_path_cache


def _snapshots_dir() -> Path:
    global _snapshots_dir_cache
    if _snapshots_dir_cache is None:
        from .config import get_snapshots_dir
        _snapshots_dir_cache = get_snapshots_dir()
    return _snapshots_dir_cache


def _env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default or "")
    return val.strip() if isinstance(val, str) else ""


def _append_history(snapshot_id: str, status: str) -> None:
    """Append a status update for a snapshot to snapshot_history.jsonl."""
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


def _pending_snapshot_ids_oldest_first() -> list[str]:
    """
    Return snapshot_ids that are still pending (not downloaded/ingested),
    in chronological order (oldest first) so we try the longest-running first.
    """
    path = _snapshot_history_path()
    if not path.exists():
        return []
    states: dict[str, str] = {}
    order: list[str] = []
    seen: set[str] = set()
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
            status = (rec.get("status") or "").lower()
            states[sid] = status
            if sid not in seen:
                seen.add(sid)
                order.append(sid)
    return [sid for sid in order if states.get(sid, "") not in {"downloaded", "ingested"}]


def latest_pending_snapshot_id() -> str:
    """
    Return the latest snapshot_id whose most recent status is still pending
    (i.e. not 'downloaded' or 'ingested').

    Raises FileNotFoundError if history file is missing; ValueError if no valid snapshot_id.
    """
    path = _snapshot_history_path()
    if not path.exists():
        raise FileNotFoundError(f"No snapshot history file at {path}")
    pending = _pending_snapshot_ids_oldest_first()
    if not pending:
        raise ValueError(f"No valid snapshot_id entries found in {path}")
    return pending[-1]


def get_snapshot_status(api_key: str, snapshot_id: str) -> Tuple[str, dict[str, Any]]:
    """
    Query Bright Data's progress endpoint for a snapshot_id.

    Returns (status_string, full_progress_payload).
    Raises RuntimeError if the snapshot is 404/not found; requests.RequestException on network errors.
    Retries once on timeout or 5xx.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    proxies = {"http": None, "https": None}
    url = f"{PROGRESS_URL}/{snapshot_id}"
    last_exc: BaseException | None = None
    for attempt in range(1, DOWNLOAD_MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=REQUEST_TIMEOUT_SEC,
            )
        except requests.RequestException as e:
            log.error("Bright Data progress request failed for %s (attempt %d/%d): %s", snapshot_id, attempt, DOWNLOAD_MAX_ATTEMPTS, e)
            last_exc = e
            if attempt < DOWNLOAD_MAX_ATTEMPTS:
                log.info("Retrying in %d seconds...", DOWNLOAD_RETRY_DELAY_SEC)
                time.sleep(DOWNLOAD_RETRY_DELAY_SEC)
            else:
                raise
            continue
        if resp.status_code == 404:
            log.error("Snapshot %s not found (404).", snapshot_id)
            raise RuntimeError(f"Snapshot {snapshot_id} not found (404)")
        if not resp.ok and attempt < DOWNLOAD_MAX_ATTEMPTS and resp.status_code >= 500:
            log.error("Bright Data progress error %s for %s (attempt %d/%d); retrying.", resp.status_code, snapshot_id, attempt, DOWNLOAD_MAX_ATTEMPTS)
            time.sleep(DOWNLOAD_RETRY_DELAY_SEC)
            continue
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
    Retries once on timeout or 5xx.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    proxies = {"http": None, "https": None}
    url = f"{SNAPSHOT_DOWNLOAD_URL}/{snapshot_id}"
    for attempt in range(1, DOWNLOAD_MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(
                url,
                headers=headers,
                params={"format": "json"},
                proxies=proxies,
                timeout=REQUEST_TIMEOUT_SEC,
            )
        except requests.RequestException as e:
            log.error("Bright Data download request failed for %s (attempt %d/%d): %s", snapshot_id, attempt, DOWNLOAD_MAX_ATTEMPTS, e)
            if attempt < DOWNLOAD_MAX_ATTEMPTS:
                log.info("Retrying in %d seconds...", DOWNLOAD_RETRY_DELAY_SEC)
                time.sleep(DOWNLOAD_RETRY_DELAY_SEC)
            else:
                raise
            continue
        if resp.status_code == 202:
            log.info("Snapshot %s reported 202 (not ready) at download time.", snapshot_id)
            raise SnapshotNotReadyError(f"Snapshot {snapshot_id} not ready (202)")
        if not resp.ok and attempt < DOWNLOAD_MAX_ATTEMPTS and resp.status_code >= 500:
            log.error("Bright Data download error %s for %s (attempt %d/%d); retrying.", resp.status_code, snapshot_id, attempt, DOWNLOAD_MAX_ATTEMPTS)
            time.sleep(DOWNLOAD_RETRY_DELAY_SEC)
            continue
        resp.raise_for_status()
        break
    try:
        payload = resp.json()
    except json.JSONDecodeError as e:
        log.error("Bright Data download invalid JSON for %s: %s", snapshot_id, e)
        raise
    snapshots_dir = _snapshots_dir()
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
    - With no arg: checks all pending snapshots (oldest first), downloads any that are ready.
    - With <snapshot_id>: checks that snapshot only and downloads if ready.
    Raises ValueError for missing/invalid args; SnapshotNotReadyError when a single snapshot is not ready.
    """
    api_key = _env("BRIGHTDATA_API_KEY")
    if not api_key:
        raise ValueError("Missing BRIGHTDATA_API_KEY in environment")

    if snapshot_id_arg:
        snapshot_id = snapshot_id_arg.strip()
        if not snapshot_id:
            raise ValueError("Snapshot ID must not be empty")
        ids_to_try = [snapshot_id]
        single_snapshot = True
    else:
        ids_to_try = _pending_snapshot_ids_oldest_first()
        if not ids_to_try:
            raise ValueError("No pending snapshots in history")
        single_snapshot = False
        print(f"Found {len(ids_to_try)} pending snapshot(s); checking oldest first.")

    downloaded = 0
    for sid in ids_to_try:
        try:
            status, _prog = get_snapshot_status(api_key, sid)
        except RuntimeError as e:
            log.warning("Skipping %s: %s", sid, e)
            continue
        log.info("Snapshot %s status: %s", sid, status)
        if single_snapshot:
            print(f"Status for {sid}: {status}")
        if status != "ready":
            _append_history(sid, "running")
            if single_snapshot:
                raise SnapshotNotReadyError(f"Snapshot {sid} status is {status!r}, not ready")
            continue
        try:
            out_path, count = download_snapshot(api_key, sid)
            downloaded += 1
            log.info("Downloaded snapshot %s: %d records to %s", sid, count, out_path)
            print(f"Saved {sid} to {out_path} ({count} records)")
        except SnapshotNotReadyError:
            _append_history(sid, "running")
            if single_snapshot:
                raise
            log.warning("Snapshot %s returned 202 (not ready); skipping.", sid)
        except requests.RequestException as e:
            log.warning("Download failed for %s: %s", sid, e)
            if single_snapshot:
                raise

    if not single_snapshot and downloaded == 0:
        print("No snapshots were ready to download yet.")
    elif not single_snapshot and downloaded > 0:
        print(f"Downloaded {downloaded} snapshot(s).")


if __name__ == "__main__":
    run_from_env(None)

