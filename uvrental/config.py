"""
TOML config loader for Utah Valley Rental Skimmer.

Loads config from paths.config_file (default config.toml), with fallback to
config_schema.toml in the project root. API keys remain in env / GitHub Secrets only.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"
FALLBACK_CONFIG_PATH = PROJECT_ROOT / "config_schema.toml"

_config_cache: dict | None = None


def _load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_config(config_path: str | Path | None = None) -> dict:
    """Load TOML config. Uses env CONFIG_FILE if set, else config_path or default."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    env_path = os.environ.get("CONFIG_FILE", "").strip()
    if env_path:
        path = Path(env_path)
    elif config_path is not None:
        path = Path(config_path)
    else:
        path = DEFAULT_CONFIG_PATH

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if path.exists():
        _config_cache = _load_toml(path)
    elif FALLBACK_CONFIG_PATH.exists():
        _config_cache = _load_toml(FALLBACK_CONFIG_PATH)
    else:
        _config_cache = {}

    return _config_cache


def get_config() -> dict:
    """Return loaded config (loads if not yet loaded)."""
    return load_config()


def get_db_path() -> str:
    """SQLite DB path from config paths.db or env LISTINGS_DB."""
    env_db = os.environ.get("LISTINGS_DB", "").strip()
    if env_db:
        return env_db
    cfg = get_config()
    return cfg.get("paths", {}).get("db", "listings.db")


def get_output_dir() -> str:
    """Output directory from config paths.output or env BUILD_PAGE_OUTPUT."""
    env_out = os.environ.get("BUILD_PAGE_OUTPUT", "").strip()
    if env_out:
        return env_out
    cfg = get_config()
    return cfg.get("paths", {}).get("output", "docs")


def get_data_dir() -> Path | None:
    """
    Optional data directory for snapshot_history.jsonl and snapshots/.
    If set (via env SNAPSHOT_DATA_DIR or config paths.data_dir), scripts use
    data_dir/snapshot_history.jsonl and data_dir/snapshots/. Otherwise use PROJECT_ROOT.
    """
    env_dir = os.environ.get("SNAPSHOT_DATA_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    cfg = get_config()
    data_dir = cfg.get("paths", {}).get("data_dir")
    if not data_dir:
        return None
    p = Path(data_dir)
    return p if p.is_absolute() else PROJECT_ROOT / p


def get_snapshot_history_path() -> Path:
    """Path to snapshot_history.jsonl. Uses data_dir if set, else PROJECT_ROOT."""
    data_dir = get_data_dir()
    base = data_dir if data_dir is not None else PROJECT_ROOT
    return base / "snapshot_history.jsonl"


def get_snapshots_dir() -> Path:
    """Directory for downloaded snapshot JSONs. Uses data_dir if set, else PROJECT_ROOT."""
    data_dir = get_data_dir()
    base = data_dir if data_dir is not None else PROJECT_ROOT
    return base / "snapshots"


def get_price_min() -> int:
    """Min price from env PRICE_MIN or config search.price_min."""
    env_val = os.environ.get("PRICE_MIN", "").strip()
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass
    cfg = get_config()
    return int(cfg.get("search", {}).get("price_min", 0))


def get_price_max() -> int:
    """Max price from env PRICE_MAX or config search.price_max."""
    env_val = os.environ.get("PRICE_MAX", "").strip()
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass
    cfg = get_config()
    return int(cfg.get("search", {}).get("price_max", 2000))


def get_location() -> str:
    """Location from config search.location (city or city, state)."""
    cfg = get_config()
    loc = cfg.get("search", {}).get("location", "Provo")
    state = cfg.get("search", {}).get("location_state", "UT")
    if state and "," not in str(loc):
        return f"{loc}, {state}"
    return str(loc)


def get_category() -> str:
    """Category/keyword from config search.category."""
    cfg = get_config()
    return cfg.get("search", {}).get("category", "Apartment")


def get_dataset_id() -> str:
    """Bright Data dataset ID from config bright_data.dataset_id."""
    cfg = get_config()
    return cfg.get("bright_data", {}).get("dataset_id", "gd_lvt9iwuh6fbcwmx1a")


def get_claude_model() -> str:
    """Claude model from config claude.model or env CLAUDE_MODEL."""
    env_model = os.environ.get("CLAUDE_MODEL", "").strip()
    if env_model:
        return env_model
    cfg = get_config()
    return cfg.get("claude", {}).get("model", "claude-sonnet-4-20250514")


def get_claude_timeout() -> int:
    """Claude timeout from config claude.timeout_seconds."""
    cfg = get_config()
    return int(cfg.get("claude", {}).get("timeout_seconds", 60))


def get_run_status_store() -> str:
    """Run status store from config run_status.store."""
    cfg = get_config()
    return cfg.get("run_status", {}).get("store", "sqlite")


def get_display_days() -> int:
    """Number of days for last_seen window (listings older are hidden). Env DISPLAY_DAYS or config."""
    env_val = os.environ.get("DISPLAY_DAYS", "").strip()
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass
    cfg = get_config()
    return int(cfg.get("search", {}).get("display_days", 30))


def reset_config_cache() -> None:
    """Clear config cache (for tests)."""
    global _config_cache
    _config_cache = None
