"""Rewired Index: AI-powered 5-layer investment framework."""

from pathlib import Path

__version__ = "0.1.0"

# Project root: 2 parents up from src/rewired/__init__.py
PROJECT_ROOT = Path(__file__).parents[2]


def get_data_dir() -> Path:
    """Return the data directory, creating it if needed."""
    d = PROJECT_ROOT / "data"
    d.mkdir(exist_ok=True)
    return d


def get_config_dir() -> Path:
    """Return the config directory."""
    return PROJECT_ROOT / "config"
