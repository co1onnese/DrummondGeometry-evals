"""Performance optimization utilities.

Provides caching, lazy loading, and performance monitoring.
"""

from __future__ import annotations

import functools
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

import streamlit as st

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Monitor and track performance metrics."""

    def __init__(self):
        """Initialize performance monitor."""
        self.metrics: Dict[str, Any] = {}
        self._query_times: list = []
        self._cache_hits = 0
        self._cache_misses = 0

    def record_query_time(self, query_name: str, duration: float) -> None:
        """
        Record query execution time.

        Args:
            query_name: Name of the query
            duration: Execution time in seconds
        """
        if query_name not in self.metrics:
            self.metrics[query_name] = []

        self.metrics[query_name].append(duration)
        self._query_times.append(duration)

    def get_average_query_time(self, query_name: Optional[str] = None) -> float:
        """
        Get average query time.

        Args:
            query_name: Optional specific query name

        Returns:
            Average time in seconds
        """
        if query_name:
            times = self.metrics.get(query_name, [])
            return sum(times) / len(times) if times else 0
        else:
            return sum(self._query_times) / len(self._query_times) if self._query_times else 0

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": self._cache_hits / (self._cache_hits + self._cache_misses) if (self._cache_hits + self._cache_misses) > 0 else 0,
        }

    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        self._cache_hits += 1

    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        self._cache_misses += 1

    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get performance summary.

        Returns:
            Performance summary dictionary
        """
        return {
            "total_queries": len(self._query_times),
            "avg_query_time": self.get_average_query_time(),
            "max_query_time": max(self._query_times) if self._query_times else 0,
            "min_query_time": min(self._query_times) if self._query_times else 0,
            "cache_stats": self.get_cache_stats(),
            "timestamp": datetime.now().isoformat(),
        }


# Global monitor instance
_monitor = PerformanceMonitor()


def get_monitor() -> PerformanceMonitor:
    """
    Get the global performance monitor.

    Returns:
        Monitor instance
    """
    return _monitor


def performance_timer(func: Callable) -> Callable:
    """
    Decorator to measure function execution time.

    Args:
        func: Function to wrap

    Returns:
        Wrapped function
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start_time

        monitor = get_monitor()
        monitor.record_query_time(func.__name__, duration)

        return result
    return wrapper


class CacheManager:
    """Enhanced cache manager with TTL and size limits."""

    def __init__(self, max_size: int = 100, default_ttl: int = 300):
        """
        Initialize cache manager.

        Args:
            max_size: Maximum number of cached items
            default_ttl: Default time-to-live in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_times: Dict[str, float] = {}

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if key not in self._cache:
            get_monitor().record_cache_miss()
            return None

        # Check TTL
        cache_entry = self._cache[key]
        if time.time() > cache_entry["expires_at"]:
            self._delete(key)
            get_monitor().record_cache_miss()
            return None

        # Update access time
        self._access_times[key] = time.time()
        get_monitor().record_cache_hit()

        return cache_entry["value"]

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds
        """
        # Evict if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._evict_lru()

        ttl = ttl or self.default_ttl
        expires_at = time.time() + ttl

        self._cache[key] = {
            "value": value,
            "expires_at": expires_at,
        }
        self._access_times[key] = time.time()

    def delete(self, key: str) -> None:
        """
        Delete value from cache.

        Args:
            key: Cache key
        """
        self._delete(key)

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()
        self._access_times.clear()

    def _delete(self, key: str) -> None:
        """Delete key from cache."""
        self._cache.pop(key, None)
        self._access_times.pop(key, None)

    def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if not self._access_times:
            return

        lru_key = min(self._access_times, key=self._access_times.get)
        self._delete(lru_key)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Cache statistics
        """
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "utilization": len(self._cache) / self.max_size if self.max_size > 0 else 0,
            "default_ttl": self.default_ttl,
        }


# Global cache instance
_cache = CacheManager(max_size=50, default_ttl=600)  # 10 minutes default TTL


def get_cache() -> CacheManager:
    """
    Get the global cache instance.

    Returns:
        Cache instance
    """
    return _cache


def cached_query(ttl: int = 300, key_prefix: str = ""):
    """
    Decorator for caching query results.

    Args:
        ttl: Time-to-live in seconds
        key_prefix: Prefix for cache key

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key - safely convert args/kwargs to strings
            # Handle context managers and other non-serializable objects
            def safe_str(obj):
                """Safely convert object to string for cache key."""
                try:
                    # Try normal string conversion first
                    if isinstance(obj, (str, int, float, bool, type(None))):
                        return str(obj)
                    # For tuples/lists, recursively convert
                    if isinstance(obj, (tuple, list)):
                        return f"({','.join(safe_str(item) for item in obj)})"
                    # For dicts, convert items
                    if isinstance(obj, dict):
                        return f"{{{','.join(f'{k}:{safe_str(v)}' for k, v in sorted(obj.items()))}}}"
                    # For other objects, use repr but limit length
                    return repr(obj)[:100]
                except Exception:
                    # Fallback: use object id if conversion fails
                    return f"<obj_{id(obj)}>"
            
            cache_key = f"{key_prefix}_{func.__name__}"
            try:
                cache_key += f"_{safe_str(args)}_{safe_str(sorted(kwargs.items()))}"
            except Exception:
                # Fallback: use function name and hash of args
                cache_key += f"_{hash(args)}_{hash(tuple(sorted(kwargs.items())))}"

            # Try to get from cache
            cache = get_cache()
            result = cache.get(cache_key)

            if result is not None:
                return result

            # Execute function
            result = func(*args, **kwargs)

            # Cache result
            cache.set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator


class LazyLoader:
    """Lazy loader for expensive operations."""

    def __init__(self):
        """Initialize lazy loader."""
        self._loaded: Dict[str, bool] = {}

    def is_loaded(self, key: str) -> bool:
        """
        Check if item is loaded.

        Args:
            key: Item key

        Returns:
            True if loaded
        """
        return self._loaded.get(key, False)

    def mark_loaded(self, key: str) -> None:
        """
        Mark item as loaded.

        Args:
            key: Item key
        """
        self._loaded[key] = True

    def mark_unloaded(self, key: str) -> None:
        """
        Mark item as unloaded.

        Args:
            key: Item key
        """
        self._loaded[key] = False


# Global lazy loader instance
_lazy_loader = LazyLoader()


def get_lazy_loader() -> LazyLoader:
    """
    Get the global lazy loader instance.

    Returns:
        Lazy loader instance
    """
    return _lazy_loader


# Performance optimization decorators

def lazy_property(func: Callable) -> property:
    """
    Decorator for lazy-evaluated properties.

    Args:
        func: Function to wrap

    Returns:
        Property descriptor
    """
    attr_name = f"_lazy_{func.__name__}"

    @property
    @functools.wraps(func)
    def wrapper(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, func(self))
        return getattr(self, attr_name)

    return wrapper


def measure_performance(func: Callable) -> Callable:
    """
    Decorator to measure and log performance.

    Args:
        func: Function to wrap

    Returns:
        Wrapped function
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start_time

        monitor = get_monitor()
        monitor.record_query_time(func.__name__, duration)

        logger.info(f"{func.__name__} executed in {duration:.3f}s")

        return result
    return wrapper


# Streamlit integration

def render_performance_panel() -> None:
    """Render performance monitoring panel in Streamlit."""
    monitor = get_monitor()
    cache = get_cache()

    st.subheader("Performance Metrics")

    # Query performance
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Total Queries",
            monitor.get_performance_summary()["total_queries"],
        )

    with col2:
        st.metric(
            "Avg Query Time",
            f"{monitor.get_average_query_time():.3f}s",
        )

    with col3:
        st.metric(
            "Cache Hit Rate",
            f"{monitor.get_cache_stats()['hit_rate']*100:.1f}%",
        )

    st.markdown("---")

    # Cache statistics
    st.markdown("**Cache Statistics**")
    cache_stats = cache.get_stats()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Cache Size", cache_stats["size"])

    with col2:
        st.metric("Max Size", cache_stats["max_size"])

    with col3:
        st.metric("Utilization", f"{cache_stats['utilization']*100:.1f}%")

    # Cache actions
    if st.button("Clear Cache"):
        cache.clear()
        st.success("Cache cleared!")
        st.rerun()

    st.markdown("---")

    # Detailed metrics
    with st.expander("Detailed Performance Metrics"):
        st.json(monitor.get_performance_summary())


if __name__ == "__main__":
    # Test the performance monitor
    monitor = PerformanceMonitor()
    monitor.record_query_time("test_query", 0.5)
    monitor.record_query_time("test_query", 0.3)
    monitor.record_cache_hit()
    monitor.record_cache_miss()

    print(monitor.get_performance_summary())
    print(monitor.get_cache_stats())

    # Test the cache
    cache = CacheManager()
    cache.set("key1", "value1", ttl=1)
    print(cache.get("key1"))
    time.sleep(2)
    print(cache.get("key1"))  # Should be None
