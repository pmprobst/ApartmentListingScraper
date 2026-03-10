"""
Regex-based extraction for apartment listing fields.

Extracts high-confidence values from title + description before Claude extraction.
See ARCHITECTURE.md for extraction pipeline.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Optional


def normalize_text(text: str) -> str:
    """
    Normalize listing text before matching: remove emoji, fix unicode,
    collapse whitespace, fix common typos.
    """
    text = text.encode("ascii", errors="ignore").decode("ascii")
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\butilites\b", "utilities", text, flags=re.IGNORECASE)
    text = re.sub(r"\broomates?\b", "roommates", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\bwasher\s+dryer\s+hooks?\s+ups?\b",
        "washer dryer hookups",
        text,
        flags=re.IGNORECASE,
    )
    return text


try:
    ROOMMATE_PRICE_THRESHOLD = float(
        os.environ.get("ROOMMATE_PRICE_THRESHOLD", "600")
    )
except (TypeError, ValueError):
    ROOMMATE_PRICE_THRESHOLD = 600.0

# Pre-compiled regexes (used by extractors below)
_STUDIO_RE = re.compile(r"\bstudio\b", re.IGNORECASE)
_BEDROOM_PATTERNS = [
    r"(\d+)\s*bed(?:room)?s?",
    r"(\d+)\s*b[rd]\b",
    r"(\d+)x\d",
    r"(\d+)\s*/\s*\d+\s*ba",
    r"(\d+)\s+rooms?\s+\d+\s+bath",
    r"(\d+)\s*x\s*\d+\s+(?:apartment|apt|unit)",
]
_COMPILED_BEDROOM = [re.compile(p, re.IGNORECASE) for p in _BEDROOM_PATTERNS]

_BATHROOM_PATTERNS = [
    r"(\d+(?:\.\d)?)\s*bath(?:room)?s?",
    r"(\d+(?:\.\d)?)\s*ba\b",
]
_COMPILED_BATHROOM = [re.compile(p, re.IGNORECASE) for p in _BATHROOM_PATTERNS]

_IN_UNIT_WD_PATTERNS = [
    r"in[\s\-]?unit\s+(?:washer|laundry)",
    r"washer\s*(?:and|&|/)\s*dryer\s+in\s+(?:unit|apartment|apt|home|the\s+unit)",
    r"in[\s\-]?unit\s+washer",
    r"in\s+house\s+washer",
    r"in[\s\-]unit\s+laundry",
    r"laundry\s+in\s+(?:unit|apartment|apt)",
    r"washer\s*(?:and|&|/)\s*dryer\s+(?:provided|included|hookups?\s+in)",
    r"laundry\s+room\s+with\s+washer\s+and\s+dryer",
    r"private\s+laundry",
]
_SHARED_WD_PATTERNS = [
    r"(?:shared|building|on[\s\-]?site|coin[\s\-]?op(?:erated)?)\s+laundry",
    r"laundry\s+(?:mat|room\s+shared|(?:is\s+)?shared)",
    r"laundry\s+room\s+shared\s+with",
    r"laundromat",
]
_COMPILED_IN_UNIT_WD = [re.compile(p) for p in _IN_UNIT_WD_PATTERNS]
_COMPILED_SHARED_WD = [re.compile(p) for p in _SHARED_WD_PATTERNS]

_FEMALE_PATTERNS = [
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
_MALE_PATTERNS = [
    r"\bmen(?:'s)?\s+(?:housing|apartment|contract|only|room|lease|shared|contact|spot)",
    r"\bmale\s+(?:housing|apartment|only|BYU|room|roommate|student)",
    r"\bfor\s+(?:a\s+)?(?:man|male|guy)\b",
    r"\blooking\s+for\s+(?:a\s+)?(?:man|male|guy)",
    r"\bmale[\s\-]only\b",
    r"\bsingle\s+male\s+room\b",
    r"\broom\s+for\s+a\s+man\b",
]
_COMPILED_FEMALE = [re.compile(p) for p in _FEMALE_PATTERNS]
_COMPILED_MALE = [re.compile(p) for p in _MALE_PATTERNS]

_ALL_INCLUDED_UTIL_PATTERNS = [
    r"\ball\s+utilities\s+included\b",
    r"\butilities\s+(?:are\s+)?included\b",
    r"\bincluding\s+utilities\b",
    r"\brent\s+includes\s+utilities\b",
    r"\butilities\s+included\s+in\s+(?:rent|price)\b",
    r"\bprice\s+includes\s+(?:all\s+)?utilities\b",
    r"\butility\s+fee\s+of\s+\$[\d,]+.*includes\s+all\b",
    r"\$[\d,]+\s*(?:per\s+month|\/mo)?\s+including\s+utilities",
    r"\bflat\s+rate\s+utilities\s+included",
    r"flat\s+rate\s+(?:of\s+)?\$[\d,]+.*(?:utilities|electric|gas|internet)",
    r"\$[\d,]+\s+flat\s+rate.*(?:includes?|including|with)\s+(?:all\s+)?utilities",
    r"\$[\d,]+\s+flat\s+rate.*(?:utilities|electric|gas|internet)",
    r"flat\s+rate\s+utilities",
    r"\binclude[sd]?\s+bills?\b",
    r"\bbills?\s+included\b",
]
_COMPILED_ALL_INCLUDED_UTIL = [re.compile(p) for p in _ALL_INCLUDED_UTIL_PATTERNS]

_UTIL_KEYWORD_PATTERNS = [
    (r"\bwater\b(?:\s+(?:bill|is|are))?\s+included", "water"),
    (r"\bsewer\b(?:\s+(?:bill|is|are))?\s+included", "sewer"),
    (r"\btrash\b(?:\s+(?:bill|is|are))?\s+included", "trash"),
    (r"\bgas\b(?:\s+(?:bill|is|are))?\s+included", "gas"),
    (r"\b(?:electric(?:ity)?|electric\s+bill)\b\s+included", "electric"),
    (r"\b(?:internet|wifi|wi-fi)\b\s+included", "internet"),
]
_COMPILED_UTIL_KEYWORDS = [(re.compile(p), util) for p, util in _UTIL_KEYWORD_PATTERNS]

_COST_UTIL_PATTERNS = [
    r"utilities\s+(?:are\s+|run\s+|come\s+to\s+|around\s+|about\s+|~\s*)?\$[\d,]+(?:\s*[-–]\s*\$?[\d,]+)?",
    r"utilities?\s+(?:which\s+)?(?:are\s+|is\s+)?(?:about|around|~|roughly|typically)\s*\$[\d,]+",
    r"\$[\d,]+\s*(?:[-–]\s*\$?[\d,]+)?\s*(?:per\s+month\s+)?(?:for\s+)?utilities",
    r"utilities\s+(?:is|are)\s+(?:fixed\s+at\s+|flat\s+|around\s+|about\s+)?\$[\d,]+",
    r"utilities:\s*\$[\d,]+",
    r"\+\s*\$[\d,]+\s*(?:/\s*mo(?:nth)?)?\s*(?:for\s+)?utilities",
    r"usually\s+end\s+up\s+paying\s+(?:a\s+little\s+(?:less|more)\s+than\s+|around\s+|about\s+)?\$[\d,]+",
    r"after\s+utilities\s+(?:it\s+)?comes?\s+to\s+\$[\d,]+",
]
_COMPILED_COST_UTIL = [re.compile(p) for p in _COST_UTIL_PATTERNS]
_PLUS_UTILITIES_RE = re.compile(r"\+\s*utilities\b|plus\s+utilities\b")

_LEASE_PATTERNS = [
    r"\d+[\s\-]month\s+lease",
    r"month[\s\-]to[\s\-]month",
    r"m2m\b",
    r"apr(?:il)?\s*[-–to]+\s*aug(?:ust)?(?:\s*\d{4})?",
    r"(?:jan|feb|mar|apr|may|jun|jul|aug)\w*\s+\d{1,2}\s*[-–]\s*(?:jan|feb|mar|apr|may|jun|jul|aug)\w*\s+\d{1,2}",
    r"spring\s*(?:/|and|&|[-–])?\s*summer(?:\s+\d{4})?",
    r"fall\s*(?:/|and|&|[-–])?\s*winter(?:\s+\d{4})?",
    r"year[\s\-]round",
    r"20\d{2}[\s\-–/]+20\d{2}",
    r"(?:through|until|thru|ends?(?:\s+mid)?)\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|"
    r"Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)(?:\s+\d{1,2}(?:st|nd|rd|th)?)?(?:,?\s*20\d{2})?",
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?"
    r"\s*[-–]\s*(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?",
]
_COMPILED_LEASE = [re.compile(p, re.IGNORECASE) for p in _LEASE_PATTERNS]

_WHOLE_UNIT_PATTERNS = [
    r"\bwhole\s+(?:place|unit|apartment)\s+to\s+yourself\b",
    r"\bno\s+one\s+else\s+(?:is\s+)?(?:currently\s+)?living\s+in\s+the\s+unit\b",
    r"\bentire\s+unit\b",
    r"\bwhole\s+unit\b",
    r"\bprivate\s+(?:entrance|basement\s+suite)\b",
    r"\bno\s+roommates?\b",
]
_HAS_ROOMMATES_PATTERNS = [
    r"\bshared\s+room\b",
    r"\bshare\s+room\b",
    r"\bshared\s+(?:female|male|bedroom|bedrooms|apartment)\b",
    r"\b\d+\s+(?:existing\s+)?roommates?\b",
    r"\b\d+\s+(?:great\s+|clean\s+|fun\s+)?roommates?\s+staying\b",
    r"\b(?:two|three|four|five|six)\s+(?:other\s+)?roommates?\b",
    r"\b\d+\s*(?:person|people|man|guys?|girls?|women|men)\s+apartment\b",
    r"\b(?:other\s+)?roommates?\s+(?:are\s+)?(?:very|super|so\s+)?(?:great|sweet|fun|clean|amazing|chill)\b",
    r"\bjoining\b.*\broommates?\b",
    r"\bsharing\s+with\s+(?:a\s+few\s+)?\w+",
    r"\b\d+\s+tenants?\s+total\b",
    r"\b\d+\s+(?:spots?|spaces?|openings?)\s+available\b",
    r"\bsplit\s+between\s+\d+\s+roommates?\b",
    r"\broommate\s+matching\b",
    r"\bselling\s+(?:my|a|one|their)\s+(?:spot|contract)\b",
    r"\bsubleasing\s+(?:my|a)\s+contract\b",
    r"\bpeople\s+in\s+(?:my|the|this)\s+apartment\b",
    r"\bmove\s+(?:here\s+)?with\s+a\s+(?:buddy|friend)\b",
]
_COMPILED_WHOLE_UNIT = [re.compile(p) for p in _WHOLE_UNIT_PATTERNS]
_COMPILED_HAS_ROOMMATES = [re.compile(p) for p in _HAS_ROOMMATES_PATTERNS]

_OPTION_RENEW_RE = re.compile(r"option\s+to\s+renew", re.IGNORECASE)
_PRIVATE_ROOM_RE = re.compile(r"\bprivate\s+room\b", re.IGNORECASE)
_SOLO_UNIT_RE = re.compile(
    r"\bno\s+roommates?\b|\bwhole\s+(?:place|unit|apartment)\b|\bentire\s+unit\b|\bno\s+one\s+else\b",
    re.IGNORECASE,
)


def extract_bedrooms(text: str) -> Optional[int]:
    """
    Matches: '2 Beds', '2 bed', '2BR', '2bd', 'Studio', '3x2' (first number)
    """
    if _STUDIO_RE.search(text):
        return 0
    for pat in _COMPILED_BEDROOM:
        m = pat.search(text)
        if m:
            val = int(m.group(1))
            if 0 < val <= 10:
                return val
    return None


def extract_bathrooms(text: str) -> Optional[float]:
    """
    Matches: '2 Baths', '1 Bath', '2.5 Baths', '1ba', '1BA'
    """
    for pat in _COMPILED_BATHROOM:
        m = pat.search(text)
        if m:
            val = float(m.group(1))
            if 0 < val <= 10:
                return val
    return None


def extract_in_unit_washer_dryer(
    text: str, text_lower: str | None = None
) -> Optional[bool]:
    """
    Returns True for in-unit, False for shared/building/coin-op, None if unmentioned.
    Order matters: check in-unit patterns FIRST, then negatives.
    """
    lower = text_lower if text_lower is not None else text.lower()
    for pat in _COMPILED_IN_UNIT_WD:
        if pat.search(lower):
            return True
    for pat in _COMPILED_SHARED_WD:
        if pat.search(lower):
            return False
    return None


def extract_gender_preference(
    text: str, text_lower: str | None = None
) -> Optional[str]:
    """
    Returns 'male', 'female', or None (caller should default None → 'any').
    """
    lower = text_lower if text_lower is not None else text.lower()
    for pat in _COMPILED_FEMALE:
        if pat.search(lower):
            return "female"
    for pat in _COMPILED_MALE:
        if pat.search(lower):
            return "male"
    return None


def extract_utilities(
    text: str, text_lower: str | None = None
) -> tuple:
    """
    Returns:
      utilities_included: list of strings | "all" | None
      non_included_cost: string | None
    """
    lower = text_lower if text_lower is not None else text.lower()

    for pat in _COMPILED_ALL_INCLUDED_UTIL:
        if pat.search(lower):
            return "all", None

    specific_included = []
    for pat, util in _COMPILED_UTIL_KEYWORDS:
        if pat.search(lower):
            specific_included.append(util)
    if specific_included:
        return specific_included, None

    for pat in _COMPILED_COST_UTIL:
        m = pat.search(lower)
        if m:
            non_included_cost = text[m.start() : m.end()].strip()
            return None, non_included_cost

    if _PLUS_UTILITIES_RE.search(lower):
        return None, "cost not specified"

    return None, None


def extract_lease_length(text: str) -> Optional[str]:
    """
    Captures named seasons, academic terms, specific date ranges, and duration strings.
    Returns the matched string for LLM to normalize.
    """
    for pat in _COMPILED_LEASE:
        m = pat.search(text)
        if m:
            return m.group(0).strip()
    return None


def _enrich_lease(lease_raw: str | None, full_text: str) -> str | None:
    """
    If lease looks like summer and listing mentions "option to renew",
    upgrade to "summer w/ option to review" for Claude to use.
    """
    if lease_raw is None:
        return None
    if _OPTION_RENEW_RE.search(full_text):
        if re.search(r"summer|apr|may|jun|jul|aug", lease_raw, re.IGNORECASE):
            return "summer w/ option to review"
    return lease_raw


def extract_has_roommates(
    text: str, text_lower: str | None = None
) -> Optional[bool]:
    """
    Returns True = will have roommates, False = whole unit, None = unclear.
    Private room (without explicit whole-unit language) almost always means shared.
    """
    lower = text_lower if text_lower is not None else text.lower()
    for pat in _COMPILED_WHOLE_UNIT:
        if pat.search(lower):
            return False
    for pat in _COMPILED_HAS_ROOMMATES:
        if pat.search(lower):
            return True
    if _PRIVATE_ROOM_RE.search(text) and not _SOLO_UNIT_RE.search(text):
        return True
    return None


def run_stage1(
    title: str,
    description: str,
    price: float | None = None,
    db_beds: float | None = None,
) -> dict:
    """
    Run regex extraction on title + description.
    Returns dict with extraction fields, _confident, _missing_fields, and _needs_llm.
    """
    combined = normalize_text(f"{title}\n{description}")
    combined_lower = combined.lower()

    regex_beds = extract_bedrooms(combined)
    beds = regex_beds if regex_beds is not None else db_beds
    baths = extract_bathrooms(combined)
    washer = extract_in_unit_washer_dryer(combined, text_lower=combined_lower)
    gender = extract_gender_preference(combined, text_lower=combined_lower)
    roommates = extract_has_roommates(combined, text_lower=combined_lower)
    utilities_inc, util_cost = extract_utilities(combined, text_lower=combined_lower)
    lease_raw = extract_lease_length(combined)
    lease = _enrich_lease(lease_raw, combined)

    if roommates is None and beds is not None and price is not None:
        try:
            p_val = float(price)
        except (TypeError, ValueError):
            p_val = None
        if p_val is not None and beds >= 2 and p_val < ROOMMATE_PRICE_THRESHOLD:
            roommates = True

    fields = {
        "bedrooms": (beds, beds is not None),
        "bathrooms": (baths, baths is not None),
        "in_unit_washer_dryer": (washer, washer is not None),
        "has_roommates": (roommates, roommates is not None),
        "gender_preference": (gender if gender else "any", True),
        "utilities_included": (utilities_inc, utilities_inc is not None),
        "non_included_utilities_cost": (
            util_cost,
            util_cost is not None and util_cost != "cost not specified",
        ),
        "lease_length": (lease, lease is not None),
    }
    values = {k: v for k, (v, _) in fields.items()}
    confident = {k: c for k, (_, c) in fields.items()}
    missing = [k for k, c in confident.items() if not c]
    needs_llm = bool(missing)

    return {
        **values,
        "_confident": confident,
        "_missing_fields": missing,
        "_needs_llm": needs_llm,
    }
