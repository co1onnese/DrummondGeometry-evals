"""Tests for performance optimization system."""

import time
import pytest
from unittest.mock import Mock, patch, MagicMock
from dgas.dashboard.performance.optimizer import (
    PerformanceMonitor,
    CacheManager,
    LazyLoader,
    CacheEntry,
)


class TestCacheEntry:
    """Test CacheEntry data class."""

    def test_cache_entry_creation(self):
        """Test creating a cache entry."""
        entry = CacheEntry(
            key="test_key",
            value={"data": "test_data"},
            timestamp=time.time(),
            ttl=300
        )

        assert entry.key == "test_key"
        assert entry.value == {"data": "test_data"}
        assert entry.timestamp is not None
        assert entry.ttl == 300

    def test_cache_entry_is_expired(self):
        """Test checking if cache entry is expired."""
        now = time.time()

        # Not expired
        entry1 = CacheEntry(
            key="test1",
            value="value1",
            timestamp=now,
            ttl=300
        )
        assert entry1.is_expired() is False

        # Expired
        entry2 = CacheEntry(
            key="test2",
            value="value2",
            timestamp=now - 500,
            ttl=300
        )
        assert entry2.is_expired() is True

    def test_cache_entry_touches(self):
        """Test touching a cache entry updates timestamp."""
        entry = CacheEntry(
            key="test",
            value="value",
            timestamp=time.time(),
            ttl=300
        )

        old_timestamp = entry.timestamp
        time.sleep(0.01)  # Small delay
        entry.touch()

        assert entry.timestamp > old_timestamp


class TestCacheManager:
    """Test CacheManager functionality."""

    @pytest.fixture
    def cache(self):
        """Create a test cache manager."""
        return CacheManager(max_size=100, default_ttl=300)

    def test_cache_initialization(self, cache):
        """Test cache initializes correctly."""
        assert cache.max_size == 100
        assert cache.default_ttl == 300
        assert isinstance(cache._cache, dict)
        assert isinstance(cache._access_order, list)

    def test_cache_set(self, cache):
        """Test setting values in cache."""
        cache.set("key1", "value1")
        assert "key1" in cache._cache

        entry = cache._cache["key1"]
        assert entry.value == "value1"
        assert entry.ttl == cache.default_ttl

    def test_cache_set_with_custom_ttl(self, cache):
        """Test setting value with custom TTL."""
        cache.set("key2", "value2", ttl=600)

        entry = cache._cache["key2"]
        assert entry.ttl == 600

    def test_cache_get(self, cache):
        """Test getting values from cache."""
        cache.set("key3", "value3")
        value = cache.get("key3")

        assert value == "value3"

    def test_cache_get_not_found(self, cache):
        """Test getting non-existent value."""
        value = cache.get("nonexistent")
        assert value is None

    def test_cache_get_expired(self, cache):
        """Test getting expired value."""
        cache.set("key4", "value4", ttl=1)  # 1 second TTL
        time.sleep(1.1)  # Wait for expiration

        value = cache.get("key4")
        assert value is None

    def test_cache_delete(self, cache):
        """Test deleting values from cache."""
        cache.set("key5", "value5")
        assert "key5" in cache._cache

        cache.delete("key5")
        assert "key5" not in cache._cache

    def test_cache_clear(self, cache):
        """Test clearing all cache values."""
        cache.set("key6", "value6")
        cache.set("key7", "value7")
        cache.set("key8", "value8")

        assert len(cache._cache) == 3

        cache.clear()
        assert len(cache._cache) == 0

    def test_cache_size_limit(self, cache):
        """Test cache size limit enforcement."""
        small_cache = CacheManager(max_size=3, default_ttl=300)

        small_cache.set("k1", "v1")
        small_cache.set("k2", "v2")
        small_cache.set("k3", "v3")
        small_cache.set("k4", "v4")  # Should evict oldest

        assert "k1" not in small_cache._cache
        assert "k2" in small_cache._cache
        assert "k3" in small_cache._cache
        assert "k4" in small_cache._cache

    def test_cache_lru_eviction(self, cache):
        """Test LRU eviction on access."""
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.set("k3", "v3")
        cache.set("k4", "v4")  # Should evict k1

        # Access k2 (makes it recently used)
        cache.get("k2")

        # Add one more to evict
        cache.set("k5", "v5")

        # k2 should NOT be evicted, but k3 should be
        assert "k1" not in cache._cache
        assert "k2" in cache._cache
        assert "k3" not in cache._cache

    def test_cache_get_stats(self, cache):
        """Test getting cache statistics."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Miss
        cache.get("nonexistent")

        # Hit
        cache.get("key1")

        stats = cache.get_stats()

        assert stats["total_keys"] == 2
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert "hit_rate" in stats

    def test_cache_contains(self, cache):
        """Test checking if key exists in cache."""
        cache.set("key1", "value1")

        assert "key1" in cache
        assert "key2" not in cache

    def test_cache_keys(self, cache):
        """Test getting all cache keys."""
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.set("k3", "v3")

        keys = cache.keys()
        assert len(keys) == 3
        assert "k1" in keys
        assert "k2" in keys
        assert "k3" in keys

    def test_cache_values(self, cache):
        """Test getting all cache values."""
        cache.set("k1", "v1")
        cache.set("k2", "v2")

        values = cache.values()
        assert "v1" in values
        assert "v2" in values

    def test_cache_update(self, cache):
        """Test updating existing cache value."""
        cache.set("key1", "value1")
        cache.set("key1", "value1_updated")

        entry = cache._cache["key1"]
        assert entry.value == "value1_updated"

    def test_cache_ttl_extension(self, cache):
        """Test extending TTL on access."""
        cache.set("key1", "value1", ttl=1)
        time.sleep(0.5)

        # Access should extend TTL
        cache.get("key1")

        time.sleep(0.5)  # Total 1 second
        value = cache.get("key1")  # Should still be valid

        assert value is not None


class TestLazyLoader:
    """Test LazyLoader functionality."""

    def test_lazy_loader_initialization(self):
        """Test lazy loader initializes correctly."""
        loader = LazyLoader("test_loader")
        assert loader.loader_id == "test_loader"
        assert not loader.is_loaded()
        assert loader._loaded_at is None

    def test_mark_loaded(self):
        """Test marking loader as loaded."""
        loader = LazyLoader("test")
        assert not loader.is_loaded()

        loader.mark_loaded()
        assert loader.is_loaded()
        assert loader._loaded_at is not None

    def test_mark_unloaded(self):
        """Test marking loader as unloaded."""
        loader = LazyLoader("test")
        loader.mark_loaded()
        assert loader.is_loaded()

        loader.mark_unloaded()
        assert not loader.is_loaded()
        assert loader._loaded_at is None

    def test_mark_loaded_multiple_times(self):
        """Test marking loaded multiple times."""
        loader = LazyLoader("test")
        loader.mark_loaded()
        first_timestamp = loader._loaded_at

        time.sleep(0.01)
        loader.mark_loaded()
        second_timestamp = loader._loaded_at

        # Timestamp should update
        assert second_timestamp >= first_timestamp


class TestPerformanceMonitor:
    """Test PerformanceMonitor functionality."""

    @pytest.fixture
    def monitor(self):
        """Create a test performance monitor."""
        return PerformanceMonitor()

    def test_monitor_initialization(self, monitor):
        """Test monitor initializes correctly."""
        assert isinstance(monitor.query_times, list)
        assert isinstance(monitor.query_count, dict)
        assert monitor.slow_query_threshold == 1.0  # 1 second

    def test_record_query_time(self, monitor):
        """Test recording query execution time."""
        monitor.record_query_time("SELECT * FROM table", 0.5)

        assert len(monitor.query_times) == 1
        assert monitor.query_times[0]["query"] == "SELECT * FROM table"
        assert monitor.query_times[0]["duration"] == 0.5

    def test_record_fast_query(self, monitor):
        """Test recording a fast query."""
        monitor.record_query_time("SELECT 1", 0.1)

        # Should be in normal queries
        assert len(monitor.query_times) == 1

    def test_record_slow_query(self, monitor):
        """Test recording a slow query."""
        monitor.record_query_time("SELECT * FROM large_table", 2.0)

        # Should be marked as slow
        last_query = monitor.query_times[-1]
        assert last_query["duration"] == 2.0

    def test_get_performance_summary(self, monitor):
        """Test getting performance summary."""
        monitor.record_query_time("Q1", 0.5)
        monitor.record_query_time("Q2", 0.3)
        monitor.record_query_time("Q3", 0.7)

        summary = monitor.get_performance_summary()

        assert "total_queries" in summary
        assert "average_time" in summary
        assert "min_time" in summary
        assert "max_time" in summary
        assert "total_time" in summary

        assert summary["total_queries"] == 3
        assert summary["average_time"] == pytest.approx(0.5, rel=1e-2)

    def test_get_cache_stats(self, monitor):
        """Test getting cache statistics."""
        # Simulate some cache operations
        monitor.cache_stats["hits"] = 10
        monitor.cache_stats["misses"] = 3
        monitor.cache_stats["evictions"] = 2

        stats = monitor.get_cache_stats()

        assert stats["hits"] == 10
        assert stats["misses"] == 3
        assert stats["evictions"] == 2
        assert "hit_rate" in stats
        assert stats["hit_rate"] == pytest.approx(10/13, rel=1e-2)

    def test_slow_query_detection(self, monitor):
        """Test detecting slow queries."""
        monitor.slow_query_threshold = 0.5

        monitor.record_query_time("Fast query", 0.1)
        monitor.record_query_time("Slow query", 1.0)

        summary = monitor.get_performance_summary()
        assert summary["total_queries"] == 2
        assert summary["max_time"] == 1.0

    def test_query_count_tracking(self, monitor):
        """Test tracking query counts by type."""
        monitor.record_query_time("SELECT * FROM predictions", 0.5)
        monitor.record_query_time("SELECT * FROM predictions", 0.3)
        monitor.record_query_time("SELECT * FROM signals", 0.4)

        assert monitor.query_count["SELECT * FROM predictions"] == 2
        assert monitor.query_count["SELECT * FROM signals"] == 1

    def test_clear_metrics(self, monitor):
        """Test clearing performance metrics."""
        monitor.record_query_time("Q1", 0.5)
        monitor.record_query_time("Q2", 0.3)

        assert len(monitor.query_times) == 2

        monitor.clear_metrics()

        assert len(monitor.query_times) == 0
        assert len(monitor.query_count) == 0

    def test_export_metrics(self, monitor):
        """Test exporting performance metrics."""
        monitor.record_query_time("Q1", 0.5)
        monitor.record_query_time("Q2", 0.3)

        metrics = monitor.export_metrics()

        assert "query_times" in metrics
        assert "query_count" in metrics
        assert "cache_stats" in metrics
        assert "summary" in metrics

        assert len(metrics["query_times"]) == 2

    def test_set_slow_query_threshold(self, monitor):
        """Test setting slow query threshold."""
        assert monitor.slow_query_threshold == 1.0

        monitor.set_slow_query_threshold(2.0)
        assert monitor.slow_query_threshold == 2.0

    def test_get_slow_queries(self, monitor):
        """Test getting slow queries."""
        monitor.slow_query_threshold = 0.5

        monitor.record_query_time("Fast", 0.1)
        monitor.record_query_time("Slow1", 1.0)
        monitor.record_query_time("Slow2", 2.0)

        slow_queries = monitor.get_slow_queries()

        assert len(slow_queries) == 2
        assert all(q["duration"] >= 0.5 for q in slow_queries)


@pytest.mark.asyncio
async def test_async_performance_tracking():
    """Test performance tracking in async context."""
    from dgas.dashboard.performance.optimizer import performance_timer

    monitor = PerformanceMonitor()

    @performance_timer(monitor)
    async def sample_async_function():
        await asyncio.sleep(0.1)
        return "result"

    result = await sample_async_function()
    assert result == "result"

    # Check that the query was recorded
    assert len(monitor.query_times) >= 1


def test_performance_decorator():
    """Test performance decorator."""
    from dgas.dashboard.performance.optimizer import measure_performance

    monitor = PerformanceMonitor()

    @measure_performance(monitor)
    def sample_function():
        time.sleep(0.05)
        return "done"

    result = sample_function()
    assert result == "done"
    assert len(monitor.query_times) >= 1


def test_cache_manager_with_custom_hasher():
    """Test cache with custom key hasher."""
    cache = CacheManager(max_size=10, default_ttl=300)

    # Use tuple as key
    cache.set(("key", "subkey"), "value")
    value = cache.get(("key", "subkey"))

    assert value == "value"


def test_cache_ttl_zero():
    """Test cache with TTL of zero (never expires)."""
    cache = CacheManager(max_size=10, default_ttl=300)

    cache.set("key", "value", ttl=0)
    entry = cache._cache["key"]

    # TTL 0 means no expiration
    assert entry.ttl == 0
    assert not entry.is_expired()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
