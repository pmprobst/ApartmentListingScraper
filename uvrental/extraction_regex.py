"""
Stage 1: Regex-based extraction for apartment listing fields.

Extracts high-confidence values from title + description before Stage 2 (Claude).
See plan/extraction_plan.md for pattern rationale and data observations.
"""

from __future__ import annotations

import os
import re
from typing import Optional


try:
    ROOMMATE_PRICE_THRESHOLD = float(
        os.environ.get("ROOMMATE_PRICE_THRESHOLD", "600")
    )
except (TypeError, ValueError):
    ROOMMATE_PRICE_THRESHOLD = 600.0

def extract_bedrooms(text: str) -> Optional[int]:
    """
    Matches: '2 Beds', '2 bed', '2BR', '2bd', 'Studio', '3x2' (first number)
    """
    if re.search(r"\bstudio\b", text, re.IGNORECASE):
        return 0

    patterns = [
        r"(\d+)\s*bed(?:room)?s?",  # "2 bedrooms", "3 bed"
        r"(\d+)\s*b[rd]\b",  # "2BR", "2bd"
        r"(\d+)x\d",  # "3x2" floor plan notation
        r"(\d+)\s*/\s*\d+\s*ba",  # "2/1ba"
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 0 < val <= 10:
                return val
    return None


def extract_bathrooms(text: str) -> Optional[float]:
    """
    Matches: '2 Baths', '1 Bath', '2.5 Baths', '1ba', '1BA'
    """
    patterns = [
        r"(\d+(?:\.\d)?)\s*bath(?:room)?s?",  # "2 bathrooms", "2.5 bath"
        r"(\d+(?:\.\d)?)\s*ba\b",  # "1ba", "2ba"
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
    shared_patterns = [
        r"(?:shared|building|on[\s\-]?site|coin[\s\-]?op(?:erated)?)\s+laundry",
        r"laundry\s+(?:mat|room\s+shared|(?:is\s+)?shared)",
        r"laundry\s+room\s+shared\s+with",
        r"laundromat",
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
    for p in female_patterns:
        if re.search(p, lower):
            return "female"
    for p in male_patterns:
        if re.search(p, lower):
            return "male"
    return None


def extract_utilities(text: str) -> tuple:
    """
    Returns:
      utilities_included: list of strings | "all" | None
      non_included_cost: string | None
    """
    lower = text.lower()

    # --- ALL utilities included ---
    all_included_patterns = [
        r"\ball\s+utilities\s+included\b",
        r"\butilities\s+(?:are\s+)?included\b",
        r"\bincluding\s+utilities\b",
        r"\brent\s+includes\s+utilities\b",
        r"\butilities\s+included\s+in\s+(?:rent|price)\b",
        r"\bprice\s+includes\s+(?:all\s+)?utilities\b",
        r"\butility\s+fee\s+of\s+\$[\d,]+.*includes\s+all\b",
        r"\$[\d,]+\s*(?:per\s+month|\/mo)?\s+including\s+utilities",
        r"\bflat\s+rate\s+utilities\s+included",
    ]
    for p in all_included_patterns:
        if re.search(p, lower):
            return "all", None

    # --- Specific utilities included ---
    specific_included = []
    utility_keywords = {
        "water": [r"\bwater\b(?:\s+(?:bill|is|are))?\s+included"],
        "sewer": [r"\bsewer\b(?:\s+(?:bill|is|are))?\s+included"],
        "trash": [r"\btrash\b(?:\s+(?:bill|is|are))?\s+included"],
        "gas": [r"\bgas\b(?:\s+(?:bill|is|are))?\s+included"],
        "electric": [r"\b(?:electric(?:ity)?|electric\s+bill)\b\s+included"],
        "internet": [r"\b(?:internet|wifi|wi-fi)\b\s+included"],
    }
    for util, patterns in utility_keywords.items():
        for p in patterns:
            if re.search(p, lower):
                specific_included.append(util)
                break
    if specific_included:
        return specific_included, None

    # --- NOT included + cost mentioned ---
    cost_patterns = [
        r"utilities\s+(?:are\s+|run\s+|come\s+to\s+|around\s+|about\s+|~\s*)?\$[\d,]+(?:\s*[-–]\s*\$?[\d,]+)?",
        r"\$[\d,]+\s*(?:[-–]\s*\$?[\d,]+)?\s*(?:per\s+month\s+)?(?:for\s+)?utilities",
        r"utilities\s+(?:is|are)\s+(?:fixed\s+at\s+|flat\s+|around\s+|about\s+)?\$[\d,]+",
        r"utilities:\s*\$[\d,]+",
        r"\+\s*\$[\d,]+\s*utilities",
        r"usually\s+end\s+up\s+paying\s+(?:a\s+little\s+(?:less|more)\s+than\s+|around\s+|about\s+)?\$[\d,]+",
        r"after\s+utilities\s+(?:it\s+)?comes?\s+to\s+\$[\d,]+",
    ]
    for p in cost_patterns:
        m = re.search(p, lower)
        if m:
            non_included_cost = text[m.start() : m.end()].strip()
            return None, non_included_cost

    # --- Explicit "plus utilities" with no cost ---
    if re.search(r"\+\s*utilities\b|plus\s+utilities\b", lower):
        return None, "cost not specified"

    return None, None


def extract_lease_length(text: str) -> Optional[str]:
    """
    Captures named seasons, academic terms, specific date ranges, and duration strings.
    Returns the matched string for LLM to normalize.
    """
    patterns = [
        r"\d+[\s\-]month\s+lease",
        r"month[\s\-]to[\s\-]month",
        r"m2m\b",
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
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def extract_has_roommates(text: str) -> Optional[bool]:
    """
    Returns True = will have roommates, False = whole unit, None = unclear.
    """
    whole_unit_patterns = [
        r"\bwhole\s+(?:place|unit|apartment)\s+to\s+yourself\b",
        r"\bno\s+one\s+else\s+(?:is\s+)?(?:currently\s+)?living\s+in\s+the\s+unit\b",
        r"\bentire\s+unit\b",
        r"\bwhole\s+unit\b",
        r"\bprivate\s+(?:entrance|basement\s+suite)\b",
        r"\bno\s+roommates?\b",
    ]
    has_roommates_patterns = [
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
    lower = text.lower()
    for p in whole_unit_patterns:
        if re.search(p, lower):
            return False
    for p in has_roommates_patterns:
        if re.search(p, lower):
            return True
    return None


def run_stage1(title: str, description: str, price: float | None = None) -> dict:
    """
    Run regex extraction on title + description.
    Returns dict with extraction fields and _needs_llm flag.
    """
    combined = f"{title}\n{description}"
    beds = extract_bedrooms(combined)
    baths = extract_bathrooms(combined)
    washer = extract_in_unit_washer_dryer(combined)
    gender = extract_gender_preference(combined)
    roommates = extract_has_roommates(combined)
    utilities_inc, util_cost = extract_utilities(combined)
    lease = extract_lease_length(combined)

    if roommates is None and beds is not None and price is not None:
        try:
            p_val = float(price)
        except (TypeError, ValueError):
            p_val = None
        if p_val is not None and beds >= 2 and p_val < ROOMMATE_PRICE_THRESHOLD:
            roommates = True

    return {
        "bedrooms": beds,
        "bathrooms": baths,
        "in_unit_washer_dryer": washer,
        "has_roommates": roommates,
        "gender_preference": gender if gender else "any",
        "utilities_included": utilities_inc,
        "non_included_utilities_cost": util_cost,
        "lease_length": lease,
        "_needs_llm": any(
            v is None for v in [beds, baths, washer, roommates, utilities_inc, lease]
        )
        or util_cost == "cost not specified",
    }
