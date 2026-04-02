## Data overview and useful queries

This document summarizes key data questions about the Utah Valley Rental Skimmer and provides ready-to-run SQL/CLI snippets you can execute against your **private** `listings.db` to generate numbers and examples for posts or analysis.

### 1. Total listings vs. displayed listings

- **Definitions**
  - **Total listings in DB**: all rows in the `listings` table, across all time and sources.
  - **Displayed listings**: rows that survive the 30‑day window, price filter, and exclusion rules applied in `uvrental.build_page`.

- **Where these values are maintained**
  - `uvrental.ingest.ingest_records` updates `run_status.total_count` after each ingest:

    ```sql
    SELECT COUNT(*) FROM listings;
    ```
    Output:
    ```
    815
    ```

  - `uvrental.build_page.build_page` logs:
    - `total_in_db` – `SELECT COUNT(*) FROM listings`
    - `after_filter` – number of rows after **date + price** filter
    - `displayed` – number of rows after additional **gender/roommates/lease** exclusions; this is written to `run_status.displayed`.

- **SQL to inspect current counts**

  ```sql
  -- From run_status (what the last pipeline run saw)
  SELECT
    total_count   AS total_listings,
    displayed     AS listings_displayed_last_build,
    scraped,
    thrown,
    duplicate,
    added,
    new_count,
    updated_count,
    llm_processed
  FROM run_status
  WHERE id = 1;
  ```
  Output:
  ```
  | total_listings | listings_displayed_last_build | scraped | thrown | duplicate | added | new_count |updated_count | llm_processed |
  | 815            | 212                           | 101     | 1      | 48        | 52    | 52        | 48           | 44            |
  ```


  -- Recompute from listings with current filters
  -- (use the same cutoff and price range as build_page)

  -- 1) Basic totals
  ```sql
  SELECT COUNT(*) AS total_listings FROM listings;
  ```
   Output:
  ```
  815
  ```

  -- 2) After date + price filter, matching build_page:
  --    last_seen >= cutoff AND price within [price_min, price_max] or NULL.
  .param set :cutoff     '2025-01-01T00:00:00Z'   -- replace with dynamic cutoff
  .param set :price_min  0                        -- match config or env
  .param set :price_max  1200                     -- match config or env

  ```sql
  SELECT COUNT(*) AS listings_after_date_price
  FROM listings
  WHERE last_seen >= :cutoff
    AND (price IS NULL OR (price BETWEEN :price_min AND :price_max));
  ```
  Output:
  ```
  | listings_after_date_price |
  | 0                         |
  ```

### 2. HTML table columns vs. full schema

- **Listings schema** (`uvrental.db.init_schema`):
  - `id`, `source`, `source_listing_id`, `normalized_address`, `link`, `title`,
    `price`, `beds`, `baths`, `first_seen`, `last_seen`, `listing_date`,
    `description`, `in_unit_washer_dryer`, `has_roommates`, `gender_preference`,
    `utilities_included`, `non_included_utilities_cost`, `lease_length`,
    `llm_extraction_status`, `canonical_listing_id`.

- **Columns actually displayed in the HTML table** (`uvrental.build_page.build_page`):
  1. **Title** (rendered as a link; uses `title` and `link`)
  2. **Price** (`price`, formatted as `$1234` or `—`)
  3. **Beds** (`beds`)
  4. **Baths** (`baths`)
  5. **Listing date** (`listing_date`, date‑only formatting)
  6. **In‑unit W/D** (`in_unit_washer_dryer`, shown as `Yes` / `No` / `—`)
  7. **Utilities** (`utilities_included`)
  8. **Util cost** (`non_included_utilities_cost`)
  9. **Lease** (`lease_length`)

Everything else (e.g., `normalized_address`, `first_seen`, `last_seen`, `canonical_listing_id`) is stored in SQLite but not rendered in the final HTML table.

### 3. Missingness metrics for extracted fields

Extraction populates:

- `beds`, `baths`
- `in_unit_washer_dryer`
- `has_roommates`
- `gender_preference`
- `utilities_included`
- `non_included_utilities_cost`
- `lease_length`
- `llm_extraction_status` (`NULL` / `'pending'` / `'done'`)

#### 3.1 Overall missingness for each field

Run against `listings.db`:

```sql
SELECT
  COUNT(*) AS n,
  SUM(CASE WHEN beds IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS p_beds_non_null,
  SUM(CASE WHEN baths IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS p_baths_non_null,
  SUM(CASE WHEN in_unit_washer_dryer IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS p_iuwd_non_null,
  SUM(CASE WHEN has_roommates IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS p_roommates_non_null,
  SUM(CASE WHEN gender_preference IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS p_gender_non_null,
  SUM(CASE WHEN utilities_included IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS p_utils_inc_non_null,
  SUM(CASE WHEN non_included_utilities_cost IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS p_util_cost_non_null,
  SUM(CASE WHEN lease_length IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS p_lease_non_null
FROM listings;
```
Output:
```
|  n  |  p_beds_non_null  | p_baths_non_null  |  p_iuwd_non_null  | p_roommates_non_null | p_gender_non_null | p_utils_inc_non_null | p_util_cost_non_null | p_lease_non_null  |
| 815 | 0.619631901840491 | 0.623312883435583 | 0.409815950920245 | 0.710429447852761    | 0.862576687116564 | 0.192638036809816    | 0.288343558282209    | 0.402453987730061 |
```

Use this for a quick “coverage by field” table in a blog or notebook.

#### 3.2 Regex‑only vs. Claude (Stage 1 vs Stage 2)

`llm_extraction_status` meaning:

- `NULL` – no extraction yet (no description or not processed).
- `'pending'` – Stage 1 (regex) ran and found gaps; queued for Claude.
- `'done'` – extraction finished (either regex alone or regex + Claude); final values in the DB.

You can look at counts and completeness by status:

```sql
SELECT
  llm_extraction_status,
  COUNT(*) AS n,
  SUM(CASE WHEN beds IS NOT NULL THEN 1 ELSE 0 END)                AS filled_beds,
  SUM(CASE WHEN baths IS NOT NULL THEN 1 ELSE 0 END)               AS filled_baths,
  SUM(CASE WHEN in_unit_washer_dryer IS NOT NULL THEN 1 ELSE 0 END) AS filled_iuwd,
  SUM(CASE WHEN has_roommates IS NOT NULL THEN 1 ELSE 0 END)       AS filled_roommates,
  SUM(CASE WHEN utilities_included IS NOT NULL THEN 1 ELSE 0 END)  AS filled_utils_inc,
  SUM(CASE WHEN non_included_utilities_cost IS NOT NULL THEN 1 ELSE 0 END) AS filled_util_cost,
  SUM(CASE WHEN lease_length IS NOT NULL THEN 1 ELSE 0 END)        AS filled_lease
FROM listings
GROUP BY llm_extraction_status;
```
Output:
```
| llm_extraction_status |  n  | filled_beds | filled_baths | filled_iuwd | filled_roommates | filled_utils_inc | filled_util_cost | filled_lease |
|                       | 112 | 0           | 0            | 0           | 0                | 0                | 0                | 0            |
| done                  | 703 | 505         | 508          | 334         | 579              | 157              | 235              | 328          |
```

### 4. Deduplication and `canonical_listing_id`

There are two notions of duplicates:

- **Ingest‑time duplicates** (same source + `source_listing_id`):
  - Counted as `duplicate` in `run_status` during ingest.
  - `uvrental.ingest.ingest_records` checks whether the (source, `source_listing_id`) pair already exists and increments `duplicate` vs `added`.

- **Cross‑source deduplication** via `normalized_address` and `canonical_listing_id`:
  - During `upsert_listing`, if `normalized_address` is non‑empty, the code looks for another row with the same `normalized_address` but a different `source`.
  - If found, the new row’s `canonical_listing_id` is set to the existing row’s `id`.

#### 4.1 How many duplicates have been grouped

```sql
-- Rows that are considered duplicates of some canonical listing
SELECT
  COUNT(*) AS rows_with_canonical
FROM listings
WHERE canonical_listing_id IS NOT NULL;
```
Output:
```
| rows_with_canonical |
| 0                   |
```

### 5. Regex vs. Claude extraction behavior

- **Stage 1: regex (`uvrental.extraction_regex.run_stage1`)**
  - Normalizes text (removes emoji, fixes whitespace/typos).
  - Extracts:
    - `bedrooms` / `bathrooms`
    - `in_unit_washer_dryer` (`True` = in‑unit; `False` = building/shared; `None` = unmentioned)
    - `has_roommates` (True/False/None)
    - `gender_preference` (`"male"`, `"female"`, `"any"`)
    - `utilities_included` (`"all"` or list or `None`)
    - `non_included_utilities_cost` (short string like `"$80–100/month"`)
    - `lease_length` (`"summer"`, `"summer w/ option to review"`, `"fall/winter"`, or None)
  - Tracks `_confident` and `_missing_fields`; if any field is not confidently filled, `_needs_llm = True`.

- **Stage 2: Claude (`uvrental.extraction_claude` + `uvrental.extraction_pipeline`)**
  - Called for listings where `_needs_llm` is true; rows are marked `llm_extraction_status = 'pending'` after Stage 1.
  - Claude gets the title, description, and all Stage 1 values as **ground truth pre‑fills** and returns final values for all 8 fields.
  - `llm_result_to_db_values` converts these into DB updates and sets `llm_extraction_status = 'done'`.

For a narrative example in a blog, you can:

1. Query a few listings with `llm_extraction_status = 'done'`.
2. Recompute `run_stage1` on their text in a notebook to show:
   - Stage 1 output (`bedrooms`, `bathrooms`, etc., plus `_missing_fields`).
   - Final DB row (after Claude).
3. Highlight specific cases where regex was uncertain (e.g., utilities/lease) and Claude filled in or left null.

### 6. Address normalization (`normalize_address`)

Implementation (`uvrental.db.normalize_address`):

- Lowercases the string.
- Strips leading/trailing whitespace.
- Removes all punctuation (`[^\w\s]`).
- Collapses multiple spaces into one.
- Splits into tokens and normalizes street suffixes via `SUFFIX_MAP`, e.g.:
  - `st`, `street` → `street`
  - `ave`, `av`, `avenue` → `avenue`
  - `blvd` → `boulevard`, `dr` → `drive`, `ln` → `lane`, `rd` → `road`, etc.

**Examples (approximate):**

- `"123 N 100 E St., Provo, UT"` → `"123 n 100 e street provo ut"`
- `"456 W 200 North, Orem, UT 84057"` → `"456 w 200 north orem ut 84057"`

This normalized string is used to find potential cross‑source duplicates; when another listing from a different source shares the same normalized address, `canonical_listing_id` on the new row points back to the existing row’s `id`.

### 7. Raw Bright Data JSON vs. cleaned DB row

Ingest path (`uvrental.ingest.normalize_record` and `ingest_records`):

- Handles differing shapes of Bright Data payload (list vs. `{data: [...]}`, `results`, etc.).
- Derives:
  - `source_listing_id` from `product_id`, `listing_id`, `id`, or a hash of `link` / `title`.
  - A canonical Facebook Marketplace URL using `_numeric_listing_id` when possible.
  - `price`, `beds`, `baths` by normalizing common field variants (`price`, `final_price`, `bedrooms`, etc.).
  - `address_raw` from `location` (string or object) or fallback fields (`address`, `city`, `location_name`).
  - `description` from `seller_description` or `description`.

**Illustrative raw record** (shape inferred from code; not a real snapshot):

```json
{
  "product_id": "1000000000000001",
  "title": "2BR Apartment Near UVU",
  "url": "https://www.facebook.com/marketplace/item/1000000000000001",
  "price": "$1,100",
  "location": {
    "city": "Orem",
    "state": "UT",
    "address": "123 N 100 E",
    "street": "123 N 100 E",
    "region": "Utah County"
  },
  "bedrooms": 2,
  "bathrooms": 1,
  "seller_description": "2 bed / 1 bath near UVU. Men's contract. Utilities about $80/mo."
}
```

**Normalized record passed to `upsert_listing`:**

```text
source_listing_id: "1000000000000001"
link:              "https://www.facebook.com/marketplace/item/1000000000000001/"
title:             "2BR Apartment Near UVU"
price:             1100.0
beds:              2.0
baths:             1.0
address_raw:       "Orem, UT, 123 N 100 E, 123 N 100 E, Utah County"
listing_date:      NULL (if not provided)
description:       "2 bed / 1 bath near UVU. Men's contract. Utilities about $80/mo."
```

**Representative DB row after ingest + extraction** (schema‑level view):

```text
id:                          42                    -- auto
source:                      "facebook_marketplace"
source_listing_id:           "1000000000000001"
normalized_address:          "orem ut 123 n 100 e 123 n 100 e utah county"
link:                        "https://www.facebook.com/marketplace/item/1000000000000001/"
title:                       "2BR Apartment Near UVU"
price:                       1100.0
beds:                        2.0
baths:                       1.0
first_seen:                  "2026-03-10T09:00:00Z"
last_seen:                   "2026-03-10T09:00:00Z"
listing_date:                NULL or ISO string if present
description:                 "...Men's contract. Utilities about $80/mo."
in_unit_washer_dryer:        0 / 1 / NULL   -- from regex/Claude
has_roommates:               1 / 0 / NULL
gender_preference:           "male" / "female" / "any"
utilities_included:          "all" or JSON list or NULL
non_included_utilities_cost: "$80/mo" or similar
lease_length:                "summer" / "fall/winter" / "summer w/ option to review" / NULL
llm_extraction_status:       "done" / "pending" / NULL
canonical_listing_id:        NULL or another listing.id if deduped
```

For a blog, you can pull a **real** before/after pair by:

1. Identifying a specific `id` in `listings`.
2. Finding the corresponding record in `snapshots/marketplace_snapshot_<snapshot_id>.json` by matching `product_id` / `listing_id` / URL.
3. Showing the raw JSON fragment next to the cleaned DB row from `sqlite3`.

### 8. Bright Data configuration for Provo/Orem

Configuration lives in `config.toml` / `config_schema.toml` and environment variables; `uvrental.brightdata.trigger_from_env` wires it into the trigger payload.

- **Key config fields**

  ```toml
  [search]
  location = "Provo"        # or "Provo, Orem"
  location_state = "UT"
  price_max = 1200
  price_min = 0
  category = "Apartment"

  [bright_data]
  dataset_id = "gd_lvt9iwuh6fbcwmx1a"
  ```

- **Trigger parameters**

  ```text
  city    = BRIGHTDATA_CITY    or [search].location
  keyword = BRIGHTDATA_KEYWORD or [search].category
  radius  = BRIGHTDATA_RADIUS_MILES or DEFAULT_RADIUS_MILES (20)
  ```

  The trigger payload sent to Bright Data is:

  ```json
  {
    "input": [
      {
        "keyword": "<category/keyword>",
        "city": "<location string>",
        "radius": <radius_miles>,
        "date_listed": ""
      }
    ]
  }
  ```

- **Recommended Provo/Orem setup**
  - In `config.toml`:

    ```toml
    [search]
    location = "Provo, Orem"
    location_state = "UT"
    category = "Apartment"
    ```

  - Or via env:
    - `BRIGHTDATA_CITY="Provo, Orem"`
    - `BRIGHTDATA_KEYWORD="Apartment"`
    - `BRIGHTDATA_RADIUS_MILES=20` (or similar)

This gives you a single place to document how the dataset is targeted geographically and what Bright Data query parameters are being used.

