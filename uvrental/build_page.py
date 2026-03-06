"""
Phase 1: Generate static HTML from SQLite listings and run_status.
Reads DB path, output path, and price filter from env. Applies 30-day window.
See plan/phase-1.md and plan/features.md.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

from .db import (
    get_connection,
    get_run_status,
    update_run_status_after_build_page,
)

load_dotenv()

LISTINGS_DB = "LISTINGS_DB"
BUILD_PAGE_OUTPUT = "BUILD_PAGE_OUTPUT"
PRICE_MAX = "PRICE_MAX"
PRICE_MIN = "PRICE_MIN"

DEFAULT_DB = "listings.db"
DEFAULT_OUTPUT_DIR = "docs"
DEFAULT_PRICE_MAX = 2000
DEFAULT_PRICE_MIN = 0


def _env(key: str, default: str | None = None) -> str:
    v = os.environ.get(key, default or "")
    return v.strip() if isinstance(v, str) else ""


def _parse_int_env(key: str, default: int) -> int:
    s = _env(key, str(default))
    try:
        return int(s)
    except ValueError:
        return default


def _thirty_days_ago_iso() -> str:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_run_ts(iso_ts: str | None) -> str:
    if not iso_ts:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(iso_ts)


def _format_listing_date(iso_ts: str | None) -> str:
    """Format listing_date for display (date only)."""
    if not iso_ts:
        return ""
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(iso_ts)


def _escape_html(s: str) -> str:
    """Escape &, <, > for HTML. Pass-through for placeholder —."""
    if s == "—":
        return s
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_page() -> None:
    """
    Read listings (within price range and 30-day window) and run_status from SQLite,
    generate static HTML, write to output dir, and update run_status.displayed.
    """
    db_path = _env(LISTINGS_DB, DEFAULT_DB)
    output_dir = _env(BUILD_PAGE_OUTPUT, DEFAULT_OUTPUT_DIR)
    price_max = _parse_int_env(PRICE_MAX, DEFAULT_PRICE_MAX)
    price_min = _parse_int_env(PRICE_MIN, DEFAULT_PRICE_MIN)
    cutoff = _thirty_days_ago_iso()

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                source,
                source_listing_id,
                link,
                title,
                price,
                beds,
                baths,
                first_seen,
                last_seen,
                listing_date,
                in_unit_washer_dryer,
                has_roommates,
                gender_preference,
                utilities_included,
                non_included_utilities_cost,
                lease_length
            FROM listings
            WHERE last_seen >= ?
              AND (price IS NULL OR (price >= ? AND price <= ?))
            ORDER BY CASE WHEN listing_date IS NULL THEN 1 ELSE 0 END, listing_date DESC, id
            """,
            (cutoff, price_min, price_max),
        ).fetchall()

        # Exclude listings that are female-only or have roommates
        def _excluded(r):
            keys = r.keys()
            gender_val = r["gender_preference"] if "gender_preference" in keys else None
            gender = (gender_val or "").strip().lower()
            if gender == "female":
                return True
            hrm = r["has_roommates"] if "has_roommates" in keys else None
            if hrm is not None and hrm != 0:
                return True
            return False

        rows = [r for r in rows if not _excluded(r)]

        run = get_run_status(conn)
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        html_parts = [
            "<!DOCTYPE html>",
            "<html lang=\"en\">",
            "<head>",
            "  <meta charset=\"utf-8\">",
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
            "  <title>Utah Valley Rentals</title>",
            "  <style>",
            "    .listings table { border-collapse: collapse; font-size: 1em; }",
            "    .listings th, .listings td { border: 1px solid #ccc; padding: 0.25em 0.5em; text-align: left; }",
            "    .listings th { background: #f5f5f5; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <h1>Utah Valley Rentals</h1>",
        ]

        html_parts.append("  <section class=\"run-status\" aria-label=\"Run status\">")
        html_parts.append("    <h2>Run status</h2>")
        if run is None:
            html_parts.append(
                "    <p>No run recorded yet. Run <code>scrape.py</code>, "
                "<code>scrape_download.py</code>, and <code>main.py</code> first.</p>"
            )
        else:
            success_str = "success" if run["success"] else "failure"
            html_parts.append(
                f"    <p><strong>Last run:</strong> {_format_run_ts(run['last_run_ts'])} ({success_str})</p>"
            )
            html_parts.append("    <ul>")
            html_parts.append(f"      <li>Scraped: {run['scraped']}</li>")
            html_parts.append(f"      <li>Thrown: {run['thrown']}</li>")
            html_parts.append(f"      <li>Duplicate: {run['duplicate']}</li>")
            html_parts.append(f"      <li>Added: {run['added']}</li>")
            html_parts.append(f"      <li>Total in DB: {run['total_count']}</li>")
            html_parts.append(f"      <li>New this run: {run['new_count']}</li>")
            html_parts.append(f"      <li>Updated this run: {run['updated_count']}</li>")
            html_parts.append(f"      <li>LLM processed: {run['llm_processed']}</li>")
            html_parts.append(f"      <li>Displayed: {run['displayed']}</li>")
            html_parts.append("    </ul>")
        html_parts.append("  </section>")

        html_parts.append("  <section class=\"listings\" aria-label=\"Listings\">")
        html_parts.append("    <h2>Listings</h2>")
        if not rows:
            html_parts.append("    <p>No listings in range (price, 30-day window, and exclude female-only / has-roommates).</p>")
        else:
            html_parts.append("    <table><thead><tr>")
            html_parts.append("      <th>Title</th><th>Price</th><th>Beds</th><th>Baths</th>")
            html_parts.append("      <th>Listing date</th>")
            html_parts.append("      <th>In-unit W/D</th><th>Utilities</th><th>Util cost</th><th>Lease</th>")
            html_parts.append("    </tr></thead><tbody>")
            for r in rows:
                title = (r["title"] or "No title").replace("<", "&lt;").replace(">", "&gt;")
                link = (r["link"] or "#").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                price_str = f"${r['price']:.0f}" if r["price"] is not None else "—"
                beds_str = str(r["beds"]) if r["beds"] is not None else "—"
                baths_str = str(r["baths"]) if r["baths"] is not None else "—"
                listing_date_str = _format_listing_date(r["listing_date"]) or "—"

                html_parts.append("      <tr>")
                html_parts.append(f"        <td><a href=\"{link}\" rel=\"noopener noreferrer\">{title}</a></td>")
                html_parts.append(f"        <td>{price_str}</td><td>{beds_str}</td><td>{baths_str}</td>")
                html_parts.append(f"        <td>{listing_date_str}</td>")
                # Extraction-plan columns (in_unit_washer_dryer, has_roommates, etc.)
                # sqlite3.Row has no .get(); use key check and [] for optional columns.
                keys = r.keys()
                iuw = r["in_unit_washer_dryer"] if "in_unit_washer_dryer" in keys else None
                in_unit_wd = "—" if iuw is None else ("Yes" if iuw else "No")
                def _cell(key):
                    v = r[key] if key in keys else None
                    return (str(v).strip() if v is not None and str(v).strip() else "—")

                util_inc = _cell("utilities_included")
                util_cost = _cell("non_included_utilities_cost")
                lease = _cell("lease_length")
                if util_inc != "—":
                    util_inc = _escape_html(util_inc)
                if util_cost != "—":
                    util_cost = _escape_html(util_cost)
                if lease != "—":
                    lease = _escape_html(lease)
                html_parts.append(
                    f"        <td>{in_unit_wd}</td>"
                    f"<td>{util_inc}</td><td>{util_cost}</td><td>{lease}</td>"
                )
                html_parts.append("      </tr>")
            html_parts.append("    </tbody></table>")
        html_parts.append("  </section>")

        html_parts.append("</body>")
        html_parts.append("</html>")

        out_path = Path(output_dir) / "index.html"
        out_path.write_text("\n".join(html_parts), encoding="utf-8")

        update_run_status_after_build_page(conn, displayed=len(rows))
    finally:
        conn.close()


if __name__ == "__main__":
    build_page()

