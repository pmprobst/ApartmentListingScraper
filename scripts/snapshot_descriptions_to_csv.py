#!/usr/bin/env python3
"""
Extract all "description" fields from a Bright Data marketplace snapshot JSON
and write them to a single CSV file.

Usage:
    python scripts/snapshot_descriptions_to_csv.py [snapshot_json_path] [output_csv_path]

Defaults:
    snapshot_json_path: marketplace_snapshot_sd_mme3w7li1z5y9k050f.json (repo root)
    output_csv_path: descriptions_sd_mme3w7li1z5y9k050f.csv (repo root)
"""

import csv
import json
import sys
from pathlib import Path

# Repo root (parent of scripts/)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = REPO_ROOT / "marketplace_snapshot_sd_mme3w7li1z5y9k050f.json"


def load_snapshot(path: Path) -> list[dict]:
    """Load snapshot JSON; return list of record dicts."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "results", "listings", "items", "records"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def main() -> None:
    snapshot_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SNAPSHOT
    if not snapshot_path.is_absolute():
        snapshot_path = REPO_ROOT / snapshot_path
    if not snapshot_path.exists():
        print(f"Error: snapshot file not found: {snapshot_path}", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) > 2:
        out_path = Path(sys.argv[2])
    else:
        out_path = REPO_ROOT / f"descriptions_{snapshot_path.stem.replace('marketplace_snapshot_', '')}.csv"
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path

    records = load_snapshot(snapshot_path)
    rows: list[dict[str, str]] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        if rec.get("error") or rec.get("error_code"):
            continue
        product_id = str(rec.get("product_id") or rec.get("listing_id") or rec.get("id") or "")
        title = str(rec.get("title") or rec.get("name") or "").strip()
        description = str(rec.get("description") or "").strip()
        rows.append({"product_id": product_id, "title": title, "description": description})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["product_id", "title", "description"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} descriptions to {out_path}")


if __name__ == "__main__":
    main()
