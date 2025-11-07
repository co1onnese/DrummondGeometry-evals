"""Core package for the Drummond Geometry Analysis System."""

from __future__ import annotations

from importlib.metadata import version

__all__ = ["get_version"]


def get_version() -> str:
    """Return the installed package version."""

    try:
        return version("drummond-geometry")
    except Exception:  # pragma: no cover - fallback for editable installs
        return "0.0.0"
