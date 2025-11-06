"""
Prediction system for scheduled signal generation and alerting.

This module provides:
- Scheduled prediction execution (scheduler.py)
- Signal generation engine (engine.py)
- Database persistence for signals and metrics (persistence.py)
- Multi-channel notifications (notifications/)
- Performance monitoring and calibration (monitoring/)
"""

from __future__ import annotations

__all__ = [
    "PredictionPersistence",
    "SignalType",
    "GeneratedSignal",
    "SignalGenerator",
    "SignalAggregator",
    "PredictionEngine",
    "PredictionRunResult",
    "TradingSession",
    "SchedulerConfig",
    "MarketHoursManager",
    "PredictionScheduler",
    "NotificationConfig",
    "NotificationRouter",
    "DiscordAdapter",
    "ConsoleAdapter",
]

from .persistence import PredictionPersistence
from .engine import (
    SignalType,
    GeneratedSignal,
    SignalGenerator,
    SignalAggregator,
    PredictionEngine,
    PredictionRunResult,
)
from .scheduler import (
    TradingSession,
    SchedulerConfig,
    MarketHoursManager,
    PredictionScheduler,
)
from .notifications import (
    NotificationConfig,
    NotificationRouter,
    DiscordAdapter,
    ConsoleAdapter,
)
