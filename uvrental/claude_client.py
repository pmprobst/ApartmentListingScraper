"""
Claude client wrapper for extracting structured fields from rental listings.

This module is designed so the rest of the pipeline can call a single
function with listing text and receive a small, JSON-serializable dict
matching `ClaudeExtraction` from `claude_schema`.

It does NOT wire into the main pipeline yet; that orchestration step is kept
separate so you can experiment with prompts and models without touching the
core ingestion logic.
"""

from __future__ import annotations

import json
import os
import time
from textwrap import dedent
from typing import Any, Mapping, Optional, Tuple

from dotenv import load_dotenv

from .claude_schema import ClaudeExtraction

load_dotenv()


_DEFAULT_MODEL = ""  # require explicit CLAUDE_MODEL to avoid retired/default models
_MODEL_ENV = "CLAUDE_MODEL"


EXTRACTION_FIELD_DOC = dedent(
    """
    You must extract the following fields from the listing description.
    Use null or the explicit "not_mentioned" enum when a field is not clearly
    specified. Do not guess based only on price or city.

    Fields:

    - washer_dryer (string or null):
      One of: "in_unit", "hookups_only", "shared_laundry",
      "laundry_in_building", "coin_op_on_site", "no_laundry", "not_mentioned".

    - renter_paid_fees (array of strings or null):
      Recurring utility costs the renter must pay in addition to base rent.
      Examples: ["electricity", "gas", "internet"]. Use [] if the text says
      something like "all utilities included". Use null when utilities are
      not mentioned at all.

    - availability (string or null):
      Short phrase like "ASAP", "March 1, 2026", "mid-March".

    - pet_policy (string or null):
      Short summary of which pets are allowed, deposits, and monthly pet rent.

    - roommates (string or null):
      Short summary such as "entire_unit",
      "private_room_in_3br_with_2_roommates",
      "shared_room", or "unspecified".
    """
).strip()


def _system_prompt() -> str:
    return (
        "You are a careful information extraction assistant for rental listings. "
        "You read listing text (title + description and simple metadata) and "
        "output strictly valid JSON according to the given schema. "
        "If something is not clearly stated, use null or the explicit "
        '"not_mentioned" enum instead of guessing.\n\n'
        "Rules:\n"
        "- Return exactly one JSON object.\n"
        "- Do not include any explanation, comments, or extra keys.\n"
        "- Keys must match the schema exactly.\n"
        "- JSON must be valid: no trailing commas, no code fences, no backticks.\n"
    )


def _build_user_content(
    *,
    title: str,
    description: str,
    price: Any = None,
    beds: Any = None,
    baths: Any = None,
    address_raw: str | None = None,
) -> str:
    """Build the user message content for a single listing."""
    metadata_lines: list[str] = []
    if price is not None:
        metadata_lines.append(f"price: {price}")
    if beds is not None:
        metadata_lines.append(f"beds: {beds}")
    if baths is not None:
        metadata_lines.append(f"baths: {baths}")
    if address_raw:
        metadata_lines.append(f"address_raw: {address_raw}")
    if not metadata_lines:
        metadata_lines.append("price: unknown")

    metadata_block = "\n".join(metadata_lines)

    return dedent(
        f"""
        You are an information extraction assistant for rental listings in
        Utah Valley. Extract structured details conservatively from the text
        below. If something is not clearly stated, use null or "not_mentioned"
        instead of guessing.

        {EXTRACTION_FIELD_DOC}

        Listing to analyze:

        TITLE:
        {title.strip()}

        METADATA:
        {metadata_block}

        DESCRIPTION:
        {description.strip()}
        """
    ).strip()


def _load_client():
    try:
        import anthropic  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - import-time guard
        raise RuntimeError(
            "anthropic package is not installed. "
            "Run `pip install anthropic>=0.25.0` in your environment."
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file or export it before running extraction."
        )

    return anthropic.Anthropic(api_key=api_key)


def _model_name() -> str:
    name = os.environ.get(_MODEL_ENV, _DEFAULT_MODEL).strip()
    if not name:
        raise RuntimeError(
            "CLAUDE_MODEL is not set. Please set it to a valid Anthropic "
            "model identifier in your environment (for example, one of the "
            "current Claude Sonnet/Haiku models listed in the Anthropic "
            "API docs)."
        )
    return name


def extract_from_text(
    *,
    title: str,
    description: str,
    price: Any = None,
    beds: Any = None,
    baths: Any = None,
    address_raw: str | None = None,
    max_tokens: int = 512,
) -> Tuple[Optional[ClaudeExtraction], float]:
    """
    Call Claude to extract structured fields from a single listing text.

    Returns (extracted_data, latency_seconds). extracted_data is a dict
    matching ClaudeExtraction, or None on error.
    """
    client = _load_client()
    messages = [
        {
            "role": "user",
            "content": _build_user_content(
                title=title,
                description=description,
                price=price,
                beds=beds,
                baths=baths,
                address_raw=address_raw,
            ),
        }
    ]

    model = _model_name()

    t0 = time.monotonic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        system=_system_prompt(),
        messages=messages,
    )
    latency = time.monotonic() - t0

    # Anthropics Python SDK returns a content list; assume a single text block.
    text_parts = [
        getattr(c, "text", "")
        for c in getattr(response, "content", [])
        if getattr(c, "type", "") == "text"
    ]
    raw = "".join(text_parts).strip()

    # Some models wrap JSON in Markdown code fences (```json ... ```). Strip them.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```", 2)
        if len(parts) >= 3:
            # parts[1] may be a language tag like 'json'; keep only the middle section.
            inner = parts[1]
            if "\n" in inner:
                # Language tag line + JSON below
                _, inner_json = inner.split("\n", 1)
                cleaned = inner_json.strip()
            else:
                cleaned = parts[1].strip()
        else:
            # Fallback: remove leading and trailing fences if present.
            cleaned = cleaned.strip("`").strip()

    try:
        parsed: dict[str, Any] = json.loads(cleaned)
    except json.JSONDecodeError:
        # If we cannot parse JSON, surface latency but return no data.
        return None, latency

    # Down-select and normalize to the small schema we care about.
    result: ClaudeExtraction = {}

    wd = parsed.get("washer_dryer")
    if isinstance(wd, str) or wd is None:
        # Trust the model to use a valid enum; caller can apply stronger checks.
        result["washer_dryer"] = wd  # type: ignore[assignment]

    rpf = parsed.get("renter_paid_fees")
    if isinstance(rpf, list) or rpf is None:
        # Filter to strings only if it's a list.
        if isinstance(rpf, list):
            result["renter_paid_fees"] = [str(x) for x in rpf]
        else:
            result["renter_paid_fees"] = None

    avail = parsed.get("availability")
    if isinstance(avail, str) or avail is None:
        result["availability"] = avail

    pet = parsed.get("pet_policy")
    if isinstance(pet, str) or pet is None:
        result["pet_policy"] = pet

    roommates = parsed.get("roommates")
    if isinstance(roommates, str) or roommates is None:
        result["roommates"] = roommates

    return result, latency


def extract_from_snapshot_record(record: Mapping[str, Any]) -> Tuple[Optional[ClaudeExtraction], float]:
    """
    Convenience helper: build text from a Bright Data snapshot record.

    This does not touch the database. It is intended for use in prototype
    scripts and future pipeline hooks.
    """
    title = str(record.get("title") or "").strip()
    # Prefer the more detailed seller_description when present.
    description = str(
        record.get("seller_description")
        or record.get("description")
        or ""
    )
    price = record.get("final_price") or record.get("initial_price") or record.get("price")
    beds = record.get("beds") or record.get("bedrooms") or record.get("bed")
    baths = record.get("baths") or record.get("bathrooms") or record.get("bath")
    address_raw = None  # Bright Data records currently do not include a clean address field.

    return extract_from_text(
        title=title,
        description=description,
        price=price,
        beds=beds,
        baths=baths,
        address_raw=address_raw,
    )

