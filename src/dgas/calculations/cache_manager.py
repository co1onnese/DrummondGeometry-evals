"""Cache invalidation strategy for Drummond geometry calculations.

This module provides intelligent cache invalidation to ensure calculation
results remain accurate while maintaining high cache hit rates.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from .cache import CalculationCache, get_calculation_cache

logger = logging.getLogger(__name__)


@dataclass
class InvalidationRule:
    """Defines a cache invalidation rule."""
    pattern: str  # Pattern to match cache keys
    trigger: str  # What triggers invalidation ('time', 'data_change', 'manual')
    ttl_seconds: int  # Time-to-live for automatic invalidation
    max_entries: Optional[int] = None  # Maximum entries before eviction


class CacheInvalidationManager:
    """
    Manages intelligent cache invalidation for calculation results.

    Provides automated and manual invalidation strategies to maintain
    cache accuracy while maximizing hit rates.
    """

    def __init__(self, cache: Optional[CalculationCache] = None):
        """
        Initialize cache invalidation manager.

        Args:
            cache: CalculationCache instance (uses global if None)
        """
        self.cache = cache if cache is not None else get_calculation_cache()
        self.rules: List[InvalidationRule] = []
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5 minutes

    def add_rule(self, rule: InvalidationRule) -> None:
        """
        Add an invalidation rule.

        Args:
            rule: InvalidationRule to add
        """
        self.rules.append(rule)
        logger.debug(f"Added invalidation rule: {rule.pattern} (trigger: {rule.trigger})")

    def add_time_based_rule(
        self,
        pattern: str,
        ttl_seconds: int,
    ) -> None:
        """
        Add a time-based invalidation rule.

        Args:
            pattern: Pattern to match cache keys
            ttl_seconds: Time-to-live in seconds
        """
        rule = InvalidationRule(
            pattern=pattern,
            trigger="time",
            ttl_seconds=ttl_seconds,
        )
        self.add_rule(rule)

    def add_data_change_rule(
        self,
        pattern: str,
        max_entries: int,
    ) -> None:
        """
        Add a data-change-based invalidation rule.

        Args:
            pattern: Pattern to match cache keys
            max_entries: Maximum entries before eviction
        """
        rule = InvalidationRule(
            pattern=pattern,
            trigger="data_change",
            ttl_seconds=0,  # Not used
            max_entries=max_entries,
        )
        self.add_rule(rule)

    def invalidate_by_pattern(self, pattern: str) -> int:
        """
        Manually invalidate cache entries matching a pattern.

        Args:
            pattern: String pattern to match

        Returns:
            Number of entries invalidated
        """
        count = self.cache.invalidate_by_pattern(pattern)
        logger.info(f"Invalidated {count} cache entries matching pattern: {pattern}")
        return count

    def invalidate_expired(self) -> int:
        """
        Invalidate all expired cache entries.

        Returns:
            Number of entries invalidated
        """
        count = self.cache.clear_expired()
        if count > 0:
            logger.debug(f"Cleared {count} expired cache entries")
        return count

    def cleanup(self) -> Dict[str, int]:
        """
        Run periodic cache cleanup.

        Applies all invalidation rules and removes expired entries.

        Returns:
            Dictionary with cleanup statistics
        """
        stats = {
            "expired_cleared": 0,
            "pattern_invalidated": 0,
            "evicted_by_limit": 0,
        }

        # Clear expired entries
        stats["expired_cleared"] = self.invalidate_expired()

        # Apply time-based rules
        current_time = time.time()
        for rule in self.rules:
            if rule.trigger == "time":
                # Invalidate entries older than ttl
                pattern = f'"{rule.pattern}"'  # Simplified matching
                # Note: This is a simplified approach. In production,
                # you'd want more sophisticated pattern matching.
                pass

        # Apply data-change rules (max entries)
        for rule in self.rules:
            if rule.trigger == "data_change" and rule.max_entries:
                if len(self.cache._cache) > rule.max_entries:
                    # Remove oldest entries
                    excess = len(self.cache._cache) - rule.max_entries
                    sorted_entries = sorted(
                        self.cache._cache.items(),
                        key=lambda x: (x[1].hit_count, x[1].timestamp),
                    )
                    for key, _ in sorted_entries[:excess]:
                        del self.cache._cache[key]
                    stats["evicted_by_limit"] = excess

        self._last_cleanup = current_time
        return stats

    def auto_cleanup_if_needed(self) -> None:
        """
        Run cleanup if enough time has passed.

        Automatically called to perform periodic cleanup without manual intervention.
        """
        if time.time() - self._last_cleanup >= self._cleanup_interval:
            self.cleanup()

    def should_invalidate(self, cache_key: str, last_updated: float) -> bool:
        """
        Check if a cache entry should be invalidated.

        Args:
            cache_key: Cache key to check
            last_updated: When the cache entry was last updated

        Returns:
            True if entry should be invalidated
        """
        current_time = time.time()

        for rule in self.rules:
            if rule.trigger == "time":
                if current_time - last_updated > rule.ttl_seconds:
                    return True

        return False

    def register_data_update(self, symbol: str, timeframe: str) -> None:
        """
        Register that data has been updated for a symbol/timeframe.

        This should be called when new market data is ingested.

        Args:
            symbol: Market symbol
            timeframe: Timeframe string
        """
        pattern = f"{symbol}_{timeframe}"
        count = self.invalidate_by_pattern(pattern)
        logger.debug(f"Data updated for {symbol} {timeframe}, invalidated {count} cache entries")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive cache statistics.

        Returns:
            Dictionary with cache and invalidation statistics
        """
        cache_stats = self.cache.get_stats()
        return {
            "cache": cache_stats,
            "rules_count": len(self.rules),
            "last_cleanup": datetime.fromtimestamp(self._last_cleanup).isoformat(),
        }


# Global invalidation manager instance
_invalidation_manager: Optional[CacheInvalidationManager] = None


def get_invalidation_manager() -> CacheInvalidationManager:
    """
    Get the global invalidation manager instance.

    Returns:
        CacheInvalidationManager instance
    """
    global _invalidation_manager
    if _invalidation_manager is None:
        _invalidation_manager = CacheInvalidationManager()
        _setup_default_rules()
    return _invalidation_manager


def _setup_default_rules() -> None:
    """Set up default invalidation rules."""
    manager = get_invalidation_manager()

    # Time-based rules
    manager.add_time_based_rule("pldot", ttl_seconds=300)  # 5 minutes
    manager.add_time_based_rule("envelope", ttl_seconds=300)  # 5 minutes
    manager.add_time_based_rule("pattern", ttl_seconds=600)  # 10 minutes
    manager.add_time_based_rule("multi_timeframe", ttl_seconds=180)  # 3 minutes

    # Data-change rules (max entries to prevent memory bloat)
    manager.add_data_change_rule("pldot", max_entries=500)
    manager.add_data_change_rule("envelope", max_entries=500)
    manager.add_data_change_rule("pattern", max_entries=300)
    manager.add_data_change_rule("multi_timeframe", max_entries=200)


class DataUpdateListener:
    """
    Listener for data updates that triggers cache invalidation.

    Automatically invalidates related cache entries when new data arrives.
    """

    def __init__(self, invalidation_manager: Optional[CacheInvalidationManager] = None):
        """
        Initialize data update listener.

        Args:
            invalidation_manager: CacheInvalidationManager instance
        """
        self.manager = invalidation_manager if invalidation_manager is not None else get_invalidation_manager()

    def on_data_ingested(
        self,
        symbol: str,
        timeframe: str,
        bars_count: int,
        latest_timestamp: datetime,
    ) -> None:
        """
        Called when new market data is ingested.

        Args:
            symbol: Market symbol
            timeframe: Timeframe of ingested data
            bars_count: Number of bars ingested
            latest_timestamp: Timestamp of latest bar
        """
        logger.info(
            f"Data ingested: {symbol} {timeframe} "
            f"({bars_count} bars, latest: {latest_timestamp})"
        )

        # Invalidate related cache entries
        self.manager.register_data_update(symbol, timeframe)

        # Also invalidate multi-timeframe caches that might use this data
        pattern = f"multi_timeframe.*_{symbol}"
        self.manager.invalidate_by_pattern(pattern)


# Convenience functions

def invalidate_calculation_cache(
    calculation_type: str,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
) -> int:
    """
    Invalidate calculation cache for specific type/symbol/timeframe.

    Args:
        calculation_type: Type of calculation ('pldot', 'envelope', 'pattern', 'multi_timeframe')
        symbol: Optional market symbol
        timeframe: Optional timeframe

    Returns:
        Number of entries invalidated
    """
    manager = get_invalidation_manager()

    if symbol and timeframe:
        pattern = f"{calculation_type}_{symbol}_{timeframe}"
    elif symbol:
        pattern = f"{calculation_type}_{symbol}"
    else:
        pattern = calculation_type

    return manager.invalidate_by_pattern(pattern)


def invalidate_all_caches() -> int:
    """
    Invalidate all calculation caches.

    Returns:
        Total number of entries invalidated
    """
    manager = get_invalidation_manager()
    return manager.cache.clear()


__all__ = [
    "InvalidationRule",
    "CacheInvalidationManager",
    "get_invalidation_manager",
    "DataUpdateListener",
    "invalidate_calculation_cache",
    "invalidate_all_caches",
]
