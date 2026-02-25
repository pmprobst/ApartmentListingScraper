# Research: Top Rental Listing Sites for Utah Valley

This document identifies the top four sites for listing rental contracts (apartments and houses) in Utah Valley (Provo, Orem, and surrounding areas).

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

## 4. **Facebook Marketplace** (facebook.com/marketplace)

- **Coverage:** Local rental listings (apartments, houses, rooms) in Utah Valley; users list by location (e.g., Provo, Orem, Salt Lake area). Often includes private landlords and sublets not found on traditional rental sites.
- **Strengths:** Huge user base, strong local reach, mix of formal and informal listings (full units, rooms, sublets). Many listings appear only on Marketplace. Search and filter by location and category (Housing → Apartments for Rent / Houses for Rent).
- **Relevance for scraping:** Requires Facebook login for full access; content is dynamic and app-heavy. Facebook’s terms of use and anti-scraping policies are strict. Consider official APIs or manual monitoring if automation is limited; otherwise use careful, respectful automation and rate limiting.

---

## Other notable platforms

- **Rentler** (rentler.com) – 284+ properties in Provo/Orem, good filters; strong alternative to the top four.
- **ForRent.com** – Lists apartments in Orem and metro area.
- **HomeFinder** – Utah-wide rentals including homes, condos, townhouses.

---

## Summary

| Rank | Site                | Primary URL                 | Best for                          |
|------|---------------------|-----------------------------|-----------------------------------|
| 1    | Zillow              | zillow.com                  | Apartments + houses, daily updates |
| 2    | KSL Real Estate     | homes.ksl.com               | Local Utah listings, high relevance |
| 3    | Apartments.com      | apartments.com              | Apartments + some houses, strong filters |
| 4    | Facebook Marketplace| facebook.com/marketplace    | Local listings, private landlords, rooms/sublets |

For an application that “regularly skims” Utah Valley rental markets, prioritizing **Zillow**, **KSL Real Estate**, **Apartments.com**, and **Facebook Marketplace** will cover a large share of available listings, including many that appear only on Marketplace. Add Rentler or others in a later phase if needed.
