"""
Core package for the Utah Valley Rental Skimmer pipeline.

This package exposes the main building blocks:

- db: SQLite schema, deduplication, and run_status helpers
- ingest: Bright Data snapshot ingestion and normalization
- build_page: static HTML generation from the SQLite DB
- pipeline: high-level orchestration helpers
"""

__all__ = ["db", "ingest", "build_page", "pipeline"]


def __getattr__(name: str):
    """Lazy-load submodules so `python -m uvrental.build_page` does not preload them."""
    if name in __all__:
        import importlib
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

