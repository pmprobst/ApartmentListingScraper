# High-Level Plan: Utah Valley Rental Skimmer

This document outlines a high-level plan to build an application that regularly skims online rental markets in Utah Valley to identify potential opportunities (apartments and houses for rent).

---

## Goal

- **Input:** Target area = Utah Valley (e.g., Provo, Orem, and nearby cities).
- **Output:** A webpage of rental opportunities from the top listing sites, sorted by user preference, with filtering. The page is **hosted on GitHub** (GitHub Pages) and updated after each **GitHub Actions** workflow run.

---

## Chosen tech stack

| Choice | Technology | Notes |
|--------|------------|--------|
| Language | **Python** | Scripts and data pipeline. |
| Data acquisition | **Bright Data API** | Pull scraped data via Bright Data’s API. **Start with Facebook Marketplace**, then expand to Zillow, KSL, Apartments.com. |
| Storage | **SQLite** (python `sqlite3`) | Primary database for listings and metadata (first-seen, last-seen, source, extracted fields). Single file; no separate server. |
| Scheduling | **GitHub Actions** | Workflow runs on a schedule (e.g. every 12 hours); runs fetch → Ollama for new listings → build_page; commits and pushes to the branch/folder that serves GitHub Pages. Credentials via GitHub Secrets. |
| LLM extraction | **Ollama** | Parse listing text to extract structured fields. **Run only on new listings** that match the price/parameter filter. Prototype this step separately before wiring into the full pipeline. |
| Interaction | **Scripts** | Run the app via scripts (e.g. `python fetch.py`, `python build_page.py`); run locally or via GitHub Actions. |
| Output | **GitHub-hosted webpage** | Static HTML generated from SQLite; workflow pushes to `gh-pages` or `docs/`. Page includes a **run status** indicator (last run time, success/fail, listing count) for observability from day one. |

**Data acquisition: Bright Data.** Bright Data provides a **Facebook Marketplace Scraper API** (listing URL, title, product ID, price, location, etc.). The app calls this API with search parameters (e.g. Utah Valley, rentals), normalizes the response into our schema, and saves to **SQLite**. For other sites we add Bright Data scrapers if available, or fall back to direct scraping later. See [Bright Data – Facebook Marketplace](https://brightdata.com/products/web-scraper/facebook/marketplace) and [Bright Data docs](https://docs.brightdata.com/api-reference/web-scraper-api/social-media-apis/facebook). **Rollout order:** 1) Facebook Marketplace (Bright Data) → 2) Zillow → 3) KSL → 4) Apartments.com.

**GitHub Actions (how it works):** A workflow (e.g. `.github/workflows/run-pipeline.yml`) triggers on schedule and optionally on push. It checks out the repo, sets up Python, installs deps, runs `fetch.py` (Bright Data → SQLite), runs Ollama extraction for **new** listings only, runs `build_page.py` (SQLite → static HTML + run status), then commits and pushes the output to the Pages branch/folder. Secrets (Bright Data API key) are in GitHub Settings → Secrets. No local cron or manual push required.

---

## Target Data Sources (from research.md)

**Rollout order:** We start with **Facebook Marketplace**, then add the others.

1. **Facebook Marketplace** *(first)* – facebook.com/marketplace (local listings, private landlords, rooms/sublets). Data via **Bright Data API**.
2. **Zillow** – zillow.com (apartments + houses, daily updates). Add in a later phase (Bright Data if available, else direct scraping).
3. **KSL Real Estate** – homes.ksl.com (Utah-focused rentals). Add in a later phase.
4. **Apartments.com** – apartments.com (apartments + some houses, strong filters). Add in a later phase.

---


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
- **Implication for this project:** We use **Bright Data’s Facebook Marketplace Scraper API** to pull listing data (no in-house scraping or login). Bright Data handles access; we consume the structured API response and normalize to our JSON schema.

### Summary table

| Site                | Public search/read API? | Publisher / partner APIs or feeds?        | Practical approach for this app   |
|---------------------|-------------------------|-------------------------------------------|-----------------------------------|
| Zillow              | No (legacy APIs gone)   | Yes (feed in, lead API out; publisher-only) | Scraping or AI browser            |
| KSL Real Estate     | No                      | No official API; third-party RSS possible | Scraping or AI browser            |
| Apartments.com      | No                      | Yes (OAuth API for your listings only)    | Scraping or AI browser            |
| Facebook Marketplace| No                      | Seller API to publish; Content Library for research only | **Bright Data API** (this project) |

*Sources: Zillow Group Developers, Apartments.com API docs, Meta for Developers (Marketplace, Content Library), third-party reporting on Zillow API discontinuations, FeedSpot/IFTTT for KSL RSS options. Last checked 2025.*

---

## Desired Features

1. **Scheduled skimming**  
   - **GitHub Actions** runs the pipeline on a schedule (e.g. every 12 hours) to fetch new/updated listings, run Ollama on new listings only, and update the webpage. No local cron or manual git push.

2. **Multi-site support**  
   - Start with **Facebook Marketplace** (Bright Data API). Then add Zillow, KSL, Apartments.com; design so adding each new source is straightforward (Bright Data if available, else direct scraping).

3. **Configurable search criteria**  
   - Location (cities/zip codes in Utah Valley), price range, bedrooms/bathrooms, property type (apartment, house, etc.), and optionally pet policy or keywords.

4. **Deduplication**  
   - Detect the same listing across sites (e.g., by address or listing ID) to avoid duplicates and merge data when possible. This feature is not a priority.

5. **Persistence**  
   - Store listings in **SQLite** (Python `sqlite3`) with first-seen and last-seen timestamps to track new vs. updated vs. removed.

6. **New-listing alerts**  
   - Optional: notify when new listings match criteria (e.g., email or desktop notification). Primary “view” is the generated webpage.

7. **Respectful data acquisition**  
   - Use Bright Data API for supported sites (they handle compliance). For any direct scraping added later, honor robots.txt, rate limits, and terms of use.

8. **Output and interaction**  
   - **Webpage:** Static HTML (and optional CSS/JS) generated from SQLite, hosted on GitHub (GitHub Pages). Updated after each workflow run. Include a **run status** indicator (last run time, success/failure, listing count) for simple observability from day one.  
   - **Interaction:** Run the app via **scripts** (e.g. `fetch.py`, `build_page.py`); no formal CLI or local server required.

---

## Price filter and LLM extraction (Ollama)

After the Bright Data API pulls in data, the app will:

1. **Filter by price** – Keep only new or updated listings that match pre-set price criteria (e.g. **below $1,200**; configurable in config).
2. **Ollama extraction only on new listings** – Run the LLM **only on listings that are new and within the parameters** (e.g. new + price < $1,200). Do not re-run Ollama on every listing every time; newly fetched listings that pass the filter get extracted, results stored in SQLite.
3. **Prototype Ollama separately** – Before building the full pipeline, **prototype the Ollama extraction step in isolation**: a small script that takes sample listing text, calls Ollama, and validates output schema and latency. This avoids discovering the LLM is the bottleneck after the whole pipeline is built. Only then wire Ollama into the main pipeline.

### Required extractions (first version)

| Field | Purpose |
|-------|--------|
| **Washer / dryer** | Included in unit vs hookups only vs not mentioned. |
| **Renter-paid fees** | Utilities, trash, internet, parking, pet rent, etc. that the renter must pay in addition to rent. |
| **Availability / contract start** | When the unit is available or when the lease starts (date or “ASAP”, “March”, etc.). |

### Additional extractions (in scope – include all)

Include all of the following in the Ollama extraction schema (stored in SQLite):

- **Pet policy** – Cats/dogs allowed, deposit, monthly pet rent, breed/weight limits.
- **Parking** – Included, assigned, garage, street only, or extra cost.
- **Lease length** – Month-to-month, 6 months, 12 months, or unspecified.
- **Deposit** – Amount and whether refundable; any “last month” requirement.
- **Application / admin fees** – One-time fees to apply or move in.
- **Furnished vs unfurnished** – Fully furnished, partial, or unfurnished.
- **Square footage** – If mentioned (helps compare value).
- **Roommates / layout** – Entire place vs room in shared unit; number of roommates.
- **Subletting** – Whether subletting is allowed (matters for students/short stays).
- **Contact** – Landlord vs property manager; phone/email/message preference.
- **Move-in incentives** – First month free, reduced deposit, waived fee.
- **Amenities** – AC, dishwasher, storage, gym, pool, yard, laundry in building.
- **Restrictions** – Non-smoking, student-only, no parties, credit check, etc.
- **Location detail** – Neighborhood, cross streets, or “near BYU/UVU” if mentioned (when full address is not given).

Output from Ollama is stored in SQLite (e.g. an `extracted` / `llm` column or related table per listing) and shown on the generated webpage. Pipeline: **Bright Data → SQLite → price filter (e.g. &lt; $1,200) → Ollama extraction (new listings only) → update SQLite → build_page (incl. run status).**

---

## Config schema (define before implementing)

**Define the config schema explicitly in YAML or TOML before writing code.** Write out the full spec (file format, required and optional keys, types, defaults) and get it agreed; then implement against that spec. Suggested contents:

- **Search / sources:** Location (cities, zip codes, Utah Valley), price max (e.g. 1200), price min (optional), bedrooms/bathrooms (optional), category/keywords for Bright Data.
- **Bright Data:** Dataset ID, endpoint, any source-specific options (maps to API params).
- **Ollama:** Model name, API base URL (if not default local), timeout; which fields to extract (or “all”).
- **Paths:** SQLite file path, output directory for static site (e.g. `docs/` or `gh-pages`), config file path.
- **Run status:** Where to write last run timestamp and outcome (e.g. SQLite table or small status file) for the webpage indicator.

Example shape (YAML): `location`, `price_max`, `price_min`, `bright_data.dataset_id`, `ollama.model`, `paths.db`, `paths.output`, etc. No implementation of config loading until this spec is written and committed (e.g. in `docs/config_schema.md` or in the repo root as `config.schema.yaml` / `config.schema.toml`).

---

## Implementation Outline

### Phase 0: Config schema and Ollama prototype (before main pipeline)

- **Config schema:** Write the full **config spec** (YAML or TOML) as in "Config schema (define before implementing)". Commit it. Do not implement config loading until this is done.
- **Ollama prototype:** Build a **standalone script** that takes sample listing text, calls Ollama with the extraction prompt, validates response shape and latency. Confirm the LLM step is viable before wiring into the full pipeline.

### Phase 1: Facebook Marketplace via Bright Data (foundation)

- **Stack:** Python, Bright Data API client, **SQLite** (python `sqlite3`) for storage. Config loaded from the agreed schema.
- **Bright Data integration:** Implement `fetch.py` that reads config, calls Bright Data's Facebook Marketplace Scraper API, normalizes to common schema (title, link, price, beds, baths, address, source, first-seen, last-seen), and **saves/merges into SQLite**. Deduplication by listing URL or product ID.
- **Run status:** Record each run's timestamp and outcome (success/failure, listing count) in SQLite or a small status file for the webpage.
- **Webpage:** Implement `build_page.py` to read from **SQLite** and generate static HTML. **Include the run status indicator** (last run time, success/fail, listing count) on the page. End-to-end: Bright Data to SQLite to build_page with run status.

### Phase 2: Ollama for new listings only, then expand sites and GitHub Actions

- **Ollama step:** Run Ollama extraction **only on new listings** that match the price/parameter filter. Store extracted fields in SQLite.
- **Add Zillow, KSL, Apartments.com:** For each site, use Bright Data if available or add a direct scraper. Reuse the same SQLite schema; tag each listing with `source`.
- **Scheduler:** Use **GitHub Actions** (not local cron). Workflow: checkout, setup Python, install deps, run `fetch.py`, run Ollama for new listings, run `build_page.py`, commit and push to the branch/folder that serves GitHub Pages. Use **GitHub Secrets** for Bright Data API key. Schedule (e.g. every 12 hours) and optionally on push.
- **New vs. updated:** On each run, compare with SQLite; tag new vs updated.

### Phase 3: Webpage and observability

- **Generate static webpage:** `build_page.py` reads SQLite and generates static HTML that displays listings (with extracted fields), sorted/filtered by user preference, and the **run status** indicator (last run, success/failure, listing count).
- **GitHub hosting:** The workflow commits and pushes the generated files; no manual push. GitHub Pages serves from the chosen branch/folder.
- **Scripts:** `python fetch.py`, `python build_page.py`; run locally or via GitHub Actions.
- **Optional alerts:** If desired, add email or other notification when new listings appear; not required for MVP.

### Phase 4: Robustness and polish

- **Error handling and logging:** Log failures per site; retry with backoff; don’t lose data if one site is down.
- **Legal/compliance:** Document and enforce robots.txt and rate limits; consider moving to official APIs or feeds where offered.
- **Optional:** Lightweight “listing diff” report (new/removed/updated) per run for easy scanning.

---

## Notes for future features

- **Drive time to a central location:** Use the **Google Distance Matrix API** (or similar) to calculate drive time from each listing’s address to a user-defined central point (e.g. work, campus, or a favorite neighborhood). Store drive time or distance in the listing data and show it on the webpage so users can sort or filter by commute. Requires a configurable “origin” address and a Google API key; handle missing or partial addresses gracefully.

---

## Deliverables (summary)

| Item | Description |
|------|-------------|
| Research | research.md – top 4 rental sites for Utah Valley (done). |
| Plan | plan.md – this high-level plan and feature set. |
| Config | **Config schema** (YAML/TOML) defined and committed before implementation; search criteria, price filter, Bright Data params, Ollama settings, paths. |
| Data acquisition | **Bright Data API** for Facebook Marketplace first; then Zillow, KSL, Apartments.com. Output to **SQLite**. |
| Storage | **SQLite** (python `sqlite3`) with listings, timestamps, source, and extracted (LLM) fields. |
| Scheduler | **GitHub Actions** workflow (schedule + optional push); credentials via GitHub Secrets. |
| Webpage | Static HTML generated from SQLite, hosted on GitHub Pages; includes **run status** indicator (last run, success/fail, listing count). |
| Ollama | Prototype extraction **separately** first; then run **only on new listings** within parameters. |
| Scripts | `fetch.py` (Bright Data → SQLite), `build_page.py` (SQLite → HTML + run status); run via GitHub Actions or locally. |
| Alerts | Optional: notifications for new listings; not required for MVP. |

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

- **Bright Data:** Paid service; requires API credentials. In GitHub Actions, use **GitHub Secrets** (e.g. `BRIGHTDATA_API_KEY`); never commit keys. Bright Data handles compliance for their scrapers; we only consume the API response.
- **Terms of use:** For sites we add via direct scraping later, honor robots.txt and rate limits. Facebook Marketplace is covered by Bright Data for this project.
- **Site changes:** Bright Data may update their API response format; our normalizer should tolerate optional fields. For direct scrapers added later, design parsers to be easy to update and add logging for parse failures.
- **Rate limiting:** Bright Data has its own concurrency and limits; follow their docs. For any direct scraping, use delays and polite concurrency.

This plan is intended to be implemented incrementally: **config schema + Ollama prototype** first; then **Facebook Marketplace via Bright Data** → SQLite → webpage with run status; then Ollama for new listings only, other sites, and **GitHub Actions** (replacing local cron and manual push).
