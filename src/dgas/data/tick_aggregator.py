"""Tick aggregator for converting real-time ticks into interval bars.

WebSocket provides tick-by-tick data. This module aggregates ticks into
interval bars (e.g., 30m bars) for storage in the database.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from .models import IntervalData

logger = logging.getLogger(__name__)

# Interval durations in seconds
INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


@dataclass
class Tick:
    """A single price tick from WebSocket."""

    symbol: str
    timestamp: datetime
    price: Decimal
    volume: int
    trade_type: Optional[str] = None  # 'trade', 'quote', etc.


@dataclass
class PendingBar:
    """A bar being built from ticks."""

    symbol: str
    interval: str
    bar_start: datetime
    bar_end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    tick_count: int

    def to_interval_data(self) -> IntervalData:
        """Convert to IntervalData for storage."""
        return IntervalData(
            symbol=self.symbol,
            exchange="US",
            timestamp=self.bar_start,
            interval=self.interval,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            adjusted_close=self.close,
            volume=self.volume,
        )


class TickAggregator:
    """
    Aggregate ticks into interval bars.

    Collects individual price ticks and aggregates them into OHLCV bars
    for a specified interval (e.g., 30 minutes).
    """

    def __init__(self, interval: str = "30m"):
        """
        Initialize tick aggregator.

        Args:
            interval: Target interval for bars (e.g., "30m", "1h")
        """
        if interval not in INTERVAL_SECONDS:
            raise ValueError(f"Unsupported interval: {interval}")

        self.interval = interval
        self.interval_seconds = INTERVAL_SECONDS[interval]

        # Pending bars by symbol
        # Key: (symbol, bar_start_timestamp)
        self._pending_bars: Dict[tuple[str, datetime], PendingBar] = {}

        # Statistics
        self.ticks_processed = 0
        self.bars_completed = 0

    def add_tick(self, tick: Tick) -> Optional[IntervalData]:
        """
        Add a tick and return completed bar if interval is finished.

        Args:
            tick: Price tick to add

        Returns:
            Completed IntervalData bar if interval finished, None otherwise
        """
        self.ticks_processed += 1

        # Calculate bar start time (aligned to interval boundaries)
        bar_start = self._align_to_interval(tick.timestamp)
        bar_end = bar_start + timedelta(seconds=self.interval_seconds)

        # Get or create pending bar
        key = (tick.symbol, bar_start)
        if key not in self._pending_bars:
            # New bar starting
            self._pending_bars[key] = PendingBar(
                symbol=tick.symbol,
                interval=self.interval,
                bar_start=bar_start,
                bar_end=bar_end,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
                volume=tick.volume,
                tick_count=1,
            )
        else:
            # Update existing bar
            bar = self._pending_bars[key]
            bar.high = max(bar.high, tick.price)
            bar.low = min(bar.low, tick.price)
            bar.close = tick.price
            bar.volume += tick.volume
            bar.tick_count += 1

        # Check if bar is complete (current time past bar end)
        current_time = datetime.now(timezone.utc)
        if current_time >= bar_end:
            # Bar is complete, return it
            completed_bar = self._pending_bars.pop(key)
            self.bars_completed += 1
            return completed_bar.to_interval_data()

        return None

    def flush_pending_bars(self, before_time: Optional[datetime] = None) -> List[IntervalData]:
        """
        Flush all pending bars that are complete.

        Args:
            before_time: Flush bars ending before this time (default: now)

        Returns:
            List of completed bars
        """
        if before_time is None:
            before_time = datetime.now(timezone.utc)

        completed_bars: List[IntervalData] = []
        keys_to_remove: List[tuple[str, datetime]] = []

        for key, bar in self._pending_bars.items():
            if before_time >= bar.bar_end:
                completed_bars.append(bar.to_interval_data())
                keys_to_remove.append(key)

        for key in keys_to_remove:
            self._pending_bars.pop(key)
            self.bars_completed += 1

        return completed_bars

    def get_pending_bar(self, symbol: str) -> Optional[PendingBar]:
        """
        Get current pending bar for a symbol.

        Args:
            symbol: Symbol to get bar for

        Returns:
            PendingBar or None if no pending bar
        """
        # Find most recent pending bar for symbol
        current_time = datetime.now(timezone.utc)
        bar_start = self._align_to_interval(current_time)
        key = (symbol, bar_start)

        return self._pending_bars.get(key)

    def _align_to_interval(self, timestamp: datetime) -> datetime:
        """
        Align timestamp to interval boundary.

        Args:
            timestamp: Timestamp to align

        Returns:
            Aligned timestamp (start of interval)
        """
        # Convert to UTC if needed
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)

        # Calculate seconds since epoch
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        total_seconds = int((timestamp - epoch).total_seconds())

        # Align to interval
        aligned_seconds = (total_seconds // self.interval_seconds) * self.interval_seconds

        # Convert back to datetime
        return epoch + timedelta(seconds=aligned_seconds)

    def get_stats(self) -> Dict[str, int]:
        """Get aggregation statistics."""
        return {
            "ticks_processed": self.ticks_processed,
            "bars_completed": self.bars_completed,
            "pending_bars": len(self._pending_bars),
        }


__all__ = ["TickAggregator", "Tick", "PendingBar"]
