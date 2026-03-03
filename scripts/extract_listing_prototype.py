import json
import os
import time
from typing import Any, Dict, List

from claude_extraction_prompt import (
    EXAMPLE_INPUT_1,
    EXAMPLE_INPUT_2,
    EXAMPLE_INPUT_3,
    build_extraction_messages,
)


def _example_listings() -> List[Dict[str, Any]]:
    return [
        {
            "title": "Spacious 2BR Apartment near BYU – In-unit Laundry",
            "description": EXAMPLE_INPUT_1,
            "price": 1350,
            "beds": 2,
            "baths": 1,
            "address_raw": "Provo, UT",
        },
        {
            "title": "Private Room in 4BR Student House – Utilities Split",
            "description": EXAMPLE_INPUT_2,
            "price": 650,
            "beds": 1,
            "baths": 1,
            "address_raw": "Orem, UT",
        },
        {
            "title": "Studio Apartment – Downtown Provo",
            "description": EXAMPLE_INPUT_3,
            "price": 900,
            "beds": 0,
            "baths": 1,
            "address_raw": "Provo, UT",
        },
    ]


EXPECTED_KEYS = [
    "washer_dryer",
    "renter_paid_fees",
    "availability",
    "pet_policy",
    "parking",
    "lease_length",
    "deposit",
    "application_fees",
    "furnished",
    "square_footage",
    "roommates",
    "subletting",
    "contact",
    "move_in_incentives",
    "amenities",
    "restrictions",
    "location_detail",
]


def _validate_output(obj: Any) -> None:
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object, got {type(obj)!r}")

    missing = [k for k in EXPECTED_KEYS if k not in obj]
    if missing:
        raise ValueError(f"Missing keys in extraction: {missing}")


def _create_client():
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise SystemExit(
            "anthropic package is not installed. "
            "Run `pip install anthropic` in your environment."
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set in the environment.")

    return Anthropic(api_key=api_key)


def run_prototype(model: str = "claude-3-5-haiku-20241022") -> None:
    client = _create_client()
    listings = _example_listings()

    total_start = time.time()

    for idx, listing in enumerate(listings, start=1):
        print(f"\n=== Listing {idx} ===")
        messages = build_extraction_messages(listing)

        start = time.time()
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0.1,
            messages=messages,
        )
        elapsed = time.time() - start

        # Anthropics Python SDK returns a content list; assume a single text block.
        text_parts = [c.text for c in response.content if getattr(c, "type", "") == "text"]
        raw = "".join(text_parts).strip()

        print(f"Raw JSON response ({elapsed:.2f}s):")
        print(raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Failed to parse JSON: {exc}") from exc

        _validate_output(data)
        print("Parsed and validated JSON keys OK.")

    total_elapsed = time.time() - total_start
    print(f"\nProcessed {len(listings)} listings in {total_elapsed:.2f}s total.")


if __name__ == "__main__":
    run_prototype()

"""
Claude API prototype for structured extraction from rental listing text.

Standalone script — not wired into the pipeline. Run directly to validate
that Claude can reliably extract fields from free-form listing descriptions
and that latency is acceptable for the intended run frequency.

Usage:
    python scripts/extract_listing_prototype.py

Requires:
    ANTHROPIC_API_KEY in .env or environment.
    pip install anthropic>=0.25.0
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
if not ANTHROPIC_API_KEY:
    print(
        "ERROR: ANTHROPIC_API_KEY is not set. "
        "Add it to your .env file or export it before running this script.",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print(
        "ERROR: 'anthropic' package not found. "
        "Run: pip install anthropic>=0.25.0",
        file=sys.stderr,
    )
    sys.exit(1)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Sample listings (hardcoded, varied — exercise all schema paths)
# ---------------------------------------------------------------------------

SAMPLE_LISTINGS = [
    {
        "label": "Dense Provo listing",
        "text": (
            "2BR/1BA apartment in Provo, UT — 850 sqft. Rent: $1,150/mo. "
            "Available August 1st. 12-month lease required. "
            "Washer/dryer hookups in unit. No pets allowed. "
            "Off-street parking included. Security deposit: $1,150 (refundable). "
            "Tenant pays: electricity, gas, internet. "
            "Amenities: dishwasher, central A/C, garbage disposal, on-site laundry. "
            "Entire place — not shared. Landlord-managed. "
            "No smoking, no subletting. Credit and background check required. "
            "Located near BYU campus, walkable to Center Street shops."
        ),
    },
    {
        "label": "Terse Orem shared room",
        "text": (
            "Room for rent near UVU. $550/mo month-to-month. "
            "Cats OK (small). Shared kitchen and bathroom with 2 other roommates. "
            "Text preferred. Move in ASAP."
        ),
    },
    {
        "label": "Springville property manager",
        "text": (
            "Fully furnished 1BR/1BA in Springville. $975/mo. "
            "First month free for move-in before April 15! "
            "Garage parking available for $75/mo extra. "
            "Professionally managed by Canyon Property Group. "
            "Email for showings. Application fee $40. "
            "6-month or 12-month lease. Pets negotiable with deposit. "
            "No smoking. Credit check required."
        ),
    },
]

# ---------------------------------------------------------------------------
# Tool definition (17 fields, all optional)
# ---------------------------------------------------------------------------

EXTRACT_TOOL = {
    "name": "extract_listing_fields",
    "description": (
        "Extract structured rental listing fields from free-form listing text. "
        "Set a field to null if the information is not mentioned. Never guess."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "washer_dryer": {
                "type": ["string", "null"],
                "enum": ["in_unit", "hookups", "not_mentioned", None],
                "description": "Washer/dryer situation: in_unit (machines provided), hookups (connections only), or not_mentioned.",
            },
            "renter_paid_fees": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "List of utilities or fees the renter must pay (e.g. electricity, gas, internet). Empty list if none mentioned.",
            },
            "availability": {
                "type": ["string", "null"],
                "description": "Move-in date or availability description as written in the listing.",
            },
            "pet_policy": {
                "type": ["object", "null"],
                "properties": {
                    "cats_allowed": {"type": ["boolean", "null"]},
                    "dogs_allowed": {"type": ["boolean", "null"]},
                    "deposit": {"type": ["number", "null"]},
                    "monthly_pet_rent": {"type": ["number", "null"]},
                    "restrictions": {"type": ["string", "null"]},
                },
                "description": "Pet policy details. Null if pets not mentioned.",
            },
            "parking": {
                "type": ["string", "null"],
                "enum": ["included", "assigned", "garage", "street", "extra_cost", None],
                "description": "Parking situation.",
            },
            "lease_length": {
                "type": ["string", "null"],
                "enum": ["month_to_month", "6_month", "12_month", "unspecified", None],
                "description": "Lease length.",
            },
            "deposit": {
                "type": ["object", "null"],
                "properties": {
                    "amount": {"type": ["number", "null"]},
                    "refundable": {"type": ["boolean", "null"]},
                    "last_month_required": {"type": ["boolean", "null"]},
                },
                "description": "Security deposit details. Null if not mentioned.",
            },
            "application_fees": {
                "type": ["number", "null"],
                "description": "Application fee in USD. Null if not mentioned.",
            },
            "furnished": {
                "type": ["string", "null"],
                "enum": ["fully", "partial", "unfurnished", None],
                "description": "Furnished status.",
            },
            "sqft": {
                "type": ["integer", "null"],
                "description": "Square footage. Null if not mentioned.",
            },
            "layout": {
                "type": ["object", "null"],
                "properties": {
                    "type": {
                        "type": ["string", "null"],
                        "enum": ["entire_place", "shared", None],
                    },
                    "roommates": {"type": ["integer", "null"]},
                },
                "description": "Layout type (entire vs shared) and number of roommates if shared.",
            },
            "subletting": {
                "type": ["boolean", "null"],
                "description": "Whether subletting is allowed. Null if not mentioned.",
            },
            "contact": {
                "type": ["object", "null"],
                "properties": {
                    "contact_type": {
                        "type": ["string", "null"],
                        "enum": ["landlord", "property_manager", None],
                    },
                    "preferred_contact": {"type": ["string", "null"]},
                },
                "description": "Contact information. Null if not mentioned.",
            },
            "move_in_incentives": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "Move-in incentives (e.g. first month free). Empty list if none mentioned.",
            },
            "amenities": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "List of amenities mentioned. Empty list if none.",
            },
            "restrictions": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "Restrictions (e.g. no smoking, no subletting, credit check required). Empty list if none.",
            },
            "location_detail": {
                "type": ["string", "null"],
                "description": "Location details or nearby landmarks as mentioned.",
            },
        },
    },
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a rental listing data extractor. "
    "Call the extract_listing_fields tool exactly once with values drawn strictly "
    "from the provided listing text. "
    "Rules:\n"
    "- Set a field to null if the information is not mentioned. Never guess or infer.\n"
    "- Enum fields: use only the allowed values listed in the schema, or null.\n"
    "- Array fields: use [] if the category exists but nothing is listed; "
    "null only if truly indeterminate.\n"
    "- Leave date/availability strings as-is; do not reformat them.\n"
    "- No prose outside the tool call."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_TYPES: dict[str, type | tuple] = {
    "washer_dryer": (str, type(None)),
    "renter_paid_fees": (list, type(None)),
    "availability": (str, type(None)),
    "pet_policy": (dict, type(None)),
    "parking": (str, type(None)),
    "lease_length": (str, type(None)),
    "deposit": (dict, type(None)),
    "application_fees": (int, float, type(None)),
    "furnished": (str, type(None)),
    "sqft": (int, type(None)),
    "layout": (dict, type(None)),
    "subletting": (bool, type(None)),
    "contact": (dict, type(None)),
    "move_in_incentives": (list, type(None)),
    "amenities": (list, type(None)),
    "restrictions": (list, type(None)),
    "location_detail": (str, type(None)),
}


def _build_user_message(text: str) -> str:
    return f"Extract structured fields from this rental listing:\n\n{text}"


def _call_claude(text: str) -> tuple[dict, float]:
    """Call Claude with forced tool use. Returns (extracted_dict, latency_seconds)."""
    t0 = time.monotonic()
    response = _client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_listing_fields"},
        messages=[{"role": "user", "content": _build_user_message(text)}],
    )
    latency = time.monotonic() - t0
    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise ValueError(f"No tool_use block in response. Stop reason: {response.stop_reason}")
    return tool_block.input, latency


def _validate_shape(result: dict) -> list[str]:
    """
    Soft validation — returns a list of warning strings, never raises.
    Checks each field's type and flags unexpected keys.
    """
    warnings: list[str] = []
    known_keys = set(_EXPECTED_TYPES.keys())
    for key in result:
        if key not in known_keys:
            warnings.append(f"Unexpected key: '{key}'")
    for field, expected in _EXPECTED_TYPES.items():
        val = result.get(field)
        if val is None:
            continue  # null is always acceptable
        if not isinstance(val, expected):
            warnings.append(
                f"Field '{field}': expected {expected}, got {type(val).__name__}"
            )
    return warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"Model: {MODEL}")
    print(f"Listings to process: {len(SAMPLE_LISTINGS)}")
    print("=" * 60)

    total_latency = 0.0
    all_warnings: list[list[str]] = []

    for i, listing in enumerate(SAMPLE_LISTINGS, start=1):
        label = listing["label"]
        text = listing["text"]

        print(f"\n[{i}/{len(SAMPLE_LISTINGS)}] {label}")
        print("-" * 50)

        extracted, latency = _call_claude(text)
        total_latency += latency

        print(f"Latency: {latency:.2f}s")
        print("Extracted fields:")
        print(json.dumps(extracted, indent=2))

        warnings = _validate_shape(extracted)
        all_warnings.append(warnings)
        if warnings:
            print(f"Validation: {len(warnings)} warning(s):")
            for w in warnings:
                print(f"  - {w}")
        else:
            print("Validation: OK (no shape issues)")

    avg_latency = total_latency / len(SAMPLE_LISTINGS)
    passed = sum(1 for w in all_warnings if not w)
    failed = len(SAMPLE_LISTINGS) - passed

    print()
    print("=" * 60)
    print(
        f"Done. Total latency: {total_latency:.2f}s across {len(SAMPLE_LISTINGS)} listing(s)."
    )
    print(f"Average latency: {avg_latency:.2f}s per listing.")
    if failed == 0:
        print("Validation result: ALL PASSED")
    else:
        print(f"Validation result: {failed} listing(s) had shape warnings.")


if __name__ == "__main__":
    main()
