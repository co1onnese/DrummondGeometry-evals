"""
Notification system for delivering trading signals through multiple channels.

This module provides:
- NotificationRouter for multi-channel signal delivery
- NotificationAdapter abstract base for channel implementations
- Discord adapter with rich embeds
- Console adapter with Rich tables
"""

from __future__ import annotations

__all__ = [
    "NotificationConfig",
    "NotificationAdapter",
    "NotificationRouter",
    "DiscordAdapter",
    "ConsoleAdapter",
]

from .router import NotificationConfig, NotificationAdapter, NotificationRouter
from .adapters.discord import DiscordAdapter
from .adapters.console import ConsoleAdapter
