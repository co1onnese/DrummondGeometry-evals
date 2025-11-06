"""Notification channel adapters."""

from __future__ import annotations

__all__ = [
    "DiscordAdapter",
    "ConsoleAdapter",
]

from .discord import DiscordAdapter
from .console import ConsoleAdapter
