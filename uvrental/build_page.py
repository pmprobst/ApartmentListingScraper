"""
Phase 1: Generate static HTML from SQLite listings and run_status.
Reads DB path, output path, and price filter from config (env override for local).
Applies 30-day window. See plan/phase-1.md and plan/features.md.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

from .config import get_db_path, get_output_dir, get_price_min, get_price_max, get_display_days
from .db import (
    get_connection,
    get_run_status,
    update_run_status_after_build_page,
)

load_dotenv()


def _cutoff_iso(days: int) -> str:
    """Return ISO timestamp for (now - days) in UTC."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
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
    db_path = get_db_path()
    output_dir = get_output_dir()
    price_max = get_price_max()
    price_min = get_price_min()
    display_days = get_display_days()
    cutoff = _cutoff_iso(display_days)
    log.info("Building page (output_dir=%s, display_days=%d, db_path=%s)", output_dir, display_days, db_path)

    try:
        conn = get_connection(db_path)
        try:
            total_in_db = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            log.info("Listings in DB: %d", total_in_db)

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

            after_filter = len(rows)
            log.info("Listings after date+price filter (last_seen>=%s): %d", cutoff, after_filter)

            # Exclude listings that are female-only, have roommates, or summer-only (no renewal option)
            def _excluded(r):
                keys = r.keys()
                gender_val = r["gender_preference"] if "gender_preference" in keys else None
                gender = (gender_val or "").strip().lower()
                if gender == "female":
                    return True
                hrm = r["has_roommates"] if "has_roommates" in keys else None
                if hrm is not None and hrm != 0:
                    return True
                lease = (r["lease_length"] or "").strip()
                if lease == "summer":
                    return True  # summer-only without option to renew
                return False

            rows = [r for r in rows if not _excluded(r)]
            log.info("Listings after exclusions (displayed): %d", len(rows))

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

            # Only show the last run timestamp under the title.
            if run is None:
                html_parts.append(
                    f"  <p><strong>Last run:</strong> {_format_run_ts(None)}</p>"
                )
            else:
                success_str = "success" if run["success"] else "failure"
                html_parts.append(
                    f"  <p><strong>Last run:</strong> {_format_run_ts(run['last_run_ts'])} ({success_str})</p>"
                )

            # Listings table (no extra headings or run-status bullets).
            html_parts.append("  <section class=\"listings\" aria-label=\"Listings\">")
            if not rows:
                html_parts.append(
                    "    <p>No listings in range (price, 30-day window; excludes female-only, has-roommates, summer-only).</p>"
                )
            else:
                html_parts.append("    <table><thead><tr>")
                html_parts.append("      <th>Title</th><th>Price</th><th>Beds</th><th>Baths</th>")
                html_parts.append("      <th>Listing date</th>")
                html_parts.append(
                    "      <th>In-unit W/D</th><th>Utilities</th><th>Util cost</th><th>Lease</th>"
                )
                html_parts.append("    </tr></thead><tbody>")
                for r in rows:
                    title = (r["title"] or "No title").replace("<", "&lt;").replace(">", "&gt;")
                    link = (
                        (r["link"] or "#")
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    price_str = f"${r['price']:.0f}" if r["price"] is not None else "—"
                    beds_str = str(r["beds"]) if r["beds"] is not None else "—"
                    baths_str = str(r["baths"]) if r["baths"] is not None else "—"
                    listing_date_str = _format_listing_date(r["listing_date"]) or "—"

                    html_parts.append("      <tr>")
                    html_parts.append(
                        f"        <td><a href=\"{link}\" rel=\"noopener noreferrer\">{title}</a></td>"
                    )
                    html_parts.append(
                        f"        <td>{price_str}</td><td>{beds_str}</td><td>{baths_str}</td>"
                    )
                    html_parts.append(f"        <td>{listing_date_str}</td>")
                    keys = r.keys()
                    iuw = (
                        r["in_unit_washer_dryer"] if "in_unit_washer_dryer" in keys else None
                    )
                    in_unit_wd = "—" if iuw is None else ("Yes" if iuw else "No")

                    def _cell(key):
                        v = r[key] if key in keys else None
                        return str(v).strip() if v is not None and str(v).strip() else "—"

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
    except Exception as e:
        log.exception("build_page failed: %s", e)
        raise


if __name__ == "__main__":
    build_page()

