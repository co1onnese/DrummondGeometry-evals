"""Calculation profiling and caching for Drummond geometry performance optimization.

This module provides utilities to profile and cache Drummond geometry calculations
to achieve the target of <200ms per symbol/timeframe bundle.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ..db.query_cache import get_cache_manager

logger = logging.getLogger(__name__)


@dataclass
class CalculationMetrics:
    """Metrics for a single calculation operation."""
    calculation_type: str
    symbol: str
    timeframe: str
    execution_time_ms: float
    success: bool
    timestamp: float
    cache_hit: bool = False


class CalculationProfiler:
    """
    Profile Drummond geometry calculations to identify performance bottlenecks.

    Tracks execution time, cache hit rates, and identifies slow operations
    that need optimization.
    """

    def __init__(self):
        """Initialize calculation profiler."""
        self._metrics: list[CalculationMetrics] = []
        self._enabled = True

    def record_calculation(
        self,
        calculation_type: str,
        symbol: str,
        timeframe: str,
        execution_time_ms: float,
        success: bool,
        cache_hit: bool = False,
    ) -> None:
        """
        Record metrics for a calculation.

        Args:
            calculation_type: Type of calculation (e.g., 'pldot', 'envelope', 'pattern')
            symbol: Market symbol
            timeframe: Timeframe (e.g., '1h', '30min')
            execution_time_ms: Execution time in milliseconds
            success: Whether calculation succeeded
            cache_hit: Whether result came from cache
        """
        if not self._enabled:
            return

        self._metrics.append(
            CalculationMetrics(
                calculation_type=calculation_type,
                symbol=symbol,
                timeframe=timeframe,
                execution_time_ms=execution_time_ms,
                success=success,
                timestamp=time.time(),
                cache_hit=cache_hit,
            )
        )

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of calculation performance.

        Returns:
            Dictionary with summary statistics
        """
        if not self._metrics:
            return {
                "total_calculations": 0,
                "avg_time_ms": 0.0,
                "cache_hit_rate": 0.0,
            }

        # Calculate statistics
        total = len(self._metrics)
        avg_time = sum(m.execution_time_ms for m in self._metrics) / total
        cache_hits = sum(1 for m in self._metrics if m.cache_hit)
        cache_hit_rate = (cache_hits / total * 100) if total > 0 else 0.0

        # By calculation type
        by_type: Dict[str, Any] = {}
        for metric in self._metrics:
            ctype = metric.calculation_type
            if ctype not in by_type:
                by_type[ctype] = {
                    "count": 0,
                    "total_time_ms": 0.0,
                    "avg_time_ms": 0.0,
                    "cache_hits": 0,
                }
            by_type[ctype]["count"] += 1
            by_type[ctype]["total_time_ms"] += metric.execution_time_ms
            if metric.cache_hit:
                by_type[ctype]["cache_hits"] += 1

        # Calculate averages per type
        for ctype, data in by_type.items():
            data["avg_time_ms"] = data["total_time_ms"] / data["count"]
            data["cache_hit_rate"] = (
                data["cache_hits"] / data["count"] * 100
            ) if data["count"] > 0 else 0.0

        return {
            "total_calculations": total,
            "avg_time_ms": avg_time,
            "cache_hit_rate": cache_hit_rate,
            "by_type": by_type,
        }

    def clear(self) -> None:
        """Clear all metrics."""
        self._metrics.clear()

    def enable(self) -> None:
        """Enable profiling."""
        self._enabled = True

    def disable(self) -> None:
        """Disable profiling."""
        self._enabled = False


class CachedCalculationEngine:
    """
    Cached calculation engine for Drummond geometry.

    Provides a caching layer for calculation results to avoid redundant
    computations and improve performance.
    """

    def __init__(self):
        """Initialize cached calculation engine."""
        self.cache_manager = get_cache_manager()
        self.profiler = CalculationProfiler()

    def get_cached_calculation(
        self,
        cache_key: str,
        calculation_func: Callable,
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute a calculation with caching.

        Args:
            cache_key: Unique key for this calculation
            calculation_func: Function to execute if not cached
            *args: Positional arguments for calculation function
            **kwargs: Keyword arguments for calculation function

        Returns:
            Calculation result
        """
        # Try to get from cache
        cache = self.cache_manager.get_cache("calculations")
        if cache is not None:
            cached_result = cache.get(cache_key, tuple())
            if cached_result is not None:
                return cached_result

        # Execute calculation
        start_time = time.time()
        try:
            result = calculation_func(*args, **kwargs)
            success = True
            return result
        finally:
            execution_time_ms = (time.time() - start_time) * 1000

            # Record metrics (without symbol/timeframe - would need to be passed)
            self.profiler.record_calculation(
                calculation_type="unknown",
                symbol="unknown",
                timeframe="unknown",
                execution_time_ms=execution_time_ms,
                success=success if 'success' in locals() else True,
                cache_hit=False,
            )

    def cache_calculation(
        self,
        cache_key: str,
        result: Any,
        ttl_seconds: int = 300,
    ) -> None:
        """
        Cache a calculation result.

        Args:
            cache_key: Unique key for this calculation
            result: Result to cache
            ttl_seconds: Time-to-live in seconds
        """
        cache = self.cache_manager.get_cache("calculations")
        if cache is not None:
            cache.set(cache_key, tuple(), result, ttl_seconds)


# Global profiler instance
_calculation_profiler: Optional[CalculationProfiler] = None


def get_calculation_profiler() -> CalculationProfiler:
    """
    Get the global calculation profiler instance.

    Returns:
        CalculationProfiler instance
    """
    global _calculation_profiler
    if _calculation_profiler is None:
        _calculation_profiler = CalculationProfiler()
    return _calculation_profiler


# Global cached calculation engine
_cached_engine: Optional[CachedCalculationEngine] = None


def get_cached_calculation_engine() -> CachedCalculationEngine:
    """
    Get the global cached calculation engine instance.

    Returns:
        CachedCalculationEngine instance
    """
    global _cached_engine
    if _cached_engine is None:
        _cached_engine = CachedCalculationEngine()
    return _cached_engine


__all__ = [
    "CalculationMetrics",
    "CalculationProfiler",
    "CachedCalculationEngine",
    "get_calculation_profiler",
    "get_cached_calculation_engine",
]
