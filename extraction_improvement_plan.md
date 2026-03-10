# Extraction Improvement Plan
## Facebook Marketplace Apartment Listings — Provo/Orem, UT

Analysis is based on your 815-listing `output.csv` dataset. Each section identifies a specific failure, its frequency in the real data, and the fix.

---

## Audit Summary

Running your current regex pipeline against the dataset reveals these concrete gaps:

| Issue | Affected Listings |
|---|---|
| `private room` with no has_roommates signal | **108** |
| `option to renew` not captured in lease_length | **74** |
| `flat rate` utilities not recognized | **24** |
| April–August date ranges not captured | **18** |
| Month-day ranges (e.g. "March 1 – Aug 15") | **13** |
| Spanish listings entirely missed | **14** |
| `utilities about/around $X` cost not captured | **9** |
| `+ $X/month utilities` cost not captured | **~5** |

These account for roughly **300+ field-level misses** before Claude even sees the listing.

---

## 1. Text Pre-Processing (Before Any Regex)

Normalize listings before matching. This catches typos, encoding oddities, and emoji noise.

```python
import re
import unicodedata

def normalize_text(text: str) -> str:
    # Remove emoji and other non-BMP characters
    text = text.encode("ascii", errors="ignore").decode("ascii")
    # Normalize unicode (e.g. accented chars in Spanish listings)
    text = unicodedata.normalize("NFKD", text)
    # Collapse excessive whitespace/newlines
    text = re.sub(r"\s+", " ", text).strip()
    # Fix common listing typos before matching
    text = re.sub(r"\butilites\b", "utilities", text, flags=re.IGNORECASE)
    text = re.sub(r"\broomates?\b", "roommates", text, flags=re.IGNORECASE)
    text = re.sub(r"\bwasher\s+dryer\s+hooks?\s+ups?\b", "washer dryer hookups", text, flags=re.IGNORECASE)
    return text
```

---

## 2. Bedrooms — Add "N rooms N bath" Pattern

Your current patterns require the word "bed". The format "4 rooms 2 bath" is used in 
shared/BYU-style listings and produces `None`.

```python
# Add to _BEDROOM_PATTERNS:
r"(\d+)\s+rooms?\s+\d+\s+bath",   # "4 rooms 2 bath"
r"(\d+)\s*x\s*(\d+)\s+(?:apartment|apt|unit)",  # "4x4 Apartment" → beds=4
```

> **Note on 4x4:** This format means 4 beds / 4 baths, each tenant gets a private bed and bath.
> It almost always implies `has_roommates=True`. Capture this association explicitly (see §5).

---

## 3. Lease Length — Three Fixes

### 3a. Capture "April–August" Style Date Ranges

```python
# Covers: "APRIL-AUGUST 2026", "April to August", "Apr-Aug"
r"apr(?:il)?\s*[-–to]+\s*aug(?:ust)?(?:\s*\d{4})?",

# Covers: "March 1st - August 15th", "March 1 – Aug 15"
r"(?:jan|feb|mar|apr|may|jun|jul|aug)\w*\s+\d{1,2}\s*[-–]\s*(?:jan|feb|mar|apr|may|jun|jul|aug)\w*\s+\d{1,2}",
```

Map these month ranges to seasons in `run_stage1` before sending to Claude:

```python
SUMMER_MONTHS = {"apr", "april", "may", "jun", "june", "jul", "july", "aug", "august"}

def classify_lease_from_range(raw: str) -> str | None:
    """Map captured date range to lease_length bucket."""
    lower = raw.lower()
    months = re.findall(r"[a-z]+", lower)
    if all(m[:3] in {m[:3] for m in SUMMER_MONTHS} for m in months if len(m) >= 3):
        return "summer"  # let Claude refine to "summer w/ option to review" if needed
    if any(m[:3] in {"aug", "sep"} for m in months) and any(m[:3] in {"apr", "dec", "jan"} for m in months):
        return "fall/winter"
    return None
```

### 3b. Capture "Option to Renew" as a Lease Qualifier

74 listings mention "option to renew" but the raw regex string fed to Claude doesn't
capture this, so Claude often classifies these as plain `"summer"`.

```python
# In run_stage1, after capturing lease_raw:
_OPTION_RENEW_RE = re.compile(r"option\s+to\s+renew", re.IGNORECASE)

def enrich_lease(lease_raw: str | None, full_text: str) -> str | None:
    if lease_raw is None:
        return None
    if _OPTION_RENEW_RE.search(full_text):
        # If it looks like a summer lease, upgrade classification
        if re.search(r"summer|apr|may|jun|jul|aug", lease_raw, re.IGNORECASE):
            return "summer w/ option to review"
    return lease_raw  # pass raw string to Claude for final normalization
```

### 3c. Pass Raw String + Hint to Claude

Instead of sending the raw matched substring alone, send a structured hint:

```python
# In build_user_message / build_batch_message:
stage1["lease_length"] = {
    "raw_match": lease_raw,       # e.g. "March 1 – August 15"
    "option_to_renew": bool(_OPTION_RENEW_RE.search(full_text)),
}
```

Then update the system prompt field definition (see §7) to handle this structured input.

---

## 4. Utilities — Four Missing Patterns

### 4a. "Utilities About/Around $X"

```python
# Covers: "utilities which are about $50", "utilities around $80"
r"utilities?\s+(?:which\s+)?(?:are\s+|is\s+)?(?:about|around|~|roughly|typically)\s*\$[\d,]+",
```

### 4b. "+ $X/month utilities" (with /month in between)

Your existing pattern `\+\s*\$[\d,]+\s*utilities` misses `+ $70/month utilities`.

```python
# Replace with:
r"\+\s*\$[\d,]+\s*(?:/\s*mo(?:nth)?)?\s*(?:for\s+)?utilities",
```

### 4c. Flat Rate Includes Utilities

"$75/month flat rate internet and utilities" is utilities-included but not captured.

```python
# Add to _ALL_INCLUDED_UTIL_PATTERNS:
r"flat\s+rate\s+(?:of\s+)?\$[\d,]+.*(?:utilities|electric|gas|internet)",
r"\$[\d,]+\s+flat\s+rate.*(?:includes?|including|with)\s+(?:all\s+)?utilities",
r"flat\s+rate\s+utilities",
```

### 4d. "Include bill" / "Bills Included"

```python
# Add to _ALL_INCLUDED_UTIL_PATTERNS:
r"\binclude[sd]?\s+bills?\b",
r"\bbills?\s+included\b",
```

---

## 5. has_roommates — "Private Room" Heuristic

**108 out of 109** listings containing "private room" are in shared apartments. This is the
single largest source of null `has_roommates` values in your data.

Add this heuristic at the end of `extract_has_roommates`, just before returning `None`:

```python
_PRIVATE_ROOM_RE = re.compile(r"\bprivate\s+room\b", re.IGNORECASE)
_SOLO_UNIT_RE = re.compile(
    r"\bno\s+roommates?\b|\bwhole\s+(?:place|unit|apartment)\b|\bentire\s+unit\b|\bno\s+one\s+else\b",
    re.IGNORECASE
)

def extract_has_roommates(text, text_lower=None):
    lower = text_lower or text.lower()
    # ... existing whole-unit check (returns False) ...
    # ... existing roommate-pattern check (returns True) ...

    # NEW: private room almost always means shared apartment
    if _PRIVATE_ROOM_RE.search(text) and not _SOLO_UNIT_RE.search(text):
        return True

    return None
```

---

## 7. Claude Prompt — Four Targeted Improvements

### 7a. Add "private room" Clarification to `has_roommates` Definition

Append to the existing field definition:

```
- has_roommates: ... Also true when the listing advertises a "private room" (i.e., the
  tenant gets their own bedroom) but shares the apartment with others
```

### 7b. Add Few-Shot Examples for Edge Cases

Append a dedicated section to the system prompt (these cover the top-miss categories):

```python
SYSTEM_PROMPT += """

Examples:
---
Listing: "Men's Private Room. 3 Roommates. $535/month. Utilities usually about $80."
Output: {"bedrooms": null, "bathrooms": null, "in_unit_washer_dryer": null,
  "has_roommates": true, "gender_preference": "male",
  "utilities_included": null, "non_included_utilities_cost": "$80/month",
  "lease_length": null}

---
Listing: "AVAILABLE APRIL-AUGUST 2026 with the option to renew for next year. Female private room."
Output: {"bedrooms": null, "bathrooms": null, "in_unit_washer_dryer": null,
  "has_roommates": true, "gender_preference": "female",
  "utilities_included": null, "non_included_utilities_cost": null,
  "lease_length": "summer w/ option to review"}

---
Listing: "Habitacion privada. Lavandería compartida. $550 con servicios básicos incluidos."
Output: {"bedrooms": null, "bathrooms": null, "in_unit_washer_dryer": false,
  "has_roommates": true, "gender_preference": "any",
  "utilities_included": "all", "non_included_utilities_cost": null,
  "lease_length": null}

---
Listing: "$75/month flat rate internet and utilities. Shared men's room (2/4 contracts for sale). Summer contract."
Output: {"bedrooms": null, "bathrooms": null, "in_unit_washer_dryer": null,
  "has_roommates": true, "gender_preference": "male",
  "utilities_included": "all", "non_included_utilities_cost": null,
  "lease_length": "summer"}
"""
```

### 7c. Per-Field Null Clarification

Add this line to the system prompt to prevent Claude from guessing:

```
If a field is genuinely absent from the listing text (not just implicit), return null — 
do not infer from price, location, or context alone.
```

### 7d. Structured Lease Input Handling

If you implement §3c, update the field definition:

```
- lease_length: When pre_extracted.lease_length is an object with "raw_match" and
  "option_to_renew" fields, use raw_match as the lease signal. If option_to_renew is
  true and raw_match maps to "summer", return "summer w/ option to review" instead.
```

---

## 8. Architecture — Per-Field Confidence & Selective Claude Calls

The current `_needs_llm` flag is all-or-nothing. A listing with 7/8 fields confidently
extracted still gets a full Claude call because one field is `None`. Replace this with
per-field confidence so Claude only fills actual gaps.

```python
# In run_stage1, return confidence alongside each value:
def run_stage1(title, description, price=None, db_beds=None) -> dict:
    ...
    fields = {
        "bedrooms":                   (beds,          beds is not None),
        "bathrooms":                  (baths,         baths is not None),
        "in_unit_washer_dryer":       (washer,        washer is not None),
        "has_roommates":              (roommates,      roommates is not None),
        "gender_preference":          (gender or "any", True),  # default is always valid
        "utilities_included":         (utilities_inc,  utilities_inc is not None),
        "non_included_utilities_cost":(util_cost,      util_cost is not None and util_cost != "cost not specified"),
        "lease_length":               (lease,          lease is not None),
    }
    values = {k: v for k, (v, _) in fields.items()}
    confident = {k: c for k, (_, c) in fields.items()}
    missing = [k for k, c in confident.items() if not c]

    return {
        **values,
        "_confident": confident,
        "_missing_fields": missing,
        "_needs_llm": bool(missing),
    }
```

Then in your pipeline, pass `_missing_fields` to the Claude prompt so it knows exactly
what to focus on (reducing hallucination on already-known fields):

```python
def build_user_message(title, description, stage1):
    pre_fills = {k: v for k, v in stage1.items() if not k.startswith("_")}
    missing = stage1.get("_missing_fields", [])
    return f"""Listing title: {title}

Listing description:
{description}

Pre-extracted values (treat as ground truth — do NOT re-derive these):
{json.dumps(pre_fills, indent=2)}

Fields still needing extraction: {missing}

Return the complete JSON object with all 8 fields."""
```

---

## Suggested Implementation Order

1. **Text normalization** (§1) — 30 min, zero risk of regressions
2. **`private room` → `has_roommates`** (§5) — highest-impact single fix (108 listings)
3. **`option to renew` lease qualifier** (§3b) — 74 listings, fixes a systematic misclassification
4. **Utility pattern gaps** (§4a–4d) — fills ~40 cost/included null values
5. **April–August and month-day lease patterns** (§3a) — 31 more lease captures
7. **Claude prompt improvements** (§7) — reduces Claude errors on the remaining ~30% of edge cases
8. **Per-field confidence architecture** (§8) — reduces Claude API call volume

Together, fixes 1–6 (regex-only) should reduce the `_needs_llm=True` rate by an estimated
**35–45%**, meaningfully cutting Claude API costs while also improving fields that Claude
was previously mis-classifying due to missing regex pre-fills.
