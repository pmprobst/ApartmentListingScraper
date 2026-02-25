# High-Level Plan: Utah Valley Rental Skimmer

This document outlines a high-level plan to build an application that regularly skims online rental markets in Utah Valley to identify potential opportunities (apartments and houses for rent).

---

## Goal

- **Input:** Target area = Utah Valley (e.g., Provo, Orem, and nearby cities).
- **Output:** A regularly updated view of rental opportunities from the top listing sites, with filtering and notification so you can act on new or matching listings.

---

## Target Data Sources (from research.md)

1. **Zillow** – zillow.com (apartments + houses, daily updates).
2. **KSL Real Estate** – homes.ksl.com (Utah-focused rentals).
3. **Apartments.com** – apartments.com (apartments + some houses, strong filters).
4. **Facebook Marketplace** – facebook.com/marketplace (local listings, private landlords, rooms/sublets; login may be required for scraping).

---

## Desired Features

1. **Scheduled skimming**  
   - Run on a schedule (e.g., daily or every few hours) to fetch new/updated listings.

2. **Multi-site support**  
   - Support at least the top 4 sites (Zillow, KSL, Apartments.com, Facebook Marketplace); design so adding Rentler or others later is straightforward.

3. **Configurable search criteria**  
   - Location (cities/zip codes in Utah Valley), price range, bedrooms/bathrooms, property type (apartment, house, etc.), and optionally pet policy or keywords.

4. **Deduplication**  
   - Detect the same listing across sites (e.g., by address or listing ID) to avoid duplicates and merge data when possible.

5. **Persistence**  
   - Store listings in a simple database or structured files (e.g., SQLite or JSON) with first-seen and last-seen timestamps to track new vs. updated vs. removed.

6. **New-listing alerts**  
   - Notify when new listings match criteria (e.g., email, desktop notification, or a simple dashboard). Optional: “saved search” per set of criteria.

7. **Respectful scraping**  
   - Honor robots.txt, use reasonable rate limits and delays, and follow each site’s terms of use. Prefer official APIs if available (e.g., some sites offer partner or RSS feeds).

8. **Simple UI or CLI**  
   - At minimum: CLI to run a scrape and view recent/new listings. Optional: minimal web dashboard to browse results and manage criteria.

---

## Implementation Outline

### Phase 1: Foundation

- **Tech choices:** Pick a language and stack (e.g., Python + requests/BeautifulSoup or Playwright for JS-heavy sites; or Node.js if preferred). Use SQLite (or similar) for storage.
- **Config:** Define search criteria in a config file (cities, price range, beds/baths, etc.).
- **One-site scraper:** Implement a single scraper for one of the four sites (e.g., Zillow or KSL) that:
  - Builds search URLs (or uses API) from config.
  - Fetches listing list and key fields (title, link, price, beds, baths, address, source).
  - Saves to DB with first-seen/last-seen and source.
- **Deduplication (basic):** Normalize address or external ID per listing; mark duplicates so the same property isn’t counted twice.

### Phase 2: Multi-site and scheduling

- **Scrapers for the other three sites:** Reuse the same storage schema and add scrapers for KSL, Apartments.com, and Facebook Marketplace. Share parsing and persistence logic where possible. (Note: Facebook Marketplace may require authenticated sessions or browser automation due to login; handle separately if needed.)
- **Scheduler:** Use cron (or a simple in-process scheduler) to run the full scrape on a set interval (e.g., daily).
- **New vs. updated:** On each run, compare with stored listings; tag “new” for first-seen in this run and “updated” if details changed.

### Phase 3: Alerts and usability

- **Alerts:** Implement at least one channel (e.g., email via SMTP or a simple webhook) for “new listings matching your criteria.”
- **CLI:** Commands such as `run scrape`, `list recent`, `list new`, and optionally `list by-site`.
- **Optional dashboard:** Simple local web page to filter and browse stored listings and manage saved criteria.

### Phase 4: Robustness and polish

- **Error handling and logging:** Log failures per site; retry with backoff; don’t lose data if one site is down.
- **Legal/compliance:** Document and enforce robots.txt and rate limits; consider moving to official APIs or feeds where offered.
- **Optional:** Lightweight “listing diff” report (new/removed/updated) per run for easy scanning.

---

## Deliverables (summary)

| Item | Description |
|------|-------------|
| Research | research.md – top 4 rental sites for Utah Valley (done). |
| Plan | plan.md – this high-level plan and feature set. |
| Config | Search criteria (location, price, beds, etc.) in a config file. |
| Scrapers | One module per site (Zillow, KSL, Apartments.com, Facebook Marketplace) with shared storage. |
| Storage | SQLite (or equivalent) with listings, timestamps, and source. |
| Scheduler | Automated runs (e.g., cron or in-app scheduler). |
| Alerts | Notifications for new matching listings. |
| CLI / UI | CLI at minimum; optional web dashboard. |

---

## Risks and considerations

- **Terms of use:** Each site may restrict scraping; implement conservatively and switch to APIs/feeds if available. Facebook Marketplace in particular has strict anti-scraping policies and typically requires login.
- **Site changes:** Listing page structure can change; design parsers to be easy to update and add logging for parse failures.
- **Rate limiting:** Use delays and polite concurrency to avoid blocks or bans.
- **Facebook Marketplace:** May require authenticated sessions or browser automation (e.g., Playwright); treat as a separate integration path if needed.

This plan is intended to be implemented incrementally: get one site working end-to-end, then add the others and scheduling, then alerts and any UI.
