# High-Level Plan: Utah Valley Rental Skimmer

Application that regularly skims online rental markets in Utah Valley to identify potential opportunities (apartments and houses for rent).

---

## Goal

- **Input:** Target area = Utah Valley (e.g., Provo, Orem, and nearby cities).
- **Output:** A webpage of rental opportunities from the top listing sites, sorted by user preference, with filtering. The page is hosted on **GitHub Pages** and updated after each **GitHub Actions** workflow run.

**One-line summary:** Webpage of rental listings from Bright Data (Facebook Marketplace first, then Zillow/KSL/Apartments.com), filtered by price, enriched by Claude API (new listings only), stored in SQLite on the **data/** branch, updated by **GitHub Actions**, and served via **GitHub Pages** with a run status indicator.

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

**Implementation order:** Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4. Each phase doc has **detailed steps** and **requirements that must pass** before moving on.

---

## Doc index (plan directory)

| Doc | Purpose |
|-----|--------|
| [plan.md](plan.md) | **This file.** High-level plan: goal, tech stack, phase summary. |
| [features.md](features.md) | All desired features; price filter and Claude extraction behavior; extraction field list. |
| [reference.md](reference.md) | Target data sources, deduplication and SQLite schema, config schema, deliverables, fallback (AI browser), risks. |
| [phase-0.md](phase-0.md) | Phase 0: Config schema (TOML) + Claude API prototype; steps and exit criteria. |
| [phase-1.md](phase-1.md) | Phase 1: Foundation – Bright Data → SQLite → run status → webpage. |
| [phase-2.md](phase-2.md) | Phase 2: Claude for new listings, multi-site, GitHub Actions, data branch. |
| [phase-3.md](phase-3.md) | Phase 3: Webpage and observability (extracted fields, run status, Pages). |
| [phase-4.md](phase-4.md) | Phase 4: Robustness and polish (errors, logging, docs). |
