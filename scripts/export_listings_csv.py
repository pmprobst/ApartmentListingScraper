"""
CLI: Export the `listings` table from the SQLite DB to a CSV file.

Usage:
    python scripts/export_listings_csv.py [output_path]

- DB path is taken from the LISTINGS_DB env var (default: listings.db).
- The CSV will include all columns from the `listings` table.
"""

import csv
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def main(argv: list[str]) -> None:
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)

    db_path = os.environ.get("LISTINGS_DB", "listings.db").strip() or "listings.db"
    output_path = (
        Path(argv[0])
        if argv
        else project_root / "listings_export.csv"
    )

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # Get column names directly from the schema so we export all fields.
        cur.execute("PRAGMA table_info(listings)")
        cols_info = cur.fetchall()
        if not cols_info:
            raise SystemExit("No `listings` table found in the database.")
        columns = [row[1] for row in cols_info]

        cur.execute(
            "SELECT {} FROM listings ORDER BY id".format(
                ", ".join(f'"{c}"' for c in columns)
            )
        )
        rows = cur.fetchall()

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)

        print(f"Wrote {len(rows)} row(s) from {db_path} to {output_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main(sys.argv[1:])

