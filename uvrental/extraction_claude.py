"""
Claude API extraction for apartment listing fields.

Called when Stage 1 regex leaves fields unknown. Injects Stage 1 pre-fills
into the prompt so the model doesn't re-derive what regex already found.
See ARCHITECTURE.md for extraction pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You extract structured data from apartment rental listings posted on Facebook Marketplace.
These listings are from the Provo/Orem, Utah area and are typically student or young-adult housing.
Many are "contract sales" where a current tenant is selling their lease.

Listings may occasionally be in Spanish. Extract fields the same way.

Return ONLY a raw JSON object — no markdown, no explanation, no backticks.

Field definitions:
- bedrooms: integer (0 for studio). null if not mentioned.
- bathrooms: float (e.g. 1.0, 2.5). null if not mentioned.
- in_unit_washer_dryer: true if washer+dryer is inside the unit/apartment. false if laundry is
  shared, coin-op, on-site building laundry, or in a separate laundry room shared with other units.
  null if not mentioned.
- has_roommates: true if the tenant will be living with other people (shared room, joining roommates,
  multi-person apartment). Also true for BYU/UVU "contract sales" where someone is selling their
  spot in an existing shared apartment, or when language implies other tenants (e.g. "sharing with",
  "people in my apartment", "tenants total", "spots available", "move here with a buddy").
  false if the listing is for an entire unit with no other occupants (e.g. "no roommates",
  "whole place to yourself"). null if genuinely unclear.
- gender_preference: "male", "female", or "any". Use "any" if no gender is mentioned.
- utilities_included: a list of specific utilities included in rent (e.g. ["water","trash"]),
  the string "all" if all utilities are included, or null if utilities are not included.
- non_included_utilities_cost: a concise string giving a single estimated total monthly cost
  for all utilities the tenant must pay that are not included in rent. If multiple fees or per-utility
  amounts are mentioned, convert them into one approximate monthly total (e.g. "$120/month" or
  "$80-100/month") rather than listing separate items. null if utilities are included or no cost
  estimate is given.
- lease_length: exactly one of these strings, or null if not mentioned or not confidently mappable:
  "summer", "summer w/ option to review", "fall/winter".
  Map listing language to the closest match (e.g. "spring/summer", "summer only", "April-August" → "summer";
  "fall/winter", "August-May", "academic year" → "fall/winter"; summer with renewal option → "summer w/ option to review").
  If the lease term does not clearly fit one of these categories, return null.

When given multiple listings, return a JSON array of objects, one per listing, in the same order.

Do not invent or assume values. If a field cannot be determined from the listing, return null."""


def _load_client():
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic package is not installed. Run `pip install anthropic>=0.25.0`."
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    from .config import get_claude_timeout

    timeout = get_claude_timeout()
    return anthropic.Anthropic(timeout=timeout)


def _model_name() -> str:
    from .config import get_claude_model

    return get_claude_model()


def build_user_message(title: str, description: str, stage1: dict) -> str:
    pre_fills = {k: v for k, v in stage1.items() if not k.startswith("_")}
    return f"""Listing title: {title}

Listing description:
{description}

Pre-extracted values (may be incomplete — correct any errors):
{json.dumps(pre_fills, indent=2)}

Extract all fields and return the complete JSON object."""


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
        "\n\n".join(parts)
        + "\n\nReturn a JSON array with one object per listing, in order. "
        "Each object must have all 8 fields. Do not skip any listing."
    )


def _parse_response(raw_text: str, expect_array: bool = False) -> Any:
    raw_text = raw_text.strip()
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)
    parsed = json.loads(raw_text)
    return parsed


def call_claude(title: str, description: str, stage1: dict) -> dict:
    """Single-listing Claude extraction. Returns dict with 8 fields."""
    client = _load_client()
    content = build_user_message(title, description, stage1)
    try:
        response = client.messages.create(
            model=_model_name(),
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        log.error("Claude API error (single listing): %s", e)
        raise
    text_parts = [
        getattr(c, "text", "")
        for c in getattr(response, "content", [])
        if getattr(c, "type", "") == "text"
    ]
    raw = "".join(text_parts).strip()
    return _parse_response(raw)


def call_claude_batch(listings: list[dict]) -> list[dict]:
    """
    Batch Claude extraction. listings: list of {"title", "description", "stage1"}.
    Returns list of dicts with 8 fields each, in same order.
    """
    if not listings:
        return []

    client = _load_client()
    content = build_batch_message(listings)
    try:
        response = client.messages.create(
            model=_model_name(),
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        log.error("Claude API error (batch): %s", e)
        raise
    text_parts = [
        getattr(c, "text", "")
        for c in getattr(response, "content", [])
        if getattr(c, "type", "") == "text"
    ]
    raw = "".join(text_parts).strip()
    parsed = _parse_response(raw, expect_array=True)
    if isinstance(parsed, list):
        return parsed
    return [parsed]
