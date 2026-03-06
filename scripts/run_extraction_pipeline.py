#!/usr/bin/env python3
"""
Two-stage extraction pipeline: regex (Stage 1) + Claude (Stage 2).

Reads from descriptions CSV (product_id, title, description), runs Stage 1 regex,
sends listings with missing/ambiguous fields to Claude in batches, writes output CSV.

Usage:
    python scripts/run_extraction_pipeline.py [input_csv] [output_csv]

Defaults:
    input_csv:  descriptions_sd_mme3w7li1z5y9k050f.csv (repo root)
    output_csv: extracted_sd_mme3w7li1z5y9k050f.csv (repo root)

Requires: ANTHROPIC_API_KEY in env. Optional: CLAUDE_MODEL.
"""

import csv
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_INPUT = REPO_ROOT / "descriptions_sd_mme3w7li1z5y9k050f.csv"
DEFAULT_OUTPUT = REPO_ROOT / "extracted_sd_mme3w7li1z5y9k050f.csv"
BATCH_SIZE = 5


def _serialize_value(val) -> str:
    """Serialize value for CSV (lists as JSON string)."""
    if val is None:
        return ""
    if isinstance(val, list):
        return json.dumps(val)
    return str(val)


def process_listings(
    input_csv: Path,
    output_csv: Path,
    batch_size: int = BATCH_SIZE,
) -> None:
    with open(input_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    from uvrental.extraction_regex import run_stage1
    from uvrental.extraction_claude import call_claude, call_claude_batch

    results = []
    llm_queue = []

    # Stage 1: run regex on all listings
    for row in rows:
        combined_id = row.get("product_id", "")
        title = row.get("title", "")
        description = row.get("description", "")
        s1 = run_stage1(title, description)
        results.append({"id": combined_id, "title": title, **s1})
        if s1.get("_needs_llm"):
            llm_queue.append({
                "idx": len(results) - 1,
                "title": title,
                "description": description,
                "stage1": s1,
            })

    print(f"Stage 1 complete. {len(llm_queue)}/{len(rows)} listings need LLM.")

    # Stage 2: batch LLM calls
    for i in range(0, len(llm_queue), batch_size):
        batch = llm_queue[i : i + batch_size]
        try:
            llm_results = call_claude_batch(batch)
            for j, llm_out in enumerate(llm_results):
                if j < len(batch):
                    original_idx = batch[j]["idx"]
                    # Merge LLM output into results (overwrite Stage 1 values)
                    for k, v in llm_out.items():
                        if not k.startswith("_"):
                            results[original_idx][k] = v
        except Exception as e:
            print(f"Batch {i // batch_size} failed: {e}")
            # Fall back to individual calls for this batch
            for item in batch:
                try:
                    out = call_claude(
                        item["title"], item["description"], item["stage1"]
                    )
                    for k, v in out.items():
                        if not k.startswith("_"):
                            results[item["idx"]][k] = v
                except Exception as e2:
                    print(f"  Single call also failed for listing {item['idx']}: {e2}")
        time.sleep(0.5)

    # Write output
    fieldnames = [
        "id",
        "title",
        "bedrooms",
        "bathrooms",
        "in_unit_washer_dryer",
        "has_roommates",
        "gender_preference",
        "utilities_included",
        "non_included_utilities_cost",
        "lease_length",
    ]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row_out = {k: _serialize_value(r.get(k)) for k in fieldnames}
            writer.writerow(row_out)

    print(f"Done. Output written to {output_csv}")


def main() -> None:
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    if not input_path.is_absolute():
        input_path = REPO_ROOT / input_path
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) > 2:
        output_path = Path(sys.argv[2])
    else:
        stem = input_path.stem.replace("descriptions_", "")
        output_path = REPO_ROOT / f"extracted_{stem}.csv"
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path

    process_listings(input_path, output_path)


if __name__ == "__main__":
    main()
