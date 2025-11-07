"""Query result caching with TTL for improved performance.

This module provides a lightweight caching layer for database query results,
with configurable TTL (time-to-live) to reduce database load and improve
response times for frequently-accessed data.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheEntry:
    """Represents a cached query result with metadata."""
    result: Any
    timestamp: float
    ttl_seconds: int
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        return time.time() - self.timestamp > self.ttl_seconds


class QueryCache:
    """
    In-memory cache for database query results.

    Provides fast access to frequently-queried data with configurable TTL.
    Designed for read-heavy workloads like dashboard queries and signal lookups.

    Note: This is an in-memory cache suitable for single-process deployments.
    For multi-process or distributed deployments, consider using Redis.
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize query cache.

        Args:
            max_size: Maximum number of cache entries before eviction
        """
        self._cache: dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _make_key(self, query: str, params: tuple) -> str:
        """
        Create a cache key from query and parameters.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            Hashed cache key
        """
        # Serialize query and params to create a unique key
        key_data = {
            "query": query,
            "params": params,
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, query: str, params: tuple) -> Optional[Any]:
        """
        Get cached result for a query.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            Cached result if available and not expired, None otherwise
        """
        key = self._make_key(query, params)
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired:
            # Remove expired entry
            del self._cache[key]
            self._misses += 1
            return None

        # Update hit count
        self._cache[key] = CacheEntry(
            result=entry.result,
            timestamp=entry.timestamp,
            ttl_seconds=entry.ttl_seconds,
            hit_count=entry.hit_count + 1,
        )
        self._hits += 1

        return entry.result

    def set(
        self,
        query: str,
        params: tuple,
        result: Any,
        ttl_seconds: int,
    ) -> None:
        """
        Cache a query result.

        Args:
            query: SQL query string
            params: Query parameters tuple
            result: Query result to cache
            ttl_seconds: Time-to-live for this cache entry
        """
        key = self._make_key(query, params)

        # Evict oldest entries if cache is full
        if len(self._cache) >= self._max_size and key not in self._cache:
            self._evict_lru()

        self._cache[key] = CacheEntry(
            result=result,
            timestamp=time.time(),
            ttl_seconds=ttl_seconds,
            hit_count=0,
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

    def invalidate(self, pattern: Optional[str] = None) -> int:
        """
        Invalidate cache entries.

        Args:
            pattern: Optional string pattern to match (all entries if None)

        Returns:
            Number of entries invalidated
        """
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            return count

        # Invalidate entries matching pattern
        keys_to_delete = [
            key for key in self._cache.keys()
            if pattern in key
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

        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": hit_rate,
            "evictions": self._evictions,
        }

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0


class QueryCacheManager:
    """
    Manages query cache instances for different use cases.

    Provides separate cache instances with different TTLs for:
    - Dashboard queries (short TTL, 30 seconds)
    - Recent signals (medium TTL, 5 minutes)
    - Performance metrics (long TTL, 1 hour)
    """

    def __init__(self):
        """Initialize cache manager with separate caches for different data types."""
        self._caches: Dict[str, QueryCache] = {
            "dashboard": QueryCache(max_size=500),
            "signals": QueryCache(max_size=1000),
            "metrics": QueryCache(max_size=200),
            "market_data": QueryCache(max_size=800),
        }

    def get_cache(self, cache_name: str) -> Optional[QueryCache]:
        """
        Get a cache instance by name.

        Args:
            cache_name: Name of the cache ('dashboard', 'signals', 'metrics', 'market_data')

        Returns:
            QueryCache instance or None if not found
        """
        return self._caches.get(cache_name)

    def get_or_create_cache(
        self,
        cache_name: str,
        max_size: int = 1000,
    ) -> QueryCache:
        """
        Get a cache instance by name, creating it if it doesn't exist.

        Args:
            cache_name: Name of the cache
            max_size: Maximum size for the cache if created

        Returns:
            QueryCache instance
        """
        if cache_name not in self._caches:
            self._caches[cache_name] = QueryCache(max_size=max_size)
        return self._caches[cache_name]

    def invalidate_all(self) -> Dict[str, int]:
        """
        Invalidate all caches.

        Returns:
            Dictionary mapping cache name to number of entries invalidated
        """
        results = {}
        for name, cache in self._caches.items():
            results[name] = len(cache._cache)
            cache.clear()
        return results

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all caches.

        Returns:
            Dictionary mapping cache name to statistics dictionary
        """
        return {
            name: cache.get_stats()
            for name, cache in self._caches.items()
        }


# Global cache manager instance
_cache_manager: Optional[QueryCacheManager] = None


def get_cache_manager() -> QueryCacheManager:
    """
    Get the global cache manager instance.

    Returns:
        QueryCacheManager instance
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = QueryCacheManager()
    return _cache_manager


def cached_query(
    cache_name: str,
    query: str,
    params: tuple,
    ttl_seconds: int,
) -> Any:
    """
    Decorator for caching database query results.

    Args:
        cache_name: Name of the cache to use
        query: SQL query string (for cache key)
        params: Query parameters (for cache key)
        ttl_seconds: Time-to-live for cache entry

    Usage:
        @cached_query('dashboard', query, params, ttl=30)
        def fetch_dashboard_data(conn, query, params):
            ...

    Note: This is a convenience decorator. For complex cases, use
    get_cache_manager().get_cache(cache_name) directly.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache = get_cache_manager().get_cache(cache_name)
            if cache is None:
                return func(*args, **kwargs)

            # Try to get from cache
            result = cache.get(query, params)
            if result is not None:
                return result

            # Execute query and cache result
            result = func(*args, **kwargs)
            cache.set(query, params, result, ttl_seconds)
            return result
        return wrapper
    return decorator


__all__ = [
    "QueryCache",
    "QueryCacheManager",
    "get_cache_manager",
    "cached_query",
]
