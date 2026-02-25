# High-Level Plan: Utah Valley Rental Skimmer

This document outlines a high-level plan to build an application that regularly skims online rental markets in Utah Valley to identify potential opportunities (apartments and houses for rent).

---

## Goal

- **Input:** Target area = Utah Valley (e.g., Provo, Orem, and nearby cities).
- **Output:** A regularly updated webpage of rental opportunities from the top listing sites, sorted by user preference, with filtering and notification so you can act on new or matching listings.

---

## Target Data Sources (from research.md)

1. **Zillow** – zillow.com (apartments + houses, daily updates).
2. **KSL Real Estate** – homes.ksl.com (Utah-focused rentals).
3. **Apartments.com** – apartments.com (apartments + some houses, strong filters).
4. **Facebook Marketplace** – facebook.com/marketplace (local listings, private landlords, rooms/sublets; login may be required for scraping).

---

## API / feed options (research)

Research into official or semi-official programmatic access for each of the four sites. **Summary:** None of the four offer a public consumer API to search or read rental listings. Scraping (or the AI-browser fallback) remains the practical approach for a personal skimmer; APIs/feeds below are mostly for publishers, partners, or researchers.

### Zillow

- **No public read API for rental search.** Zillow has discontinued its legacy consumer-facing APIs (e.g. GetSearchResults / GetDeepSearchResults returned 410 Gone as of Feb 2021; ZTRAX and other free data APIs have also been phased out).
- **Rentals Feed Integrations** (zillowgroup.com/developers) – **Publisher-only.** Lets property management companies and software syndicate listings *to* the Zillow Rental Network via XML/MITS feeds. Not for reading or searching listings as a consumer. Requires approval from the Rentals Integrations team; contact rentalfeeds@zillow.com.
- **Lead API** – Delivers *lead* data (e.g. inquiries) from Zillow Rentals to CRMs via HTTP POST callbacks. For landlords/property managers receiving leads, not for discovering listings.
- **Bridge API** (via Bridge Interactive) – Zillow Group data including public records and Zestimates; limited to approved use cases, rate limits (e.g. 1,000 calls/day), and does not provide a general rental-search API.
- **Implication for this project:** Use scraping (or AI-browser fallback) for Zillow; no viable public API for reading rental listings.

### KSL Real Estate (homes.ksl.com)

- **No official developer API.** No public documentation for a KSL Real Estate or KSL Classifieds API for rental listings.
- **RSS / third-party feeds:** Some third-party tools (e.g. FeedSpot) can build RSS feeds from KSL *webpage* URLs (e.g. a search results URL). That’s screen-scraping or URL-based syndication, not an official KSL API. IFTTT and similar can consume such feeds (e.g. daily digest). Reliability and structure depend on the third party.
- **Rentler relationship:** KSL Real Estate surfaces some listings from Rentler (e.g. ksl.com/homes/index/rentler). Rentler itself does not publish a public developer API for searching its rental inventory.
- **Implication for this project:** Use scraping (or AI-browser fallback) for KSL; no official API. Optional: explore RSS-from-URL services for a specific KSL search URL as a lightweight supplement, with the understanding it’s not an official feed.

### Apartments.com

- **API exists but is not a public consumer search API.** api.apartments.com is intended for **authorized partners and property managers** who list on Apartments.com.
- **Authentication:** OAuth 2.0 (Resource Owner Password Credentials Grant). Credentials are not public; must be requested through Apartments.com customer service / your account rep.
- **Endpoints:** e.g. `GET api/listings` (listings for the *authenticated* user) and `GET api/listings?hqKey={hqKey}` (listings under a headquarters key). Used to manage *your* listings, reviews, and comments—not to search the full public catalog.
- **Integrations:** Apartments.com offers pre-built integrations and automated feeds for property management systems (Yardi, Entrata, RealPage, AppFolio, etc.) for *publishing* and updating listings.
- **Implication for this project:** As a renter/searching consumer, you cannot use the Apartments.com API to search all listings. Use scraping (or AI-browser fallback) for discovery.

### Facebook Marketplace

- **No public API for searching or reading Marketplace listings** for general developers. The **Seller API / Item API** (Graph API) is for *publishing* and managing *your* listings (partnership/approval required), not for reading the full Marketplace catalog.
- **Content Library API** – Meta provides a **Content Library and API** that can include **Facebook Marketplace** data (listings, etc.) for **eligible researchers**. Access is restricted to qualified academic or not-for-profit research institutions; applications are reviewed by ICPSR (e.g. 4–6 weeks). Data is typically analyzed in Meta’s designated environment (e.g. Virtual Data Enclave). Not intended for personal rental skimmers or commercial use.
- **Syndication to Marketplace:** Large-scale rental syndication is possible via business partnerships (e.g. Business Extension Services Partner inquiry form); again, for *publishing* listings, not reading them.
- **Implication for this project:** No viable API for a consumer to programmatically search Marketplace. Use scraping or the AI-browser fallback (e.g. Atlas) with a logged-in session; respect Meta’s terms and automation policies.

### Summary table

| Site                | Public search/read API? | Publisher / partner APIs or feeds?        | Practical approach for this app   |
|---------------------|-------------------------|-------------------------------------------|-----------------------------------|
| Zillow              | No (legacy APIs gone)   | Yes (feed in, lead API out; publisher-only) | Scraping or AI browser            |
| KSL Real Estate     | No                      | No official API; third-party RSS possible | Scraping or AI browser            |
| Apartments.com      | No                      | Yes (OAuth API for your listings only)    | Scraping or AI browser            |
| Facebook Marketplace| No                      | Seller API to publish; Content Library for research only | Scraping or AI browser            |

*Sources: Zillow Group Developers, Apartments.com API docs, Meta for Developers (Marketplace, Content Library), third-party reporting on Zillow API discontinuations, FeedSpot/IFTTT for KSL RSS options. Last checked 2025.*

---

## Desired Features

1. **Scheduled skimming**  
   - Run on a schedule (every  to fetch new/updated listings.

2. **Multi-site support**  
   - Support at least the top 4 sites (Zillow, KSL, Apartments.com, Facebook Marketplace); design so adding Rentler or others later is straightforward.

3. **Configurable search criteria**  
   - Location (cities/zip codes in Utah Valley), price range, bedrooms/bathrooms, property type (apartment, house, etc.), and optionally pet policy or keywords.

4. **Deduplication**  
   - Detect the same listing across sites (e.g., by address or listing ID) to avoid duplicates and merge data when possible. This feature is not a priority.

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

## Fallback: AI browser or human-like access

If authentication or anti-bot measures make traditional scraping impractical (e.g., Facebook Marketplace, or sites that require login to see listings), using an **AI browser or browser extension** (e.g., **ChatGPT Atlas**, or similar agent-style tools) to access sites “as a human” is a **viable fallback**, with trade-offs.

**Why it can work**

- **You** log in and accept cookies/consent in a real browser; the AI operates in that same session, so the site sees normal human-like traffic.
- Handles JS-heavy pages, login flows, and CAPTCHAs in a way that headless scrapers often cannot.
- Good for one-off or semi-manual runs: you trigger the agent (e.g., “search Utah Valley rentals on Marketplace and list the first 20”), and it navigates and can summarize or export what it sees.

**Limitations**

- **Scale and scheduling:** These tools are usually interactive. Running them unattended every few hours for all four sites may not be supported or reliable; better suited to “run when I need it” or a single problematic site (e.g., only Marketplace).
- **Structured data:** You still need a way to get listing data into your app (e.g., AI copies to clipboard/JSON, or an extension that scrapes the DOM and exports). That step may be manual or need a small integration.
- **Reliability:** Agent behavior can be non-deterministic (wrong clicks, getting stuck). Plan for occasional re-runs or manual checks.
- **Terms of use:** Sites often prohibit *automation* regardless of how “human” the browser is. Using an AI agent may still violate ToS; assess per site and accept risk if you rely on this path.
- **Cost and platform:** Tools like Atlas may require a subscription (e.g., Plus/Pro) and are often tied to one OS (e.g., macOS first); factor that in if this becomes the primary way you hit one site.

**Recommendation:** Treat AI-browser access as a **fallback for specific sites** (e.g., Facebook Marketplace) when login or anti-bot makes scraping unworkable. Prefer traditional scraping or APIs where possible; use the AI browser for targeted, lower-frequency runs and wire its output (e.g., exported list or clipboard) into your storage/alert pipeline where feasible.

---

## Risks and considerations

- **Terms of use:** Each site may restrict scraping; implement conservatively and switch to APIs/feeds if available. Facebook Marketplace in particular has strict anti-scraping policies and typically requires login.
- **Site changes:** Listing page structure can change; design parsers to be easy to update and add logging for parse failures.
- **Rate limiting:** Use delays and polite concurrency to avoid blocks or bans.
- **Facebook Marketplace:** May require authenticated sessions or browser automation (e.g., Playwright); treat as a separate integration path if needed.

This plan is intended to be implemented incrementally: get one site working end-to-end, then add the others and scheduling, then alerts and any UI.
