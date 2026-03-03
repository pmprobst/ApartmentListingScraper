"""
Core package for the Utah Valley Rental Skimmer pipeline.

This package exposes the main building blocks:

- db: SQLite schema, deduplication, and run_status helpers
- ingest: Bright Data snapshot ingestion and normalization
- build_page: static HTML generation from the SQLite DB
- pipeline: high-level orchestration helpers
"""

from . import db  # noqa: F401
from . import ingest  # noqa: F401
from . import build_page  # noqa: F401
from . import pipeline  # noqa: F401

__all__ = ["db", "ingest", "build_page", "pipeline"]

