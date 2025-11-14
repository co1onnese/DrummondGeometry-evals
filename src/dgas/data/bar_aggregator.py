"""Bar aggregator for converting smaller interval bars into larger intervals.

For example, aggregates 5m bars into 30m bars when 30m data is not available.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List

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


def aggregate_bars(bars: List[IntervalData], target_interval: str) -> List[IntervalData]:
    """
    Aggregate smaller interval bars into larger interval bars.
    
    For example, aggregate 5m bars into 30m bars.
    
    Args:
        bars: List of smaller interval bars (e.g., 5m bars)
        target_interval: Target interval (e.g., "30m")
        
    Returns:
        List of aggregated bars in target interval
    """
    if not bars:
        return []
    
    # Get source and target interval durations
    source_interval = bars[0].interval
    if source_interval not in INTERVAL_SECONDS:
        raise ValueError(f"Unsupported source interval: {source_interval}")
    if target_interval not in INTERVAL_SECONDS:
        raise ValueError(f"Unsupported target interval: {target_interval}")
    
    source_seconds = INTERVAL_SECONDS[source_interval]
    target_seconds = INTERVAL_SECONDS[target_interval]
    
    if source_seconds >= target_seconds:
        raise ValueError(
            f"Cannot aggregate {source_interval} bars into {target_interval} bars "
            f"(source interval must be smaller than target)"
        )
    
    if target_seconds % source_seconds != 0:
        raise ValueError(
            f"Cannot aggregate {source_interval} bars into {target_interval} bars "
            f"(target interval must be a multiple of source interval)"
        )
    
    # Group bars by target interval start time
    # Store as dict of lists first, then aggregate
    grouped: dict[datetime, list[IntervalData]] = defaultdict(list)
    
    for bar in bars:
        # Align bar timestamp to target interval boundary
        bar_start = _align_to_interval(bar.timestamp, target_seconds)
        grouped[bar_start].append(bar)
    
    # Aggregate each group into a single bar
    aggregated: list[IntervalData] = []
    for bar_start, group_bars in sorted(grouped.items()):
        if not group_bars:
            continue
        
        # Filter out bars with None OHLC values (invalid data)
        valid_bars = [
            b for b in group_bars
            if b.open is not None
            and b.high is not None
            and b.low is not None
            and b.close is not None
        ]
        
        # Skip if no valid bars in this group
        if not valid_bars:
            logger.warning(
                f"Skipping aggregation for {group_bars[0].symbol} at {bar_start}: "
                f"no bars with valid OHLC data ({len(group_bars)} bars had None values)"
            )
            continue
        
        # Sort by timestamp to ensure proper ordering
        valid_bars.sort(key=lambda b: b.timestamp)
        
        # Aggregate OHLCV
        # Open is the open of the first bar
        open_price = valid_bars[0].open
        # High is the maximum high across all bars
        high_price = max(b.high for b in valid_bars)
        # Low is the minimum low across all bars
        low_price = min(b.low for b in valid_bars)
        # Close is the close of the last bar
        close_price = valid_bars[-1].close
        # Adjusted close is the adjusted close of the last bar (or close if None)
        adjusted_close = valid_bars[-1].adjusted_close or close_price
        # Volume is sum of all volumes
        total_volume = sum(b.volume for b in valid_bars)
        
        # Ensure all prices are Decimal (not None)
        # This should already be the case after filtering, but double-check
        if not all(isinstance(p, Decimal) for p in [open_price, high_price, low_price, close_price]):
            logger.error(
                f"Invalid price types for {valid_bars[0].symbol} at {bar_start}: "
                f"open={type(open_price)}, high={type(high_price)}, "
                f"low={type(low_price)}, close={type(close_price)}"
            )
            continue
        
        # Create aggregated bar
        aggregated.append(
            IntervalData(
                symbol=valid_bars[0].symbol,
                exchange=valid_bars[0].exchange,
                timestamp=bar_start,
                interval=target_interval,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                adjusted_close=adjusted_close,
                volume=total_volume,
            )
        )
    
    # Result is already sorted by timestamp
    logger.debug(
        f"Aggregated {len(bars)} {source_interval} bars into {len(aggregated)} {target_interval} bars"
    )
    
    return aggregated


def _align_to_interval(timestamp: datetime, interval_seconds: int) -> datetime:
    """
    Align timestamp to interval boundary.
    
    Args:
        timestamp: Timestamp to align
        interval_seconds: Interval duration in seconds
        
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
    aligned_seconds = (total_seconds // interval_seconds) * interval_seconds
    
    # Convert back to datetime
    return epoch + timedelta(seconds=aligned_seconds)


__all__ = ["aggregate_bars"]
