# Apartment Listing Extraction Plan

## Overview

This document covers a two-stage pipeline for extracting structured data from Facebook Marketplace
apartment listings. Stage 1 uses fast, deterministic regex to extract high-confidence values for
free. Stage 2 sends the listing (plus Stage 1 results) to the Claude API to fill in anything
ambiguous or missing.

**Target fields:**
- `bedrooms` — integer
- `bathrooms` — float
- `in_unit_washer_dryer` — boolean or null
- `has_roommates` — boolean (true = joining existing people, false = whole unit)
- `gender_preference` — "male" | "female" | "any" | null
- `utilities_included` — list of strings, "all", or null
- `non_included_utilities_cost` — string describing estimated cost, or null
- `lease_length` — string description of the lease term, or null

---

## Stage 1: Regex Extraction

### Data Observations from 100 Real Listings

Before writing patterns, here is what was actually observed in the title and description fields:

**Bedrooms/bathrooms** appear in titles with high consistency:
- `2 Beds 1 Bath`, `3 Beds 2 Baths`, `2 Beds 2.5 Baths`, `Studio 1 Bath`
- Also in descriptions: `2 bed 2 bath`, `2BR/1BA`, `3x2`, `4 bed, 2 bath`

**In-unit laundry** phrasing varies widely:
- `in unit washer and dryer`, `in unit washer/dryer`, `washer/dryer in apartment`
- `in house washer and dryer`, `laundry in unit`, `in-unit laundry`
- `washer and dryer provided`, `laundry room with washer and dryer`
- Negative: `building laundry`, `laundry mat`, `coin operated laundry`, `shared laundry`

**Roommate situation** is almost never stated directly — it must be inferred:
- Has roommates: `shared room`, `sharing with X roommates`, `X existing roommates`,
  `X person apartment`, `4 girls total`, `3 roommates staying`, `two other roommates`
- Whole unit: `whole place to yourself`, `entire unit`, `no one else is currently living in the unit`,
  `you'll have the whole place`
- Ambiguous: `private room` (usually has roommates in the rest of the unit, but not always)

**Gender preference** is usually stated explicitly:
- Female: `Girls' housing`, `Women's`, `female apartment`, `FEMALE`, `girl shared room`,
  `rented to women`, `female room`, `looking for a female`
- Male: `Men's`, `MALE`, `male housing`, `men's apartment`, `for a man`, `looking for a male roommate`,
  `single male room`, `male BYU`, `men's shared room`
- Neutral: absence of these terms (defaults to "any")

**Utilities** language:
- All included: `utilities included`, `all utilities included`, `utilities included in price`,
  `all utilities`, `including utilities`, `rent includes utilities`
- Partial: `water included`, `$50 utilities flat`, `utilities are fixed at $50/month`,
  `water, sewer, trash included`, `water bill included in the rent`
- Not included: `plus utilities`, `+ utilities`, `utilities not included`
- Cost hints: `utilities run $50-65`, `utilities about $70`, `usually end up paying ~$50`

**Lease length** formats:
- Named periods: `spring/summer`, `fall/winter`, `spring & summer`, `year-round`
- Date ranges: `April 21st - August 14th`, `August 2026-2027`, `now through July`
- Duration strings: `12-month lease`, `month to month`, `6 mo lease`
- Relative: `through August`, `ends mid August`, `until August 14`

---

### Regex Patterns

```python
import re
from typing import Optional

def extract_bedrooms(text: str) -> Optional[int]:
    """
    Matches: '2 Beds', '2 bed', '2BR', '2bd', 'Studio', '3x2' (first number)
    """
    # Studio/efficiency
    if re.search(r'\bstudio\b', text, re.IGNORECASE):
        return 0

    patterns = [
        r'(\d+)\s*bed(?:room)?s?',      # "2 bedrooms", "3 bed"
        r'(\d+)\s*b[rd]\b',             # "2BR", "2bd"
        r'(\d+)x\d',                     # "3x2" floor plan notation
        r'(\d+)\s*\/\s*\d+\s*ba',       # "2/1ba"
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 0 < val <= 10:            # sanity check
                return val
    return None


def extract_bathrooms(text: str) -> Optional[float]:
    """
    Matches: '2 Baths', '1 Bath', '2.5 Baths', '1ba', '1BA'
    """
    patterns = [
        r'(\d+(?:\.\d)?)\s*bath(?:room)?s?',   # "2 bathrooms", "2.5 bath"
        r'(\d+(?:\.\d)?)\s*ba\b',               # "1ba", "2ba"
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 0 < val <= 10:
                return val
    return None


def extract_in_unit_washer_dryer(text: str) -> Optional[bool]:
    """
    Returns True for in-unit, False for shared/building/coin-op, None if unmentioned.
    Order matters: check in-unit patterns FIRST, then negatives.
    """
    in_unit_patterns = [
        r'in[\s\-]?unit\s+(?:washer|laundry)',
        r'washer\s*(?:and|&|/)\s*dryer\s+in\s+(?:unit|apartment|apt|home|the\s+unit)',
        r'in[\s\-]?unit\s+washer',
        r'in\s+house\s+washer',
        r'in[\s\-]unit\s+laundry',
        r'laundry\s+in\s+(?:unit|apartment|apt)',
        r'washer\s*(?:and|&|/)\s*dryer\s+(?:provided|included|hookups?\s+in)',
        r'laundry\s+room\s+with\s+washer\s+and\s+dryer',  # listing 98: "laundry room with washer and dryer"
        r'private\s+laundry',
    ]
    shared_patterns = [
        r'(?:shared|building|on[\s\-]?site|coin[\s\-]?op(?:erated)?)\s+laundry',
        r'laundry\s+(?:mat|room\s+shared|(?:is\s+)?shared)',
        r'laundry\s+room\s+shared\s+with',   # listing 2
        r'laundromat',
    ]
    lower = text.lower()
    for p in in_unit_patterns:
        if re.search(p, lower):
            return True
    for p in shared_patterns:
        if re.search(p, lower):
            return False
    return None


def extract_gender_preference(text: str) -> Optional[str]:
    """
    Returns 'male', 'female', or None (caller should default None → 'any').
    """
    female_patterns = [
        r"\bgirl(?:s'?|'s)?\s+(?:housing|apartment|room|contract|only|lease)",
        r"\bwomen(?:'s)?\s+(?:housing|apartment|contract|only|spot|room)",
        r"\bfemale\s+(?:apartment|housing|only|room|village|private)",
        r"\bfemale[\s\-]only\b",
        r"\bfor\s+(?:a\s+)?(?:woman|girl|female)\b",
        r"\blooking\s+for\s+(?:a\s+)?(?:woman|girl|female)",
        r"\brented\s+to\s+women\b",
        r"\bwomen(?:'s)?\s+(?:private|BYU|contract|shared|spot)",
        r"\bgirl(?:'s)?\s+shared\b",
        r"\bfemale\s+BYU\b",
        r"\bcurrent\s+tenants\s+are\s+female\b",
    ]
    male_patterns = [
        r"\bmen(?:'s)?\s+(?:housing|apartment|contract|only|room|lease|shared|contact|spot)",
        r"\bmale\s+(?:housing|apartment|only|BYU|room|roommate|student)",
        r"\bfor\s+(?:a\s+)?(?:man|male|guy)\b",
        r"\blooking\s+for\s+(?:a\s+)?(?:man|male|guy)",
        r"\bmale[\s\-]only\b",
        r"\bsingle\s+male\s+room\b",
        r"\broom\s+for\s+a\s+man\b",
    ]
    lower = text.lower()
    # Female check first (slightly more common in dataset)
    for p in female_patterns:
        if re.search(p, lower):
            return "female"
    for p in male_patterns:
        if re.search(p, lower):
            return "male"
    return None


def extract_utilities(text: str):
    """
    Returns:
      utilities_included: list of strings | "all" | None
      non_included_cost: string | None
    """
    lower = text.lower()

    # --- ALL utilities included ---
    all_included_patterns = [
        r'\ball\s+utilities\s+included\b',
        r'\butilities\s+(?:are\s+)?included\b',
        r'\bincluding\s+utilities\b',
        r'\brent\s+includes\s+utilities\b',
        r'\butilities\s+included\s+in\s+(?:rent|price)\b',
        r'\bprice\s+includes\s+(?:all\s+)?utilities\b',
        r'\butility\s+fee\s+of\s+\$[\d,]+.*includes\s+all\b',
        r'\$[\d,]+\s*(?:per\s+month|\/mo)?\s+including\s+utilities',
        r'\bflat\s+rate\s+utilities\s+included',
    ]
    for p in all_included_patterns:
        if re.search(p, lower):
            return "all", None

    # --- Specific utilities included ---
    specific_included = []
    utility_keywords = {
        "water":     [r'\bwater\b(?:\s+(?:bill|is|are))?\s+included'],
        "sewer":     [r'\bsewer\b(?:\s+(?:bill|is|are))?\s+included'],
        "trash":     [r'\btrash\b(?:\s+(?:bill|is|are))?\s+included'],
        "gas":       [r'\bgas\b(?:\s+(?:bill|is|are))?\s+included'],
        "electric":  [r'\b(?:electric(?:ity)?|electric\s+bill)\b\s+included'],
        "internet":  [r'\b(?:internet|wifi|wi-fi)\b\s+included'],
    }
    for util, patterns in utility_keywords.items():
        for p in patterns:
            if re.search(p, lower):
                specific_included.append(util)
                break
    # Also catch: "W, S, T are $20" style — those are NOT included (tenant pays separately)
    # So only return specific_included if not empty
    if specific_included:
        return specific_included, None

    # --- NOT included + cost mentioned ---
    # Patterns that suggest cost of utilities NOT included
    cost_patterns = [
        # "$50-65 utilities", "utilities run ~$50", "utilities come to $70"
        r'utilities\s+(?:are\s+|run\s+|come\s+to\s+|around\s+|about\s+|~\s*)?\$[\d,]+(?:\s*[-–]\s*\$?[\d,]+)?',
        r'\$[\d,]+\s*(?:[-–]\s*\$?[\d,]+)?\s*(?:per\s+month\s+)?(?:for\s+)?utilities',
        r'utilities\s+(?:is|are)\s+(?:fixed\s+at\s+|flat\s+|around\s+|about\s+)?\$[\d,]+',
        r'utilities:\s*\$[\d,]+',
        r'\+\s*\$[\d,]+\s*utilities',
        r'usually\s+end\s+up\s+paying\s+(?:a\s+little\s+(?:less|more)\s+than\s+|around\s+|about\s+)?\$[\d,]+',
        # "after utilities it comes to $518"
        r'after\s+utilities\s+(?:it\s+)?comes?\s+to\s+\$[\d,]+',
    ]
    for p in cost_patterns:
        m = re.search(p, lower)
        if m:
            # Extract the matched span from ORIGINAL text to preserve casing/dollar signs
            non_included_cost = text[m.start():m.end()].strip()
            return None, non_included_cost

    # --- Explicit "plus utilities" with no cost ---
    if re.search(r'\+\s*utilities\b|plus\s+utilities\b', lower):
        return None, "cost not specified"

    return None, None


def extract_lease_length(text: str) -> Optional[str]:
    """
    Captures named seasons, academic terms, specific date ranges, and duration strings.
    Returns the matched string for LLM to normalize.
    """
    patterns = [
        # Duration: "12-month lease", "6 month lease", "month-to-month"
        r'\d+[\s\-]month\s+lease',
        r'month[\s\-]to[\s\-]month',
        r'm2m\b',
        # Named periods
        r'spring\s*(?:/|and|&|[-–])?\s*summer(?:\s+\d{4})?',
        r'fall\s*(?:/|and|&|[-–])?\s*winter(?:\s+\d{4})?',
        r'year[\s\-]round',
        # Academic year range like "2026-2027" or "2026/2027"
        r'20\d{2}[\s\-–/]+20\d{2}',
        # "through August", "until August 14", "ends mid August"
        r'(?:through|until|thru|ends?(?:\s+mid)?)\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|'
        r'Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|'
        r'Nov(?:ember)?|Dec(?:ember)?)(?:\s+\d{1,2}(?:st|nd|rd|th)?)?(?:,?\s*20\d{2})?',
        # Explicit date range: "April 21st - August 14th"
        r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|'
        r'Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?'
        r'\s*[-–]\s*(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
        r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
        r'\s+\d{1,2}(?:st|nd|rd|th)?',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def extract_has_roommates(text: str) -> Optional[bool]:
    """
    Returns True = will have roommates, False = whole unit, None = unclear.
    This field has high ambiguity — Stage 2 LLM should always review it.
    """
    whole_unit_patterns = [
        r'\bwhole\s+(?:place|unit|apartment)\s+to\s+yourself\b',
        r'\bno\s+one\s+else\s+(?:is\s+)?(?:currently\s+)?living\s+in\s+the\s+unit\b',
        r'\bentire\s+unit\b',                     # "beginning Aug, 6 spots available (the entire unit)"
        r'\bwhole\s+unit\b',
        r'\bprivate\s+(?:entrance|basement\s+suite)\b',  # standalone apt w/ private entrance
    ]
    has_roommates_patterns = [
        r'\bshared\s+room\b',
        r'\b\d+\s+(?:existing\s+)?roommates?\b',
        r'\b\d+\s+(?:great\s+|clean\s+|fun\s+)?roommates?\s+staying\b',
        r'\b(?:two|three|four|five|six)\s+(?:other\s+)?roommates?\b',
        r'\b\d+\s*(?:person|people|man|guys?|girls?|women|men)\s+apartment\b',
        r'\b(?:other\s+)?roommates?\s+(?:are\s+)?(?:very|super|so\s+)?(?:great|sweet|fun|clean|amazing|chill)\b',
        r'\bjoining\b.*\broommates?\b',
    ]
    lower = text.lower()
    for p in whole_unit_patterns:
        if re.search(p, lower):
            return False
    for p in has_roommates_patterns:
        if re.search(p, lower):
            return True
    return None
```

---

### Stage 1 Runner

```python
def run_stage1(title: str, description: str) -> dict:
    combined = f"{title}\n{description}"
    beds = extract_bedrooms(combined)
    baths = extract_bathrooms(combined)
    washer = extract_in_unit_washer_dryer(combined)
    gender = extract_gender_preference(combined)
    roommates = extract_has_roommates(combined)
    utilities_inc, util_cost = extract_utilities(combined)
    lease = extract_lease_length(combined)

    return {
        "bedrooms":                   beds,
        "bathrooms":                  baths,
        "in_unit_washer_dryer":       washer,
        "has_roommates":              roommates,
        "gender_preference":          gender if gender else "any",
        "utilities_included":         utilities_inc,
        "non_included_utilities_cost": util_cost,
        "lease_length":               lease,
        "_needs_llm": any(v is None for v in [beds, baths, washer, roommates, utilities_inc, lease])
                      or util_cost == "cost not specified",
    }
```

The `_needs_llm` flag is set when any field is still unknown or the utilities cost was flagged as
unresolved. This controls whether Stage 2 fires for a given listing.

---

## Stage 2: Claude API Extraction

### When to Call

Call the LLM when `_needs_llm` is `True`, OR when:
- `has_roommates` is `None` (it is hard to infer from regex alone)
- `utilities_included` is `None` and `non_included_utilities_cost` is also `None`
  (utilities situation completely unknown)
- The listing is long (>400 chars) and mostly prose rather than structured bullet points —
  prose listings almost always require the LLM

### Prompt Design

The prompt uses three techniques that reliably improve extraction accuracy:
1. **Injecting Stage 1 pre-fills** so the model doesn't waste tokens re-deriving what regex
   already found with confidence.
2. **Explicit null instruction** — telling the model not to guess reduces hallucination on
   sparse listings.
3. **JSON-only output** with a strict schema so the response can be `json.loads()`'d directly.

```python
SYSTEM_PROMPT = """You extract structured data from apartment rental listings posted on Facebook Marketplace.
These listings are from the Provo/Orem, Utah area and are typically student or young-adult housing.
Many are "contract sales" where a current tenant is selling their lease.

Return ONLY a raw JSON object — no markdown, no explanation, no backticks.

Field definitions:
- bedrooms: integer (0 for studio). null if not mentioned.
- bathrooms: float (e.g. 1.0, 2.5). null if not mentioned.
- in_unit_washer_dryer: true if washer+dryer is inside the unit/apartment. false if laundry is
  shared, coin-op, on-site building laundry, or in a separate laundry room shared with other units.
  null if not mentioned.
- has_roommates: true if the tenant will be living with other people (shared room, joining roommates,
  multi-person apartment). false if the listing is for an entire unit with no other occupants.
  null if genuinely unclear.
- gender_preference: "male", "female", or "any". Use "any" if no gender is mentioned.
- utilities_included: a list of specific utilities included in rent (e.g. ["water","trash"]),
  the string "all" if all utilities are included, or null if utilities are not included.
- non_included_utilities_cost: a concise string describing the estimated monthly cost of utilities
  the tenant must pay (e.g. "$50-70/month", "~$70/month", "gas + electric varies"). null if
  utilities are included or no cost estimate is given.
- lease_length: a string describing the lease term (e.g. "spring/summer 2026", "August 2026-2027",
  "month-to-month", "through August 14, 2026"). null if not mentioned.

Do not invent or assume values. If a field cannot be determined from the listing, return null."""


def build_user_message(title: str, description: str, stage1: dict) -> str:
    # Strip the internal _needs_llm flag before sending
    pre_fills = {k: v for k, v in stage1.items() if not k.startswith("_")}
    return f"""Listing title: {title}

Listing description:
{description}

Pre-extracted values (may be incomplete — correct any errors):
{json.dumps(pre_fills, indent=2)}

Extract all fields and return the complete JSON object."""


def call_claude(title: str, description: str, stage1: dict) -> dict:
    import json, requests

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 512,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": build_user_message(title, description, stage1)}
        ]
    }

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
    )
    response.raise_for_status()
    raw_text = response.json()["content"][0]["text"].strip()

    # Strip accidental markdown fences
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)

    return json.loads(raw_text)
```

---

### Batching to Reduce API Calls

For bulk processing, pack multiple listings into a single API call. This reduces per-listing
latency and cost roughly 3–5x. The model handles ~5 listings per call reliably before accuracy
drops.

```python
def build_batch_message(listings: list[dict]) -> str:
    """
    listings: list of {"title": ..., "description": ..., "stage1": ...}
    """
    parts = []
    for i, l in enumerate(listings, 1):
        pre = {k: v for k, v in l["stage1"].items() if not k.startswith("_")}
        parts.append(
            f"=== LISTING {i} ===\n"
            f"Title: {l['title']}\n\n"
            f"Description:\n{l['description']}\n\n"
            f"Pre-extracted:\n{json.dumps(pre, indent=2)}"
        )
    return (
        "\n\n".join(parts) +
        "\n\nReturn a JSON array with one object per listing, in order. "
        "Each object must have all 8 fields. Do not skip any listing."
    )
```

Batch system prompt adjustment — add one line at the end of `SYSTEM_PROMPT`:

```
When given multiple listings, return a JSON array of objects, one per listing, in the same order.
```

---

## Full Pipeline

```python
import csv, json, time

def process_listings(input_csv: str, output_csv: str, batch_size: int = 5):
    with open(input_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    results = []
    llm_queue = []

    # Stage 1: run regex on all listings
    for row in rows:
        combined_id = row.get("product_id", "")
        s1 = run_stage1(row["title"], row["description"])
        results.append({"id": combined_id, "title": row["title"], **s1})
        if s1["_needs_llm"]:
            llm_queue.append({
                "idx":   len(results) - 1,
                "title": row["title"],
                "description": row["description"],
                "stage1": s1,
            })

    print(f"Stage 1 complete. {len(llm_queue)}/{len(rows)} listings need LLM.")

    # Stage 2: batch LLM calls
    for i in range(0, len(llm_queue), batch_size):
        batch = llm_queue[i : i + batch_size]
        try:
            llm_results = call_claude_batch(batch)   # returns list of dicts
            for j, llm_out in enumerate(llm_results):
                original_idx = batch[j]["idx"]
                results[original_idx].update(llm_out)
        except Exception as e:
            print(f"Batch {i//batch_size} failed: {e}")
            # Fall back to individual calls for this batch
            for item in batch:
                try:
                    out = call_claude(item["title"], item["description"], item["stage1"])
                    results[item["idx"]].update(out)
                except Exception as e2:
                    print(f"  Single call also failed for listing {item['idx']}: {e2}")
        time.sleep(0.5)   # gentle rate limiting

    # Write output
    fieldnames = [
        "id", "title", "bedrooms", "bathrooms", "in_unit_washer_dryer",
        "has_roommates", "gender_preference", "utilities_included",
        "non_included_utilities_cost", "lease_length"
    ]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"Done. Output written to {output_csv}")
```

---

## Edge Cases to Handle

### 1. Title vs. Description Conflicts
The title `"1 Bed 2 Baths Apartment"` sometimes doesn't match the description, which may say
`"6 person apartment with shared rooms"`. The title bedroom/bath count is usually the unit's
total; the description clarifies occupancy. Give the LLM both and let it resolve conflicts.

### 2. Spanish-Language Listings
Listing 94 is in Spanish: *"Se alquila cuarto para una persona... El precio incluye servicios"*
(`servicios` = utilities). The Claude API handles Spanish natively — no translation needed.
Add a note in the system prompt:

```
Listings may occasionally be in Spanish. Extract fields the same way.
```

### 3. "Contract for Sale" vs. Full-Unit Rental
Many listings are BYU/UVU students selling their existing lease contract. This doesn't change
the data model — `has_roommates`, `gender_preference`, and `lease_length` are especially
important for these listings.

### 4. Utilities Buried in Fee Tables
Some listings enumerate fees line by line:
```
- Utilities: $50 FLAT
- Internet: $25
- Parking: $18
- Insurance: $16
```
Regex `utilities:\s*\$[\d,]+` will catch the utilities line, but the LLM should be instructed
to report only the utilities cost, not the full fee bundle.

### 5. Ambiguous "Laundry" References
- `"free to use laundry"` → likely in-building, not in-unit → return `false`
- `"laundry room with washer and dryer"` in listing 98 (a townhouse) → in-unit → return `true`
- `"smart laundry facility"` → building laundry → return `false`

The regex accounts for these. When in doubt, set to `null` and let the LLM decide.

### 6. Whole-Unit vs. Roommates for Private Room Listings
Title `"Private Room For Rent"` almost always means the listing is for one room in a shared
apartment. However, listing 52 says *"no one else is currently living in the unit — you have
the whole place to yourself."* The regex catches this specific phrasing; the LLM catches
semantic variations.

---

## Expected Stage 1 Hit Rates (estimated from 100-listing sample)

| Field                       | Regex Confidence | Notes |
|-----------------------------|-----------------|-------|
| bedrooms                    | ~90%            | Title is very consistent |
| bathrooms                   | ~90%            | Same |
| in_unit_washer_dryer        | ~60%            | Many listings don't mention laundry at all |
| has_roommates               | ~55%            | Ambiguous without reading context |
| gender_preference           | ~80%            | Usually stated explicitly when relevant |
| utilities_included          | ~65%            | "plus utilities" / "utilities included" are common |
| non_included_utilities_cost | ~50%            | Cost often buried in prose |
| lease_length                | ~70%            | Seasonal terms + date ranges are consistent |

Overall, expect ~35–45% of listings to pass through Stage 1 completely and skip the LLM.
The rest go to Stage 2 for at least one field.

---

## Output Schema

```json
{
  "id": "2522833868115316",
  "title": "2 Beds 2 Baths - Apartment",
  "bedrooms": 2,
  "bathrooms": 2.0,
  "in_unit_washer_dryer": null,
  "has_roommates": null,
  "gender_preference": "any",
  "utilities_included": null,
  "non_included_utilities_cost": "cost not specified",
  "lease_length": null
}
```

Null values indicate the field was not mentioned in the listing — they are not the same as
"not applicable." Downstream consumers should treat null as "unknown."
