# High-Level Plan: Utah Valley Rental Skimmer

Application that regularly skims online rental markets in Utah Valley to identify potential opportunities (apartments and houses for rent).

---

## Goal

- **Input:** Target area = Utah Valley (e.g., Provo, Orem, and nearby cities).
- **Output:** A webpage of rental opportunities from the top listing sites, sorted by user preference, with filtering. The page is hosted on **GitHub Pages** and updated after each **GitHub Actions** workflow run.

---

## Chosen tech stack

| Choice | Technology | Notes |
|--------|------------|--------|
| Language | **Python** | Scripts and data pipeline. |
| Data acquisition | **Bright Data API** | Start with Facebook Marketplace; then Zillow, KSL, Apartments.com. |
| Storage | **SQLite** (python `sqlite3`) | Listings and metadata; stored on **data/** branch (not main). |
| Scheduling | **GitHub Actions** | Schedule (e.g. every 12 hours); fetch → Claude extraction → build_page; push to Pages. Secrets in GitHub Secrets. |
| LLM extraction | **Claude API** | Run only on new listings within price/parameter filter. Prototype separately first. |
| Interaction | **Scripts** | `fetch.py`, `build_page.py`; run locally or via GitHub Actions. |
| Output | **GitHub-hosted webpage** | Static HTML; run status indicator on page. |

- **Bright Data:** Facebook Marketplace Scraper API; normalize response and save to SQLite. Rollout: Facebook Marketplace → Zillow → KSL → Apartments.com.
- **GitHub Actions:** Workflow checks out repo (and **data/** branch for SQLite), runs pipeline, pushes DB to **data/** and site to Pages branch/folder. Do not commit SQLite to main.

---

## High-level phases

| Phase | Focus | Details |
|-------|--------|--------|
| **Phase 0** | Config schema and Claude API prototype | Define config (TOML) and validate LLM extraction in isolation before wiring pipeline. |
| **Phase 1** | Foundation | Bright Data → SQLite (Facebook Marketplace), dedup schema, run status, static webpage. |
| **Phase 2** | Claude + multi-site + GitHub Actions | Claude extraction for new listings only; add other sites; schedule via Actions; persist DB on data/ branch. |
| **Phase 3** | Webpage and observability | Full listing display with extracted fields, run status, GitHub hosting. |
| **Phase 4** | Robustness and polish | Error handling, logging, optional diff report. |

Each phase has a dedicated doc with **detailed steps** and **requirements that must pass** before moving on.

- [phase-0.md](phase-0.md) – Config schema and Claude API prototype
- [phase-1.md](phase-1.md) – Facebook Marketplace via Bright Data (foundation)
- [phase-2.md](phase-2.md) – Claude extraction, multi-site, GitHub Actions
- [phase-3.md](phase-3.md) – Webpage and observability
- [phase-4.md](phase-4.md) – Robustness and polish

---

## Other docs

- [features.md](features.md) – All desired features and price/LLM extraction behavior.
- [reference.md](reference.md) – Target data sources, deduplication and SQLite schema, config schema, deliverables, fallback (AI browser), risks.
