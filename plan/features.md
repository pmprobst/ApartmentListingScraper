# Desired Features

This document is the **source of truth** for what the Utah Valley Rental Skimmer must support. It is used to guide implementation and to evaluate whether the project is complete. See [reference.md](reference.md) for deduplication schema, config shape, and deliverables.

---

## Definitions (for evaluation)

- **New listing** – A listing seen for the first time this run; `first_seen` is set to this run.
- **Updated listing** – A listing that already existed in the DB; `last_seen` is updated this run.
- **Removed listing** – A listing that is **phased out 30 days after last being seen** (based on `last_seen`). Listings whose `last_seen` is more than 30 days ago are treated as removed: they must be **marked as removed** (e.g. `status` or `removed_at` column) or excluded from the webpage; the project may optionally delete such rows later.
- **Run status** – The record written after each pipeline run: last run timestamp, success/failure, and listing counts (see Feature 8).
- **Pipeline** – fetch (Bright Data → SQLite) → [price filter] → [Claude extraction for new listings only] → build_page (SQLite → static HTML). (Canonical order in § Price filter and LLM extraction below.)

---

## 1. Scheduled skimming

- The pipeline is run on a **schedule** defined in the GitHub Actions workflow. The schedule must run **every 6 to 24 hours** (e.g. cron every 6h, 12h, or 24h; exact interval is workflow-configurable within that range).
- Webpage updates are triggered **only** by this scheduled workflow (and optionally by push to main, if desired). There is **no** reliance on local cron or on a manual git push to refresh listing data; the app must work without either.

---

## 2. Multi-site support

- **Rollout order:** Facebook Marketplace first, then Zillow, then KSL, then Apartments.com (see [reference.md](reference.md)#target-data-sources-from-researchmd).
- **First source:** Facebook Marketplace via **Bright Data API** only.
- **Additional sources:** Each new site uses the **same** SQLite schema and upsert contract (one row per `(source, source_listing_id)`); each site has a distinct **source** value (e.g. `facebook_marketplace`, `zillow`, `ksl`, `apartments_com`). Adding a source means adding one fetch adapter that outputs the same listing shape. Prefer **Bright Data** when available for that site; otherwise use direct scraping in line with Feature 7.
- **Design criterion:** Adding a new source must not require changing the core schema or the contract for existing sources.

---

## 3. Configurable search criteria

- All of the following are **configurable** via the project’s config (TOML) and/or env; no hardcoded search parameters in production code.
- **Location** – Cities and/or zip codes in Utah Valley (e.g. Provo, Orem; config-driven).
- **Price** – Minimum and maximum rent (config keys e.g. `price_min`, `price_max`); both may be supported; at least `price_max` is required for the price filter (see “Price filter and LLM extraction” below).
- **Bedrooms / bathrooms** – Minimum (or exact) as supported by the data source API (e.g. Bright Data parameters).
- **Property type** – E.g. apartment, house, condo, townhouse; values and support depend on the source.
- **Optional** (config may include; not required for MVP): pet-related keywords, free-text keywords. When present, they are passed to the source (e.g. Bright Data) where supported.

---

## 4. Deduplication *(priority)*

- **Within a source:** The same listing is identified by **source listing ID** (e.g. Bright Data product ID, or stable hash of link). Exactly **one row per (source, source_listing_id)**; upsert on fetch, never duplicate.
- **Across sources:** The same physical property is detected via **normalized address** (lowercase, normalized street suffixes, no extra punctuation); when two rows share the same non-empty normalized address, they are merged or linked (e.g. `canonical_listing_id`) so the webpage can show one listing with “Also on Zillow, KSL.” Implemented in **Phase 0**.
- **Stable identity:** Each listing row has an internal **id** (e.g. INTEGER PRIMARY KEY) for stable URLs and joins. Full design: [reference.md#deduplication-and-sqlite-schema](reference.md#deduplication-and-sqlite-schema).

---

## 5. Persistence

- Listings are stored in **SQLite** (Python `sqlite3`) with at least: **first_seen** and **last_seen** timestamps (set on insert; last_seen updated on every re-seen).
- **New / updated / removed:** New = first_seen this run; updated = existing row with last_seen updated this run. **Removed:** A listing is phased out **30 days after last being seen** (`last_seen`); listings with `last_seen` older than 30 days must be **marked as removed** (e.g. `status` or `removed_at` column) or excluded from the webpage; the project may optionally delete such rows later (see [reference.md](reference.md)).
- The SQLite DB is stored in a **separate private repo** (or equivalent private store); it must **not** be committed to the **public** repo. See [reference.md](reference.md) and phase-3 for workflow details.

---

## 6. New-listing alerts

- **Scope:** Not required for MVP. If implemented, “new-listing alert” means: notify the user when one or more **new** listings appear that pass the **same match criteria** as the webpage (price range, location, and any other configured filters). Alerts must use the same criteria as the webpage; no separate filter set.
- **Delivery:** Mechanism is TBD (e.g. email, desktop notification, webhook).
- **Primary view** for the project remains the generated webpage; alerts are supplementary.

---

## 7. Respectful data acquisition

- **Bright Data:** Use the Bright Data API for every supported site (they handle compliance). No direct scraping for Facebook Marketplace.
- **Direct scraping (if added):** For any source not using Bright Data, the implementation must: **honor robots.txt**; apply **rate limits and backoff** (documented in code or config); and avoid violating the site’s stated terms of use. Rate limits and backoff must be explicit (e.g. delays, retry limits).

---

## 8. Output and interaction

- **Webpage**
  - **Format:** Static HTML generated from SQLite; optional CSS/JS. No server-side logic; must be servable by GitHub Pages.
  - **Hosting:** GitHub Pages. Content is updated after each successful (or partial) pipeline run.
  - **Run status on page:** The page must display a **run status** indicator with: **(1)** last run timestamp (human-readable), **(2)** success or failure, **(3)** total listing count, and **(4)** counts for **N new** and **M updated** (required; e.g. “N new, M updated” or equivalent). Optionally, run status may include **K removed** (count of listings marked removed or phased out).
- **Interaction**
- The app is run via **scripts** (e.g. `scrape.py`, `scrape_download.py`, `ingest_records.py`, `build_page.py`). Invocation: e.g. `python scrape.py`, `python scrape_download.py`, `python ingest_records.py`, `python build_page.py` (or equivalent). Scripts must be runnable **locally** (with env and config) and **in GitHub Actions**. No formal CLI framework and no long-running local HTTP server are required.

---

## Price filter and LLM extraction (Claude API)

- **Price filter:** The app applies a **configurable** price filter using at least **price_max** (and optionally **price_min**). Listings outside the configured range: **(a)** are not sent to the Claude API, and **(b)** must be **hidden from the webpage** (not shown at all). Only listings within the price range are shown on the page.
- **Claude API only on new, in-range listings:** The LLM extraction step runs **only** on listings that are **(a)** new this run and **(b)** within the configured price (and any other configured filters). Extraction must **not** be re-run on every listing on every run; only newly fetched listings that pass the filter get extracted; results are stored in SQLite (e.g. `extracted` column).
  The extraction logic may also use **price and bedroom count together as a heuristic** to infer roommate situations (for example, a 2+ bedroom listing under a configurable per-person price threshold is likely shared housing).
- **Prototype first:** The Claude extraction step must be **prototyped and validated in isolation** (Phase 2) before being wired into the main pipeline.

### Claude extraction schema (fields to extract)

- The extraction **schema** (the set of field names and expected types) must include **all** of the following. Each field is **optional** at runtime (null/absent if not mentioned or not extractable). Extracted data is stored in the listings table in a single **extracted** column as a JSON blob (see [reference.md](reference.md)).
- **Washer / dryer** – Included in unit vs hookups only vs not mentioned.
- **Renter-paid fees** – Utilities, trash, internet, parking, pet rent, etc. that the renter must pay in addition to rent.
- **Availability / contract start** – When the unit is available or lease starts (date or “ASAP”, “March”, etc.).
- **Pet policy** – Cats/dogs allowed, deposit, monthly pet rent, breed/weight limits.
- **Parking** – Included, assigned, garage, street only, or extra cost.
- **Lease length** – Month-to-month, 6 months, 12 months, or unspecified.
- **Deposit** – Amount and whether refundable; any “last month” requirement.
- **Application / admin fees** – One-time fees to apply or move in.
- **Furnished vs unfurnished** – Fully furnished, partial, or unfurnished.
- **Square footage** – If mentioned (nullable if not).
- **Roommates / layout** – Entire place vs room in shared unit; number of roommates.
- **Subletting** – Whether subletting is allowed.
- **Contact** – Landlord vs property manager; phone/email/message preference.
- **Move-in incentives** – First month free, reduced deposit, waived fee.
- **Amenities** – AC, dishwasher, storage, gym, pool, yard, laundry in building.
- **Restrictions** – Non-smoking, student-only, no parties, credit check, etc.
- **Location detail** – Neighborhood, cross streets, or “near BYU/UVU” if mentioned (when full address is not given).

**Pipeline (canonical order):** Bright Data → SQLite (upsert) → price filter → Claude API extraction (new listings only) → update SQLite (extracted) → build_page (incl. run status).
