# Desired Features

All features the Utah Valley Rental Skimmer should support. See [reference.md](reference.md) for deduplication schema, config, and deliverables.

---

## 1. Scheduled skimming

- **GitHub Actions** runs the pipeline on a schedule (e.g. every 12 hours) to fetch new/updated listings, run Claude API extraction on new listings only, and update the webpage. No local cron or manual git push.

## 2. Multi-site support

- Start with **Facebook Marketplace** (Bright Data API). Then add Zillow, KSL, Apartments.com; design so adding each new source is straightforward (Bright Data if available, else direct scraping).

## 3. Configurable search criteria

- Location (cities/zip codes in Utah Valley), price range, bedrooms/bathrooms, property type (apartment, house, etc.), and optionally pet policy or keywords.

## 4. Deduplication *(priority)*

- Detect the same listing within a source (by source listing ID) and across sources (by normalized address). Use a stable **id/key** and **normalized address** in SQLite. Full design: [reference.md#deduplication-and-sqlite-schema](reference.md#deduplication-and-sqlite-schema).

## 5. Persistence

- Store listings in **SQLite** (Python `sqlite3`) with first-seen and last-seen timestamps to track new vs. updated vs. removed. DB lives on the **data/** branch (not main).

## 6. New-listing alerts

- Optional: notify when new listings match criteria (e.g. email or desktop notification). Primary view is the generated webpage.

## 7. Respectful data acquisition

- Use Bright Data API for supported sites (they handle compliance). For any direct scraping added later, honor robots.txt, rate limits, and terms of use.

## 8. Output and interaction

- **Webpage:** Static HTML (and optional CSS/JS) generated from SQLite, hosted on GitHub (GitHub Pages). Updated after each workflow run. Include a **run status** indicator (last run time, success/failure, listing count) for simple observability from day one.
- **Interaction:** Run the app via **scripts** (e.g. `fetch.py`, `build_page.py`); no formal CLI or local server required.

---

## Price filter and LLM extraction (Claude API)

After the Bright Data API pulls in data, the app will:

1. **Filter by price** – Keep only new or updated listings that match pre-set price criteria (e.g. **below $1,200**; configurable in config).
2. **Claude API extraction only on new listings** – Run the LLM **only on listings that are new and within the parameters** (e.g. new + price < $1,200). Do not re-run extraction on every listing every time; newly fetched listings that pass the filter get extracted via the Claude API, results stored in SQLite.
3. **Prototype Claude extraction separately** – Before building the full pipeline, prototype the Claude API extraction step in isolation; only then wire it into the main pipeline.

### Claude extraction schema (fields to extract)

Include all of the following in the Claude extraction schema (stored in SQLite):

- **Washer / dryer** – Included in unit vs hookups only vs not mentioned.
- **Renter-paid fees** – Utilities, trash, internet, parking, pet rent, etc. that the renter must pay in addition to rent.
- **Availability / contract start** – When the unit is available or when the lease starts (date or "ASAP", "March", etc.).
- **Pet policy** – Cats/dogs allowed, deposit, monthly pet rent, breed/weight limits.
- **Parking** – Included, assigned, garage, street only, or extra cost.
- **Lease length** – Month-to-month, 6 months, 12 months, or unspecified.
- **Deposit** – Amount and whether refundable; any "last month" requirement.
- **Application / admin fees** – One-time fees to apply or move in.
- **Furnished vs unfurnished** – Fully furnished, partial, or unfurnished.
- **Square footage** – If mentioned (helps compare value).
- **Roommates / layout** – Entire place vs room in shared unit; number of roommates.
- **Subletting** – Whether subletting is allowed (matters for students/short stays).
- **Contact** – Landlord vs property manager; phone/email/message preference.
- **Move-in incentives** – First month free, reduced deposit, waived fee.
- **Amenities** – AC, dishwasher, storage, gym, pool, yard, laundry in building.
- **Restrictions** – Non-smoking, student-only, no parties, credit check, etc.
- **Location detail** – Neighborhood, cross streets, or "near BYU/UVU" if mentioned (when full address is not given).

Pipeline: **Bright Data → SQLite → price filter (e.g. < $1,200) → Claude API extraction (new listings only) → update SQLite → build_page (incl. run status).**
