"""Calculation result caching with TTL for Drummond geometry computations.

This module provides a specialized caching layer for expensive calculation operations
to achieve the <200ms per symbol/timeframe target.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from ..data.models import IntervalData
from .envelopes import EnvelopeSeries
from .pldot import PLDotSeries

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheKey:
    """Represents a cache key for calculation results."""
    calculation_type: str  # 'pldot', 'envelope', 'pattern'
    symbol: str
    timeframe: str
    parameters: Dict[str, Any]  # Calculation parameters
    data_hash: str  # Hash of input data

    def to_string(self) -> str:
        """Convert to string for caching."""
        key_data = {
            "type": self.calculation_type,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "parameters": self.parameters,
            "data_hash": self.data_hash,
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()


@dataclass
class CachedResult:
    """Cached calculation result with metadata."""
    result: Any
    timestamp: float
    ttl_seconds: int
    hit_count: int = 0
    computation_time_ms: float = 0.0

    @property
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() - self.timestamp > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        """Get age of cache entry in seconds."""
        return time.time() - self.timestamp


class CalculationCache:
    """
    Specialized cache for Drummond geometry calculations.

    Provides fast, memory-efficient caching of calculation results with
    automatic invalidation and performance tracking.
    """

    def __init__(
        self,
        max_size: int = 2000,
        default_ttl_seconds: int = 300,  # 5 minutes
    ):
        """
        Initialize calculation cache.

        Args:
            max_size: Maximum number of cache entries
            default_ttl_seconds: Default time-to-live in seconds
        """
        self._cache: dict[str, CachedResult] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl_seconds
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(
        self,
        cache_key: CacheKey,
    ) -> Optional[Any]:
        """
        Get cached result for a calculation.

        Args:
            cache_key: Cache key for the calculation

        Returns:
            Cached result if available and not expired, None otherwise
        """
        key_str = cache_key.to_string()
        entry = self._cache.get(key_str)

        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired:
            # Remove expired entry
            del self._cache[key_str]
            self._misses += 1
            return None

        # Update hit count
        entry.hit_count += 1
        self._hits += 1

        return entry.result

    def set(
        self,
        cache_key: CacheKey,
        result: Any,
        ttl_seconds: Optional[int] = None,
        computation_time_ms: float = 0.0,
    ) -> None:
        """
        Cache a calculation result.

        Args:
            cache_key: Cache key for the calculation
            result: Calculation result to cache
            ttl_seconds: Time-to-live for this cache entry (uses default if None)
            computation_time_ms: Time taken to compute result
        """
        key_str = cache_key.to_string()
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        # Evict entries if cache is full
        if len(self._cache) >= self._max_size and key_str not in self._cache:
            self._evict_lru()

        self._cache[key_str] = CachedResult(
            result=result,
            timestamp=time.time(),
            ttl_seconds=ttl,
            hit_count=0,
            computation_time_ms=computation_time_ms,
        )

    def _evict_lru(self) -> None:
        """Evict least recently used cache entry."""
        if not self._cache:
            return

        # Find entry with minimum hit count and oldest timestamp
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: (self._cache[k].hit_count, self._cache[k].timestamp),
        )
        del self._cache[oldest_key]
        self._evictions += 1

    def invalidate_by_pattern(self, pattern: str) -> int:
        """
        Invalidate cache entries matching a pattern.

        Args:
            pattern: String pattern to match in cache keys

        Returns:
            Number of entries invalidated
        """
        keys_to_delete = [k for k in self._cache.keys() if pattern in k]
        for key in keys_to_delete:
            del self._cache[key]
        return len(keys_to_delete)

    def clear_expired(self) -> int:
        """
        Clear all expired cache entries.

        Returns:
            Number of entries cleared
        """
        keys_to_delete = [
            k for k, v in self._cache.items() if v.is_expired
        ]
        for key in keys_to_delete:
            del self._cache[key]
        return len(keys_to_delete)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        total_requests = self._hits + self._misses
        hit_rate = (
            (self._hits / total_requests * 100) if total_requests > 0 else 0
        )

        # Calculate average computation time saved
        total_time_saved = sum(
            entry.computation_time_ms * entry.hit_count
            for entry in self._cache.values()
        )

        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": hit_rate,
            "evictions": self._evictions,
            "total_time_saved_ms": total_time_saved,
            "expired_entries": sum(1 for v in self._cache.values() if v.is_expired),
        }

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0


def compute_data_hash(intervals: List[IntervalData]) -> str:
    """
    Compute a hash of input data for cache key generation.

    Args:
        intervals: List of IntervalData

    Returns:
        SHA256 hash of the data
    """
    if not intervals:
        return "empty"

    # Use a subset of data for hashing (first, last, and count)
    # This is much faster than hashing all data
    hash_data = {
        "count": len(intervals),
        "start": intervals[0].timestamp.isoformat() if intervals else None,
        "end": intervals[-1].timestamp.isoformat() if intervals else None,
        "symbol": intervals[0].symbol if intervals else None,
    }

    hash_str = json.dumps(hash_data, sort_keys=True, default=str)
    return hashlib.sha256(hash_str.encode()).hexdigest()


class CachedCalculator:
    """
    Base class for cached calculation operations.

    Provides a convenient interface for adding caching to calculation operations.
    """

    def __init__(self, cache: CalculationCache):
        """
        Initialize cached calculator.

        Args:
            cache: CalculationCache instance
        """
        self.cache = cache

    def get_or_compute(
        self,
        calculation_type: str,
        symbol: str,
        timeframe: str,
        parameters: Dict[str, Any],
        data: List[IntervalData],
        compute_func: callable,
        ttl_seconds: Optional[int] = None,
    ) -> Tuple[Any, bool]:
        """
        Get cached result or compute and cache.

        Args:
            calculation_type: Type of calculation ('pldot', 'envelope', 'pattern')
            symbol: Market symbol
            timeframe: Timeframe string
            parameters: Calculation parameters
            data: Input data for calculation
            compute_func: Function to compute result if not cached
            ttl_seconds: Time-to-live for cache entry

        Returns:
            Tuple of (result, is_cached)
        """
        data_hash = compute_data_hash(data)
        cache_key = CacheKey(
            calculation_type=calculation_type,
            symbol=symbol,
            timeframe=timeframe,
            parameters=parameters,
            data_hash=data_hash,
        )

        # Try to get from cache
        cached_result = self.cache.get(cache_key)
        if cached_result is not None:
            return (cached_result, True)

        # Compute result
        start_time = time.time()
        try:
            result = compute_func(data, **parameters)
            computation_time_ms = (time.time() - start_time) * 1000

            # Cache result
            self.cache.set(
                cache_key,
                result,
                ttl_seconds=ttl_seconds,
                computation_time_ms=computation_time_ms,
            )

            return (result, False)
        except Exception as e:
            logger.error(f"Calculation failed: {e}")
            raise


# Global calculation cache instance
_calculation_cache: Optional[CalculationCache] = None


def get_calculation_cache() -> CalculationCache:
    """
    Get the global calculation cache instance.

    Returns:
        CalculationCache instance
    """
    global _calculation_cache
    if _calculation_cache is None:
        _calculation_cache = CalculationCache(
            max_size=2000,
            default_ttl_seconds=300,  # 5 minutes
        )
    return _calculation_cache


class CachedPLDotCalculator:
    """Cached PLdot calculator with automatic caching."""

    def __init__(self, displacement: int = 1):
        """
        Initialize cached PLdot calculator.

        Args:
            displacement: PLdot displacement parameter
        """
        self.displacement = displacement
        self.cache = get_calculation_cache()
        self.calculator = self._create_calculator()

    def _create_calculator(self):
        """Create underlying PLdot calculator."""
        from .pldot import PLDotCalculator
        return PLDotCalculator(displacement=self.displacement)

    def calculate(
        self,
        symbol: str,
        timeframe: str,
        intervals: List[IntervalData],
        use_cache: bool = True,
        ttl_seconds: int = 300,
    ) -> List[PLDotSeries]:
        """
        Calculate PLdot with caching.

        Args:
            symbol: Market symbol
            timeframe: Timeframe string
            intervals: List of IntervalData
            use_cache: Whether to use cache
            ttl_seconds: Cache TTL in seconds

        Returns:
            List of PLDotSeries
        """
        if not use_cache:
            return self.calculator.from_intervals(intervals)

        parameters = {"displacement": self.displacement}
        cached_calc = CachedCalculator(self.cache)
        result, is_cached = cached_calc.get_or_compute(
            calculation_type="pldot",
            symbol=symbol,
            timeframe=timeframe,
            parameters=parameters,
            data=intervals,
            compute_func=lambda data, **params: self.calculator.from_intervals(data),
            ttl_seconds=ttl_seconds,
        )

        return result


class CachedEnvelopeCalculator:
    """Cached envelope calculator with automatic caching."""

    def __init__(
        self,
        method: str = "pldot_range",
        period: int = 3,
        multiplier: float = 1.5,
        percent: float = 0.02,
    ):
        """
        Initialize cached envelope calculator.

        Args:
            method: Envelope calculation method
            period: Calculation period
            multiplier: Envelope multiplier
            percent: Percentage for percentage method
        """
        self.method = method
        self.period = period
        self.multiplier = multiplier
        self.percent = percent
        self.cache = get_calculation_cache()
        self.calculator = self._create_calculator()

    def _create_calculator(self):
        """Create underlying envelope calculator."""
        from .envelopes import EnvelopeCalculator
        return EnvelopeCalculator(
            method=self.method,
            period=self.period,
            multiplier=self.multiplier,
            percent=self.percent,
        )

    def calculate(
        self,
        symbol: str,
        timeframe: str,
        intervals: List[IntervalData],
        pldot: List[PLDotSeries],
        use_cache: bool = True,
        ttl_seconds: int = 300,
    ) -> List[EnvelopeSeries]:
        """
        Calculate envelopes with caching.

        Args:
            symbol: Market symbol
            timeframe: Timeframe string
            intervals: List of IntervalData
            pldot: List of PLDotSeries
            use_cache: Whether to use cache
            ttl_seconds: Cache TTL in seconds

        Returns:
            List of EnvelopeSeries
        """
        if not use_cache:
            return self.calculator.from_intervals(intervals, pldot)

        # Combine intervals and pldot for data hash
        combined_data = intervals + pldot
        parameters = {
            "method": self.method,
            "period": self.period,
            "multiplier": self.multiplier,
            "percent": self.percent,
        }
        cached_calc = CachedCalculator(self.cache)
        result, is_cached = cached_calc.get_or_compute(
            calculation_type="envelope",
            symbol=symbol,
            timeframe=timeframe,
            parameters=parameters,
            data=combined_data,
            compute_func=lambda data, **params: self.calculator.from_intervals(intervals, pldot),
            ttl_seconds=ttl_seconds,
        )

        return result


__all__ = [
    "CacheKey",
    "CachedResult",
    "CalculationCache",
    "CachedCalculator",
    "get_calculation_cache",
    "compute_data_hash",
    "CachedPLDotCalculator",
    "CachedEnvelopeCalculator",
]
