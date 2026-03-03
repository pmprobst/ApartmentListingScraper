# Claude Extraction Schema

This document defines the JSON schema stored in the `listings.extracted` column. All
fields are **optional** at runtime; when a value cannot be confidently inferred it
should be `null` or use the explicit `"not_mentioned"` enum where specified.

The object is **flat** with snake_case keys so it is easy to query from SQLite.

## Top‑level JSON object

The Claude extraction step must return a single JSON object with exactly these keys:

```json
{
  "washer_dryer": null,
  "renter_paid_fees": null,
  "availability": null,
  "pet_policy": null,
  "parking": null,
  "lease_length": null,
  "deposit": null,
  "application_fees": null,
  "furnished": null,
  "square_footage": null,
  "roommates": null,
  "subletting": null,
  "contact": null,
  "move_in_incentives": null,
  "amenities": null,
  "restrictions": null,
  "location_detail": null
}
```

Types and semantics for each field are described below.

### `washer_dryer` (string or null)

- **Type:** string enum or `null`.
- **Allowed values (examples):**
  - `"in_unit"` – private washer & dryer inside the unit.
  - `"hookups_only"` – hookups provided; tenant supplies machines.
  - `"shared_laundry"` – washer/dryer shared with roommates in the unit.
  - `"laundry_in_building"` – machines in the building but not in the unit.
  - `"coin_op_on_site"` – coin‑operated machines on site.
  - `"no_laundry"` – explicitly states there is no laundry.
  - `"not_mentioned"` – no clear mention of laundry.

### `renter_paid_fees` (array of strings or null)

- **Type:** array of short tokens or `null`.
- **Meaning:** recurring costs the renter must pay **in addition** to base rent.
- **Examples:**
  - `["electricity", "gas", "water", "sewer", "trash", "internet"]`
  - `["parking", "pet_rent"]`
  - `null` when not mentioned.

### `availability` (string or null)

- **Type:** short free‑form string or `null`.
- **Examples:** `"ASAP"`, `"March 1, 2026"`, `"mid‑March"`, `"August for fall semester"`.

### `pet_policy` (string or null)

- **Type:** short summary string or `null`.
- **Examples:**
  - `"cats and small dogs allowed, $300 non‑refundable pet fee plus $50/month pet rent"`
  - `"no pets"`
  - `"dogs allowed with breed restrictions"`

### `parking` (string or null)

- **Type:** string enum or `null`.
- **Allowed values (examples):**
  - `"included_assigned"` – included in rent, assigned stall.
  - `"included_unassigned"` – included in rent, first‑come‑first‑served.
  - `"garage_included"`
  - `"garage_extra_cost"`
  - `"street_only"`
  - `"paid_lot"` – off‑street lot with extra monthly fee.
  - `"no_parking"` – explicitly no parking.
  - `"not_mentioned"` – not clearly described.

### `lease_length` (string or null)

- **Type:** normalized string or `null`.
- **Examples:**
  - `"month_to_month"`
  - `"6_months"`
  - `"12_months"`
  - `"6_or_12_months"`
  - `"short_term"` – clearly short‑term or sublet.
  - `"unspecified"` – lease implied but length unclear.

### `deposit` (string or null)

- **Type:** short string or `null`.
- **Meaning:** deposit amount and whether refundable; may include last‑month rent.
- **Examples:** `"$1200 refundable"`, `"$500 non‑refundable cleaning fee"`, `"first and last month’s rent"`.

### `application_fees` (string or null)

- **Type:** short string or `null`.
- **Meaning:** one‑time application, admin, or move‑in fees.
- **Examples:** `"$40 application fee per adult"`, `"$200 admin fee at move‑in"`.

### `furnished` (string or null)

- **Type:** string enum or `null`.
- **Allowed values (examples):**
  - `"fully_furnished"`
  - `"partially_furnished"`
  - `"unfurnished"`
  - `"not_mentioned"`

### `square_footage` (integer or null)

- **Type:** integer number of square feet or `null`.
- **Examples:** `850`, `1200`.

### `roommates` (string or null)

- **Type:** short summary string or `null`.
- **Examples:**
  - `"entire_unit"` – whole place, no roommates.
  - `"private_room_in_3br_with_2_roommates"`
  - `"shared_room"` – shared bedroom.
  - `"unspecified"` when it is clearly a room rental but roommate count is unclear.

### `subletting` (string or null)

- **Type:** string enum or `null`.
- **Allowed values:**
  - `"allowed"`
  - `"not_allowed"`
  - `"not_mentioned"`

### `contact` (string or null)

- **Type:** short summary string or `null`.
- **Examples:** `"contact property manager via portal"`, `"text landlord at 555‑123‑4567"`, `"listing agent; message through platform"`.

### `move_in_incentives` (string or null)

- **Type:** short string or `null`.
- **Meaning:** any discounts or incentives for moving in.
- **Examples:** `"first month free"`, `"half off first month"`, `"reduced deposit for qualified applicants"`.

### `amenities` (array of strings or null)

- **Type:** array of short tokens or `null`.
- **Examples:**
  - `["central_ac", "dishwasher", "gym", "pool", "yard", "storage", "laundry_in_unit"]`
  - `["clubhouse", "covered_parking"]`

### `restrictions` (array of strings or null)

- **Type:** array of short tokens or `null`.
- **Examples:**
  - `["no_smoking", "no_pets"]`
  - `["students_only", "credit_check_required", "background_check_required"]`

### `location_detail` (string or null)

- **Type:** short string or `null`.
- **Meaning:** location hints beyond the raw address.
- **Examples:** `"near BYU"`, `"near UVU"`, `"Downtown Provo"`, `"close to I‑15 and University Pkwy"`.

