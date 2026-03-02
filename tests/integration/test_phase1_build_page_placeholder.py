"""
Placeholder tests for Phase 1 (run status + static webpage).

These are intentionally skipped until the corresponding implementation
modules (e.g. build_page.py, run_status storage) are added.
"""

import importlib.util

import pytest


_build_page_spec = importlib.util.find_spec("build_page")

if _build_page_spec is None:
    pytest.skip(
        "Phase 1 webpage and run_status implementation not present yet; "
        "placeholder tests only.",
        allow_module_level=True,
    )

# When build_page.py exists, expand this module with real tests that:
# - generate HTML from a small seed DB
# - assert listings and run status summary are rendered as per features.md.

