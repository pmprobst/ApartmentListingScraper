import json
from textwrap import dedent
from typing import Any, Dict, List, Mapping


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
      Recurring costs the renter must pay in addition to base rent.
      Examples: ["electricity", "gas", "water", "sewer", "trash", "internet",
      "parking", "pet_rent"].

    - availability (string or null):
      Short phrase like "ASAP", "March 1, 2026", "mid-March".

    - pet_policy (string or null):
      Short summary of which pets are allowed, deposits, and monthly pet rent.

    - parking (string or null):
      One of: "included_assigned", "included_unassigned", "garage_included",
      "garage_extra_cost", "street_only", "paid_lot", "no_parking",
      "not_mentioned".

    - lease_length (string or null):
      Examples: "month_to_month", "6_months", "12_months", "6_or_12_months",
      "short_term", "unspecified".

    - deposit (string or null):
      Short description of deposit and whether refundable, e.g.
      "$1200 refundable", "$500 non-refundable cleaning fee",
      "first and last month’s rent".

    - application_fees (string or null):
      One-time application, admin, or move-in fees, e.g.
      "$40 application fee per adult".

    - furnished (string or null):
      One of: "fully_furnished", "partially_furnished", "unfurnished",
      "not_mentioned".

    - square_footage (integer or null):
      Square footage as an integer, e.g. 850. Use null if not mentioned.

    - roommates (string or null):
      Short summary such as "entire_unit",
      "private_room_in_3br_with_2_roommates",
      "shared_room", or "unspecified".

    - subletting (string or null):
      One of: "allowed", "not_allowed", "not_mentioned".

    - contact (string or null):
      Short description of who to contact and how, e.g.
      "contact property manager via portal",
      "text landlord at 555-123-4567".

    - move_in_incentives (string or null):
      Any discounts or incentives, e.g. "first month free",
      "half off first month", "reduced deposit".

    - amenities (array of strings or null):
      Amenities as short tokens such as
      ["central_ac", "dishwasher", "gym", "pool", "yard", "storage",
      "laundry_in_unit", "clubhouse", "covered_parking"].

    - restrictions (array of strings or null):
      Restrictions as short tokens, e.g.
      ["no_smoking", "no_pets", "students_only",
       "credit_check_required", "background_check_required"].

    - location_detail (string or null):
      Short description of neighborhood or landmarks, e.g.
      "near BYU", "near UVU", "Downtown Provo",
      "close to I-15 and University Pkwy".
    """
).strip()


EXAMPLE_INPUT_1 = dedent(
    """
    TITLE:
    Spacious 2BR Apartment near BYU – In-unit Laundry

    METADATA:
    price: 1350
    beds: 2
    baths: 1
    address_raw: Provo, UT

    DESCRIPTION:
    This bright 2 bedroom, 1 bath apartment is a 10-minute walk from BYU campus.
    In-unit washer and dryer included. One assigned covered parking stall plus
    additional street parking. 12-month lease. No pets, no smoking.
    $1,200 refundable security deposit plus $40 application fee per adult.
    Tenant pays electricity and internet; owner covers water, sewer, and trash.
    Central AC, dishwasher, and on-site storage unit included.
    Available March 1.
    """
).strip()


EXAMPLE_OUTPUT_1 = {
    "washer_dryer": "in_unit",
    "renter_paid_fees": [
        "electricity",
        "internet",
    ],
    "availability": "March 1",
    "pet_policy": "no pets; no smoking",
    "parking": "included_assigned",
    "lease_length": "12_months",
    "deposit": "$1,200 refundable security deposit",
    "application_fees": "$40 application fee per adult",
    "furnished": "unfurnished",
    "square_footage": None,
    "roommates": "entire_unit",
    "subletting": "not_mentioned",
    "contact": None,
    "move_in_incentives": None,
    "amenities": [
        "central_ac",
        "dishwasher",
        "storage",
    ],
    "restrictions": [
        "no_smoking",
        "no_pets",
    ],
    "location_detail": "near BYU",
}


EXAMPLE_INPUT_2 = dedent(
    """
    TITLE:
    Private Room in 4BR Student House – Utilities Split

    METADATA:
    price: 650
    beds: 1
    baths: 1
    address_raw: Orem, UT

    DESCRIPTION:
    Private bedroom in a 4 bedroom, 2 bathroom house shared with 3 other male
    students. Month-to-month lease with option to renew for fall semester.
    Shared washer/dryer in the basement. Driveway and street parking only.
    Students only; no pets, no smoking. Utilities (power, gas, internet) split
    evenly between roommates. $300 deposit plus $100 non-refundable cleaning fee.
    Available ASAP.
    """
).strip()


EXAMPLE_OUTPUT_2 = {
    "washer_dryer": "shared_laundry",
    "renter_paid_fees": [
        "electricity",
        "gas",
        "internet",
    ],
    "availability": "ASAP",
    "pet_policy": "no pets",
    "parking": "street_only",
    "lease_length": "month_to_month",
    "deposit": "$300 deposit plus $100 non-refundable cleaning fee",
    "application_fees": None,
    "furnished": "not_mentioned",
    "square_footage": None,
    "roommates": "private_room_in_4br_with_3_roommates",
    "subletting": "not_mentioned",
    "contact": None,
    "move_in_incentives": None,
    "amenities": [],
    "restrictions": [
        "students_only",
        "no_smoking",
        "no_pets",
    ],
    "location_detail": None,
}


EXAMPLE_INPUT_3 = dedent(
    """
    TITLE:
    Studio Apartment – Downtown Provo

    METADATA:
    price: 900
    beds: 0
    baths: 1
    address_raw: Provo, UT

    DESCRIPTION:
    Cozy studio in downtown Provo close to restaurants and shops.
    Recently updated flooring and paint. Great for a single professional.
    """
).strip()


EXAMPLE_OUTPUT_3 = {
    "washer_dryer": "not_mentioned",
    "renter_paid_fees": None,
    "availability": None,
    "pet_policy": None,
    "parking": "not_mentioned",
    "lease_length": "unspecified",
    "deposit": None,
    "application_fees": None,
    "furnished": "not_mentioned",
    "square_footage": None,
    "roommates": "entire_unit",
    "subletting": "not_mentioned",
    "contact": None,
    "move_in_incentives": None,
    "amenities": None,
    "restrictions": None,
    "location_detail": "Downtown Provo",
}


def _example_block() -> str:
    return dedent(
        f"""
        Here are three examples. Follow the same style strictly.

        Example 1 - input:
        {EXAMPLE_INPUT_1}

        Example 1 - JSON output:
        {json.dumps(EXAMPLE_OUTPUT_1, ensure_ascii=False, indent=2)}

        Example 2 - input:
        {EXAMPLE_INPUT_2}

        Example 2 - JSON output:
        {json.dumps(EXAMPLE_OUTPUT_2, ensure_ascii=False, indent=2)}

        Example 3 - input:
        {EXAMPLE_INPUT_3}

        Example 3 - JSON output:
        {json.dumps(EXAMPLE_OUTPUT_3, ensure_ascii=False, indent=2)}
        """
    ).strip()


def build_extraction_messages(listing: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """
    Build Anthropic Messages API payload for extracting structured fields
    from a single listing.

    The caller is responsible for passing only listings that are new and
    within the configured price range.
    """

    title = str(listing.get("title") or "").strip()
    description = str(listing.get("description") or "").strip()
    price = listing.get("price")
    beds = listing.get("beds")
    baths = listing.get("baths")
    address_raw = str(listing.get("address_raw") or "").strip()

    metadata_lines = []
    if price is not None:
        metadata_lines.append(f"price: {price}")
    if beds is not None:
        metadata_lines.append(f"beds: {beds}")
    if baths is not None:
        metadata_lines.append(f"baths: {baths}")
    if address_raw:
        metadata_lines.append(f"address_raw: {address_raw}")

    metadata_block = "\n".join(metadata_lines) if metadata_lines else "price: unknown"

    user_content = dedent(
        f"""
        You are an information extraction assistant for rental listings in
        Utah Valley. Extract structured details conservatively from the text
        below. If something is not clearly stated, use null or "not_mentioned"
        instead of guessing.

        {EXTRACTION_FIELD_DOC}

        Output requirements:
        - Return exactly one JSON object.
        - Do not include any explanation, comments, or extra keys.
        - Keys must match the schema exactly.
        - JSON must be valid: no trailing commas, no code fences, no backticks.

        Listing to analyze:

        TITLE:
        {title}

        METADATA:
        {metadata_block}

        DESCRIPTION:
        {description}

        {_example_block()}
        """
    ).strip()

    return [
        {
            "role": "system",
            "content": (
                "You are a careful information extraction assistant. "
                "You read rental listings and output strictly valid JSON "
                "according to the given schema. You never guess when the "
                "text is ambiguous; you use null or 'not_mentioned' instead."
            ),
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]

