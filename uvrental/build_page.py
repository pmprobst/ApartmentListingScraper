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
                address_raw,
                first_seen,
                last_seen,
                listing_date,
                washer_dryer,
                renter_paid_fees,
                availability,
                pet_policy,
                roommates
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
                washer_dryer = (r["washer_dryer"] or "").strip() if r["washer_dryer"] else ""
                availability = (r["availability"] or "").strip() if r["availability"] else ""
                pet_policy = (r["pet_policy"] or "").strip() if r["pet_policy"] else ""
                roommates = (r["roommates"] or "").strip() if r["roommates"] else ""

                renter_paid_fees_display = ""
                raw_fees = r["renter_paid_fees"]
                if raw_fees:
                    try:
                        parsed = json.loads(raw_fees)
                    except (TypeError, json.JSONDecodeError):
                        parsed = None
                    if isinstance(parsed, list):
                        renter_paid_fees_display = ", ".join(str(x) for x in parsed)
                    else:
                        renter_paid_fees_display = str(raw_fees)

                listing_date_str = _format_listing_date(r["listing_date"])
                html_parts.append("      <li>")
                html_parts.append(f"        <a href=\"{link}\" rel=\"noopener noreferrer\">{title}</a>")
                html_parts.append(f"        — {price_str} | {beds_str} bed, {baths_str} bath")
                if addr:
                    html_parts.append(f"        | {addr}")
                if listing_date_str:
                    html_parts.append(f"        | Listed {listing_date_str}")
                llm_bits: list[str] = []
                if washer_dryer:
                    llm_bits.append(f"Washer/dryer: {washer_dryer}")
                if pet_policy:
                    llm_bits.append(f"Pets: {pet_policy}")
                if availability:
                    llm_bits.append(f"Availability: {availability}")
                if roommates:
                    llm_bits.append(f"Roommates: {roommates}")
                if renter_paid_fees_display:
                    llm_bits.append(f"Renter-paid: {renter_paid_fees_display}")
                if llm_bits:
                    llm_text = " | ".join(llm_bits)
                    llm_text = (
                        llm_text.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    html_parts.append(f"        <br><small>{llm_text}</small>")
                html_parts.append("      </li>")
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

