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

__all__ = ["PredictionPersistence"]

from .persistence import PredictionPersistence
