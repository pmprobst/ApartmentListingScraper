"""
Phase 1: Generate static HTML from SQLite listings and run_status.
Reads DB path, output path, and price filter from env. Applies 30-day window.
See plan/phase-1.md and plan/features.md.
"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

from db import (
    get_connection,
    get_run_status,
    update_run_status_after_build_page,
)

load_dotenv()

# Env keys (optional with defaults)
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


def _is_clearly_utah(address_raw: str | None) -> bool:
    """
    Heuristic filter for Utah-only listings.

    - Returns True if the address clearly mentions Utah (\"Utah\" or state code UT).
    - Returns False otherwise (including empty/unknown or clearly non-US).

    This is intentionally strict: if we cannot see a clear Utah signal,
    we treat the listing as non-Utah and drop it.
    """
    if address_raw is None:
        return False
    s = address_raw.strip().lower()
    if not s:
        return False

    # Explicit Utah matches
    if "utah" in s:
        return True
    if ", ut" in s or s.endswith(" ut") or ", ut " in s or " ut " in s:
        return True

    return False


def _delete_non_utah_rows(conn) -> None:
    """
    Delete listings whose address is clearly outside Utah.

    This is a coarse cleanup step so that the DB and the rendered page
    stay focused on Utah Valley. It is safe to run on every build.
    """
    rows = conn.execute("SELECT id, address_raw FROM listings").fetchall()
    to_delete = [
        row["id"]
        for row in rows
        if not _is_clearly_utah(row["address_raw"])
    ]
    if not to_delete:
        return
    conn.executemany("DELETE FROM listings WHERE id = ?", [(i,) for i in to_delete])
    conn.commit()


def _format_run_ts(iso_ts: str | None) -> str:
    if not iso_ts:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(iso_ts)


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
        # Clean out listings that are clearly outside Utah before querying.
        _delete_non_utah_rows(conn)

        # Listings: within price range and within 30-day window
        # Include rows where price is NULL so we don't hide listings missing price
        rows = conn.execute(
            """
            SELECT id, source, source_listing_id, link, title, price, beds, baths,
                   address_raw, first_seen, last_seen
            FROM listings
            WHERE last_seen >= ?
              AND (price IS NULL OR (price >= ? AND price <= ?))
            ORDER BY last_seen DESC, id
            """,
            (cutoff, price_min, price_max),
        ).fetchall()

        run = get_run_status(conn)
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        html_parts = [
            "<!DOCTYPE html>",
            "<html lang=\"en\">",
            "<head>",
            "  <meta charset=\"utf-8\">",
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
            "  <title>Utah Valley Rentals</title>",
            "</head>",
            "<body>",
            "  <h1>Utah Valley Rentals</h1>",
        ]

        # Run status banner
        html_parts.append("  <section class=\"run-status\" aria-label=\"Run status\">")
        html_parts.append("    <h2>Run status</h2>")
        if run is None:
            html_parts.append("    <p>No run recorded yet. Run <code>fetch.py</code> first.</p>")
        else:
            success_str = "success" if run["success"] else "failure"
            html_parts.append(f"    <p><strong>Last run:</strong> {_format_run_ts(run['last_run_ts'])} ({success_str})</p>")
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

        # Listings
        html_parts.append("  <section class=\"listings\" aria-label=\"Listings\">")
        html_parts.append("    <h2>Listings</h2>")
        if not rows:
            html_parts.append("    <p>No listings in range (price and 30-day window).</p>")
        else:
            html_parts.append("    <ul>")
            for r in rows:
                title = (r["title"] or "No title").replace("<", "&lt;").replace(">", "&gt;")
                link = (r["link"] or "#").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                price_str = f"${r['price']:.0f}" if r["price"] is not None else "—"
                beds_str = str(r["beds"]) if r["beds"] is not None else "—"
                baths_str = str(r["baths"]) if r["baths"] is not None else "—"
                addr = (r["address_raw"] or "").replace("<", "&lt;").replace(">", "&gt;")
                html_parts.append(f"      <li>")
                html_parts.append(f"        <a href=\"{link}\" rel=\"noopener noreferrer\">{title}</a>")
                html_parts.append(f"        — {price_str} | {beds_str} bed, {baths_str} bath")
                if addr:
                    html_parts.append(f"        | {addr}")
                html_parts.append(f"      </li>")
            html_parts.append("    </ul>")
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
