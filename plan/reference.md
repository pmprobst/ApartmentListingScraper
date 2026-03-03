# Reference: Data sources, schema, config, deliverables, risks

Supporting material for the plan. See [plan.md](plan.md) and [features.md](features.md) for phases and features.

---

## Target Data Sources (from research.md)

**Rollout order:** Facebook Marketplace first, then the others.

1. **Facebook Marketplace** *(first)* – facebook.com/marketplace. Data via **Bright Data API**.
2. **Zillow** – zillow.com. Add in a later phase (Bright Data if available, else direct scraping).
3. **KSL Real Estate** – homes.ksl.com. Add in a later phase.
4. **Apartments.com** – apartments.com. Add in a later phase.

---

## Deduplication and SQLite schema

Deduplication is a priority. Use a **stable primary key**, **per-source business key**, and **normalized address** so the same listing is not stored twice (within a source or across sources).

### Identity and keys

- **`id` (INTEGER PRIMARY KEY)** – Internal surrogate key; auto-generated. Use for joins and for the webpage (stable URLs/bookmarks).
- **Per-source uniqueness** – Each listing from a given source is uniquely identified by **(source, source_listing_id)**:
  - **source** – e.g. `facebook_marketplace`, `zillow`, `ksl`, `apartments_com`.
  - **source_listing_id** – The provider’s stable ID (e.g. Bright Data product ID, Zillow listing ID). If the source has no ID, use a stable **hash of (link)** or **(title + normalized address)** as fallback.
- **Cross-source deduplication** – Use **normalized_address** to detect the same property on multiple sites:
  - **normalized_address** – Single string: lowercase, strip extra whitespace, normalize street suffixes (St/Street, Ave/Avenue, etc.), remove punctuation. Store in a column for matching across rows.
  - Optional: **address_hash** – Hash of `normalized_address` for indexing; keep `normalized_address` for display.
  - When a new row has the same `normalized_address` as an existing row (and address is not empty), treat as same property: **merge** into one row or **link** via **canonical_listing_id**. Display as one listing (e.g. “Also on Zillow, KSL”).

### Suggested table shape (listings)

- **id** – INTEGER PRIMARY KEY AUTOINCREMENT.
- **source** – TEXT NOT NULL.
- **source_listing_id** – TEXT NOT NULL.
- **normalized_address** – TEXT (nullable).
- **address_raw** – TEXT.
- **link** – TEXT NOT NULL.
- **title** – TEXT.
- **price** – INTEGER or REAL.
- **beds**, **baths** – INTEGER or REAL, nullable.
- **first_seen** – TEXT or INTEGER (set on first insert).
- **last_seen** – TEXT or INTEGER (updated every time we see this listing again).
- **extracted** – TEXT (JSON blob for Claude-extracted fields), nullable.
- **canonical_listing_id** – INTEGER NULL; optional FK for cross-source merge.
- **UNIQUE(source, source_listing_id)** so the same listing from the same source is upserted, not duplicated.

### Upsert and merge logic

1. **On fetch:** Compute `source_listing_id` (from product_id or link hash), `normalized_address` from address_raw (or empty if missing).
2. **Upsert by (source, source_listing_id):** INSERT or INSERT ... ON CONFLICT DO UPDATE. Update `last_seen` and changed fields; set `first_seen` only on insert.
3. **Cross-source (Phase 0):** If `normalized_address` is non-empty, look for another row with same `normalized_address` and different `source`. If found, set `canonical_listing_id` or merge; display as one listing.

### New vs updated vs removed

- **New** – Row just inserted (first_seen = this run).
- **Updated** – Row already existed; last_seen updated this run.
- **Removed** – A listing is **phased out 30 days after last being seen** (`last_seen`). Listings whose `last_seen` is more than 30 days ago must be **marked as removed** (e.g. add a `status` or `removed_at` column; schema is implementation-defined) or excluded from the webpage. Optional: delete such rows later. See [features.md](features.md).

#### Implementation: 30-day phased removal

1. **Schema:** Add an optional `removed_at` (TEXT/INTEGER timestamp) or `status` (e.g. `active` / `removed`) column to the listings table. If omitted, "removed" is implied by filtering on `last_seen` at read time.
2. **After each fetch run:** Compute the cutoff timestamp (e.g. now − 30 days). Either (a) **mark** rows with `last_seen` &lt; cutoff: `UPDATE listings SET removed_at = ? OR status = 'removed' WHERE last_seen < cutoff`, or (b) leave rows as-is and treat "removed" as a view (WHERE last_seen &gt;= cutoff) in queries.
3. **build_page and run_status:** Only include listings that are not removed (e.g. `removed_at IS NULL` or `last_seen >= cutoff`). Run status may optionally include count of listings marked removed or beyond the 30-day cutoff.
4. **Phase ownership:** Implement in **Phase 1** (run status and static webpage) so the first generated page only shows listings within the 30-day window and run_status can optionally report K removed.

---

## Config schema (define before implementing)

Define the full config in TOML before writing code. Suggested contents:

- **Search / sources:** Location, price max/min, bedrooms/bathrooms, category/keywords for Bright Data.
- **Bright Data:** Dataset ID, endpoint, source-specific options.
- **Claude API:** API key (via env/Secrets only), model name, timeout, which fields to extract.
- **Paths:** SQLite file path (workflow uses a **separate private repo** for the DB; config points to the path where the DB is checked out or stored in the runner), output directory for static site, config file path.
- **Run status:** Where to write last run timestamp and outcome (SQLite table or small status file).
- **Deduplication:** Address-normalization options (e.g. suffix mappings) in config if needed.

Example: `config_schema.toml` in repo root. No config loading implementation until this spec is committed.

---

## Notes for future features

- **Drive time to a central location:** Use **Google Distance Matrix API** to calculate drive time from each listing’s address to a user-defined point (e.g. work). Store and show on webpage; configurable origin and API key.

---

## Deliverables (summary)

| Item | Description |
|------|-------------|
| Research | research.md – top 4 rental sites for Utah Valley (done). |
| Plan | plan/ directory – features, phases, reference. |
| Config | Config schema (TOML) committed; search, price filter, Bright Data, Claude, paths, dedup options. |
| Data acquisition | Bright Data API for Facebook Marketplace first; then Zillow, KSL, Apartments.com. Output to SQLite. |
| Storage | SQLite with listings, timestamps, source, extracted fields. Stored in a **separate private repo** (not in the public repo). |
| Scheduler | GitHub Actions workflow; credentials via GitHub Secrets. |
| Webpage | Static HTML on GitHub Pages; run status indicator. |
| Claude API | Prototype separately first; then run only on new listings. API key in GitHub Secrets / env. |
| Scripts | `fetch.py`, `build_page.py`; run via GitHub Actions or locally. |
| Alerts | Optional; not required for MVP. |

---

## Fallback: AI browser or human-like access

If authentication or anti-bot measures make scraping impractical, use an **AI browser or extension** (e.g. **ChatGPT Atlas**) to access sites “as a human”: you log in; the AI uses that session. Good for one-off or single-site use. Limitations: scale/scheduling, structured data extraction, reliability, ToS. Use as fallback for specific sites when needed; prefer Bright Data or direct scraping where possible.

---

## Risks and considerations

- **Bright Data:** Paid service; use **GitHub Secrets** (e.g. `BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY` or `BRIGHTDATA_API_KEY`); never commit keys.
- **Terms of use:** For direct scraping later, honor robots.txt and rate limits. Facebook Marketplace covered by Bright Data.
- **Site changes:** Tolerate optional API fields; design parsers for easy updates and logging.
- **Rate limiting:** Follow Bright Data docs; use delays for any direct scraping.
- **Claude API:** Use **GitHub Secrets** (e.g. `ANTHROPIC_API_KEY`); never commit. Runs on any GitHub-hosted runner.
- **Run status on failure:** If a step fails, workflow can still run `build_page.py` with existing data and record "last run: failed" for observability.

Incremental order: **Phase 0** (Bright Data → SQLite) → **Phase 1** (run status + webpage) → **Phase 2** (config schema + Claude prototype) → **Phase 3** (Claude for new listings, other sites, GitHub Actions) → **Phase 4** (webpage polish) → **Phase 5** (robustness).
