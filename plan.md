# Utah Valley Rental Skimmer – Plan overview

This repo builds an application that regularly skims online rental markets in Utah Valley (Provo, Orem, etc.) and publishes a webpage of opportunities. The **full plan** lives in the **plan/** directory.

---

## Quick links

| Doc | Purpose |
|-----|--------|
| [plan/plan.md](plan/plan.md) | **High-level plan**: goal, tech stack, phase summary. Start here. |
| [plan/features.md](plan/features.md) | **All desired features**: scheduling, multi-site, dedup, persistence, price filter, Claude extraction, output, etc. |
| [plan/phase-0.md](plan/phase-0.md) | Phase 0: Config schema + Claude API prototype (steps + exit criteria). |
| [plan/phase-1.md](plan/phase-1.md) | Phase 1: Foundation – Bright Data → SQLite → run status → webpage. |
| [plan/phase-2.md](plan/phase-2.md) | Phase 2: Claude for new listings, multi-site, GitHub Actions, data branch. |
| [plan/phase-3.md](plan/phase-3.md) | Phase 3: Webpage and observability (extracted fields, run status, Pages). |
| [plan/phase-4.md](plan/phase-4.md) | Phase 4: Robustness and polish (errors, logging, docs). |
| [plan/reference.md](plan/reference.md) | **Reference**: data sources, deduplication/SQLite schema, config spec, deliverables, fallback, risks. |

---

## One-line summary

**Goal:** Webpage of rental listings from Bright Data (Facebook Marketplace first, then Zillow/KSL/Apartments.com), filtered by price, enriched by Claude API (new listings only), stored in SQLite on a **data/** branch, updated by **GitHub Actions** and served via **GitHub Pages** with a run status indicator.

Implement in order: **Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4.** Each phase doc lists detailed steps and **requirements to pass** before moving on.
