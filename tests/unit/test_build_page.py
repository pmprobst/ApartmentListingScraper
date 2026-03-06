"""
Unit tests for build_page helpers (e.g. 30-day cutoff).
"""

from datetime import datetime, timezone, timedelta

import pytest

# Import module to test private helper
from uvrental import build_page as build_page_module


def test_thirty_days_ago_iso_cutoff_ordering():
    """
    _thirty_days_ago_iso() returns a UTC cutoff such that:
    - last_seen 31 days ago is before cutoff (excluded),
    - last_seen 29 days ago is after cutoff (included).
    Guards against off-by-one errors in the 30-day window.
    """
    cutoff = build_page_module._thirty_days_ago_iso()
    now = datetime.now(timezone.utc)
    thirty_one_days_ago = (now - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
    twenty_nine_days_ago = (now - timedelta(days=29)).strftime("%Y-%m-%dT%H:%M:%SZ")

    assert thirty_one_days_ago < cutoff, "31 days ago should be before cutoff (excluded from page)"
    assert twenty_nine_days_ago > cutoff, "29 days ago should be after cutoff (included on page)"
