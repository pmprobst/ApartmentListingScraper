# Research: Top Rental Listing Sites for Utah Valley

This document identifies the top three sites for listing rental contracts (apartments and houses) in Utah Valley (Provo, Orem, and surrounding areas).

---

## 1. **Zillow** (zillow.com)

- **Coverage:** Apartments and houses for rent in Provo, Orem, and Utah Valley; listings updated daily.
- **Strengths:** Large national platform with strong local inventory, familiar UI, map view, and detailed filters. Good for both apartments and single-family homes.
- **Relevance for scraping:** Well-structured listing pages; rental search can be filtered by location (e.g., Provo, UT). Consider robots.txt and terms of use when designing a scraper.

---

## 2. **KSL Real Estate** (homes.ksl.com)

- **Coverage:** Utah (and Idaho/Wyoming). Dedicated rental section (e.g. apartments, houses) with search by location.
- **Strengths:** Dominant local platform in Utah; many landlords and renters use KSL first. Save searches, favorites, and messaging via KSL account.
- **Relevance for scraping:** Utah-specific, so critical for Utah Valley coverage. Rental search at paths like `/rent/search/apartment`. Check KSL’s terms of service and technical access policies.

---

## 3. **Apartments.com** (apartments.com)

- **Coverage:** Hundreds of rentals in Provo (e.g. 840+ in Provo) and Orem; includes apartments, houses, condos, townhomes.
- **Strengths:** Strong filters (price, beds/baths, amenities, pets, student housing), broad inventory, and multiple property types.
- **Relevance for scraping:** Listings and filters are structured; good candidate for automated discovery of new listings. Respect rate limits and terms of use.

---

## Other notable platforms

- **Rentler** (rentler.com) – 284+ properties in Provo/Orem, good filters; strong alternative to the top three.
- **ForRent.com** – Lists apartments in Orem and metro area.
- **HomeFinder** – Utah-wide rentals including homes, condos, townhouses.

---

## Summary

| Rank | Site              | Primary URL           | Best for                          |
|------|-------------------|------------------------|-----------------------------------|
| 1    | Zillow            | zillow.com             | Apartments + houses, daily updates |
| 2    | KSL Real Estate   | homes.ksl.com          | Local Utah listings, high relevance |
| 3    | Apartments.com    | apartments.com         | Apartments + some houses, strong filters |

For an application that “regularly skims” Utah Valley rental markets, prioritizing **Zillow**, **KSL Real Estate**, and **Apartments.com** will cover a large share of available listings. Add Rentler or others in a later phase if needed.
