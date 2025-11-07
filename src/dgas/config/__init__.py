"""
Configuration management for DGAS.

Provides YAML/JSON configuration file loading with environment variable expansion,
validation, and merging of multiple configuration sources.
"""

from __future__ import annotations

from .adapter import UnifiedSettings, load_settings
from .loader import ConfigLoader, load_config
from .schema import DGASConfig

__all__ = [
    "ConfigLoader",
    "load_config",
    "DGASConfig",
    "UnifiedSettings",
    "load_settings",
]
