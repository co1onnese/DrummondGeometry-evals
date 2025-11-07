"""Optimized multi-timeframe coordinator with performance enhancements.

This module provides performance-optimized versions of the multi-timeframe
coordination algorithms with caching, binary search, and memoization to
achieve the <200ms per symbol/timeframe target.
"""

from __future__ import annotations

import functools
import logging
import time
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from .drummond_lines import DrummondZone
from .envelopes import EnvelopeSeries, EnvelopeCalculator
from .multi_timeframe import (
    ConfluenceZone,
    MultiTimeframeAnalysis,
    MultiTimeframeCoordinator,
    PLDotOverlay,
    TimeframeAlignment,
    TimeframeData,
    TimeframeType,
    TrendDirection,
)
from .pldot import PLDotSeries
from .profiler import get_calculation_profiler
from .states import MarketState, StateSeries

logger = logging.getLogger(__name__)


class OptimizedTimeframeData(TimeframeData):
    """TimeframeData with pre-computed indexes for fast lookups."""

    def __init__(self, *args, **kwargs):
        """Initialize with timestamp index."""
        super().__init__(*args, **kwargs)
        self._build_timestamp_index()

    def _build_timestamp_index(self) -> None:
        """Build index for fast timestamp lookups."""
        self.timestamps = [s.timestamp for s in self.state_series]
        self.pldot_timestamps = [p.timestamp for p in self.pldot_series]
        self.envelope_timestamps = [e.timestamp for e in self.envelope_series]

    def get_state_at_timestamp(self, timestamp: datetime) -> Optional[StateSeries]:
        """Get state at or before timestamp using binary search."""
        if not self.state_series:
            return None

        idx = bisect_right(self.timestamps, timestamp)
        if idx == 0:
            return None
        return self.state_series[idx - 1]

    def get_pldot_at_timestamp(self, timestamp: datetime) -> Optional[PLDotSeries]:
        """Get PLdot at or before timestamp using binary search."""
        if not self.pldot_series:
            return None

        idx = bisect_right(self.pldot_timestamps, timestamp)
        if idx == 0:
            return None
        return self.pldot_series[idx - 1]

    def get_envelope_at_timestamp(self, timestamp: datetime) -> Optional[EnvelopeSeries]:
        """Get envelope at or before timestamp using binary search."""
        if not self.envelope_series:
            return None

        idx = bisect_right(self.envelope_timestamps, timestamp)
        if idx == 0:
            return None
        return self.envelope_series[idx - 1]

    def get_recent_envelopes(self, timestamp: datetime, count: int = 20) -> List[EnvelopeSeries]:
        """Get recent envelopes using binary search."""
        if not self.envelope_series:
            return []

        idx = bisect_right(self.envelope_timestamps, timestamp)
        start = max(0, idx - count)
        return list(self.envelope_series[start:idx])


class OptimizedMultiTimeframeCoordinator(MultiTimeframeCoordinator):
    """
    Performance-optimized multi-timeframe coordinator.

    Optimizations:
    - Binary search for timestamp lookups (O(log n) vs O(n))
    - Memoization of expensive operations
    - Caching of confluence zones
    - Optimized clustering algorithm
    - Early termination of unnecessary calculations
    """

    def __init__(self, *args, enable_cache: bool = True, **kwargs):
        """
        Initialize optimized coordinator.

        Args:
            *args: Arguments for parent class
            enable_cache: Whether to enable result caching
            **kwargs: Keyword arguments for parent class
        """
        super().__init__(*args, **kwargs)
        self.enable_cache = enable_cache
        self.profiler = get_calculation_profiler()
        self._cache: Dict[str, any] = {}

    def analyze(
        self,
        htf_data: TimeframeData,
        trading_tf_data: TimeframeData,
        ltf_data: Optional[TimeframeData] = None,
        target_timestamp: Optional[datetime] = None,
    ) -> MultiTimeframeAnalysis:
        """
        Perform optimized multi-timeframe analysis with profiling.

        Args:
            htf_data: Higher timeframe complete analysis
            trading_tf_data: Trading timeframe complete analysis
            ltf_data: Optional lower timeframe analysis
            target_timestamp: Timestamp to analyze (default: latest common timestamp)

        Returns:
            Complete multi-timeframe analysis with trading recommendations
        """
        start_time = time.time()

        # Convert to optimized data structures if needed
        if not isinstance(htf_data, OptimizedTimeframeData):
            htf_data = OptimizedTimeframeData(**htf_data.__dict__)
        if not isinstance(trading_tf_data, OptimizedTimeframeData):
            trading_tf_data = OptimizedTimeframeData(**trading_tf_data.__dict__)
        if ltf_data is not None and not isinstance(ltf_data, OptimizedTimeframeData):
            ltf_data = OptimizedTimeframeData(**ltf_data.__dict__)

        # Check cache
        cache_key = self._make_cache_key(htf_data, trading_tf_data, ltf_data, target_timestamp)
        if self.enable_cache and cache_key in self._cache:
            self.profiler.record_calculation(
                calculation_type="multi_timeframe_coordinator",
                symbol="unknown",
                timeframe="multi",
                execution_time_ms=(time.time() - start_time) * 1000,
                success=True,
                cache_hit=True,
            )
            return self._cache[cache_key]

        # Use parent's analyze method (which is already optimized)
        result = super().analyze(htf_data, trading_tf_data, ltf_data, target_timestamp)

        # Cache result
        if self.enable_cache:
            self._cache[cache_key] = result

        # Record metrics
        execution_time_ms = (time.time() - start_time) * 1000
        self.profiler.record_calculation(
            calculation_type="multi_timeframe_coordinator",
            symbol="unknown",
            timeframe="multi",
            execution_time_ms=execution_time_ms,
            success=True,
            cache_hit=False,
        )

        return result

    def _make_cache_key(
        self,
        htf_data: OptimizedTimeframeData,
        trading_tf_data: OptimizedTimeframeData,
        ltf_data: Optional[OptimizedTimeframeData],
        target_timestamp: Optional[datetime],
    ) -> str:
        """Create cache key for this analysis."""
        return f"{id(htf_data)}_{id(trading_tf_data)}_{id(ltf_data)}_{target_timestamp}"

    def clear_cache(self) -> None:
        """Clear the analysis cache."""
        self._cache.clear()

    @functools.lru_cache(maxsize=128)
    def _detect_confluence_zones_cached(
        self,
        all_timeframe_data_tuple: tuple,
        timestamp: datetime,
    ) -> List[ConfluenceZone]:
        """
        Cached version of confluence zone detection.

        Args:
            all_timeframe_data_tuple: Frozen tuple of timeframe data
            timestamp: Target timestamp

        Returns:
            List of confluence zones
        """
        # Convert back from tuple
        all_timeframe_data = [TimeframeData(**data.__dict__) for data in all_timeframe_data_tuple]

        # Use parent's implementation
        return self._detect_confluence_zones_impl(all_timeframe_data, timestamp)

    def _detect_confluence_zones(
        self,
        all_timeframe_data: List[TimeframeData],
        timestamp: datetime,
    ) -> List[ConfluenceZone]:
        """
        Optimized confluence zone detection.

        This version uses:
        - Binary search for recent envelopes
        - Optimized clustering algorithm
        - Early termination
        """
        if not all_timeframe_data:
            return []

        # Check cache first
        timeframe_data_tuple = tuple(all_timeframe_data)
        if self.enable_cache:
            try:
                return self._detect_confluence_zones_cached(timeframe_data_tuple, timestamp)
            except TypeError:
                # Fallback if not hashable
                pass

        return self._detect_confluence_zones_impl(all_timeframe_data, timestamp)

    def _detect_confluence_zones_impl(
        self,
        all_timeframe_data: List[TimeframeData],
        timestamp: datetime,
    ) -> List[ConfluenceZone]:
        """
        Optimized implementation of confluence zone detection.

        Uses optimized algorithms and binary search for better performance.
        """
        tf_weight_map = {
            TimeframeType.HIGHER: Decimal("1.5"),
            TimeframeType.TRADING: Decimal("1.0"),
            TimeframeType.LOWER: Decimal("0.75"),
        }

        base_relative_tolerance = Decimal(str(self.confluence_tolerance_pct / 100.0))
        min_absolute_tolerance = Decimal("0.0001")

        # Pre-allocate list for better performance
        level_entries: List[Dict[str, object]] = []

        # Pre-compute recent envelope data for each timeframe
        for tf_data in all_timeframe_data:
            if not tf_data or not tf_data.envelope_series:
                continue

            timeframe_label = tf_data.timeframe or tf_data.classification.value
            tf_weight = tf_weight_map.get(tf_data.classification, Decimal("1.0"))

            # Use binary search to get recent envelopes
            if isinstance(tf_data, OptimizedTimeframeData):
                recent_envelopes = tf_data.get_recent_envelopes(timestamp, count=20)
            else:
                # Fallback to linear search
                recent_envelopes = [
                    env for env in tf_data.envelope_series if env.timestamp <= timestamp
                ][-20:]

            # Process envelopes
            for env in recent_envelopes:
                width = Decimal(env.width)
                vol_measure = width if width > 0 else Decimal("0.01")

                # Upper envelope (resistance)
                level_entries.append({
                    "price": Decimal(env.upper),
                    "zone_type": "resistance",
                    "timeframe": timeframe_label,
                    "classification": tf_data.classification,
                    "timestamp": env.timestamp,
                    "source": "envelope_upper",
                    "weight": tf_weight,
                    "component_strength": Decimal("1.0"),
                    "volatility": vol_measure,
                })

                # Lower envelope (support)
                level_entries.append({
                    "price": Decimal(env.lower),
                    "zone_type": "support",
                    "timeframe": timeframe_label,
                    "classification": tf_data.classification,
                    "timestamp": env.timestamp,
                    "source": "envelope_lower",
                    "weight": tf_weight,
                    "component_strength": Decimal("1.0"),
                    "volatility": vol_measure,
                })

                # Center (pivot)
                level_entries.append({
                    "price": Decimal(env.center),
                    "zone_type": "pivot",
                    "timeframe": timeframe_label,
                    "classification": tf_data.classification,
                    "timestamp": env.timestamp,
                    "source": "pldot_center",
                    "weight": tf_weight,
                    "component_strength": Decimal("0.5"),
                    "volatility": vol_measure,
                })

            # Process Drummond zones if available
            for zone in getattr(tf_data, "drummond_zones", []) or []:
                width = abs(Decimal(zone.upper_price) - Decimal(zone.lower_price))
                vol_measure = width if width > 0 else Decimal("0.01")

                level_entries.append({
                    "price": Decimal(zone.center_price),
                    "zone_type": zone.line_type,
                    "timeframe": timeframe_label,
                    "classification": tf_data.classification,
                    "timestamp": timestamp,
                    "source": "drummond_zone",
                    "weight": tf_weight,
                    "component_strength": Decimal(zone.strength),
                    "volatility": vol_measure,
                })

        if not level_entries:
            return []

        # Optimized clustering using sorting first (O(n log n) vs O(n²))
        # This is much faster than the original nested loop approach
        level_entries.sort(key=lambda x: (x["zone_type"], x["price"]))

        zones: List[ConfluenceZone] = []
        used_indices: set[int] = set()

        precision = Decimal("0.000001")

        # Process clusters with optimized algorithm
        for idx, entry in enumerate(level_entries):
            if idx in used_indices:
                continue

            # Find cluster using forward scan (much faster than nested loop)
            cluster = [entry]
            cluster_indices = {idx}
            price = Decimal(entry["price"])
            zone_type = entry["zone_type"]

            # Scan forward for entries within tolerance
            tolerance = Decimal(entry["volatility"])
            min_tolerance = min_absolute_tolerance

            for jdx in range(idx + 1, len(level_entries)):
                if jdx in used_indices:
                    continue

                candidate = level_entries[jdx]
                if candidate["zone_type"] != zone_type:
                    continue

                price_diff = abs(Decimal(candidate["price"]) - price)
                candidate_tolerance = max(
                    tolerance,
                    Decimal(candidate["volatility"]),
                    min_tolerance,
                )

                if price_diff <= candidate_tolerance:
                    cluster.append(candidate)
                    cluster_indices.add(jdx)
                elif candidate["price"] > price + candidate_tolerance * Decimal("1.5"):
                    # Early termination: prices are sorted, and we've moved too far
                    break

            # Check if we have confluence (multiple timeframes)
            unique_timeframes = {str(item["timeframe"]) for item in cluster}
            if len(unique_timeframes) < 2:
                used_indices.update(cluster_indices)
                continue

            used_indices.update(cluster_indices)

            # Create zone from cluster
            levels = [Decimal(item["price"]) for item in cluster]
            center = sum(levels, Decimal("0")) / Decimal(len(levels))
            upper = max(levels)
            lower = min(levels)
            timestamps = [item["timestamp"] for item in cluster]

            # Aggregate sources and weights
            aggregate_sources: Dict[str, Tuple[str, Decimal]] = {}
            total_weight = Decimal("0")
            total_volatility = Decimal("0")

            for item in cluster:
                tf_label = str(item["timeframe"])
                source = str(item["source"])
                weight = Decimal(item["weight"])
                total_weight += weight
                total_volatility += Decimal(item["volatility"])

                existing = aggregate_sources.get(tf_label)
                if existing is None or weight > existing[1]:
                    aggregate_sources[tf_label] = (source, weight)

            avg_volatility = (
                total_volatility / Decimal(len(cluster)) if cluster else Decimal("0")
            )

            zones.append(
                ConfluenceZone(
                    level=center.quantize(precision),
                    upper_bound=upper.quantize(precision),
                    lower_bound=lower.quantize(precision),
                    strength=len(unique_timeframes),
                    timeframes=sorted(unique_timeframes),
                    zone_type=str(entry["zone_type"]),
                    first_touch=min(timestamps),
                    last_touch=max(timestamps),
                    weighted_strength=total_weight.quantize(precision),
                    sources={tf: src for tf, (src, _) in aggregate_sources.items()},
                    volatility=avg_volatility.quantize(precision),
                )
            )

        # Sort by strength and weighted strength
        return sorted(
            zones,
            key=lambda z: (z.strength, z.weighted_strength),
            reverse=True,
        )


# Export
__all__ = [
    "OptimizedTimeframeData",
    "OptimizedMultiTimeframeCoordinator",
]
