"""Performance optimization package.

Provides caching, lazy loading, and performance monitoring.
"""

from dgas.dashboard.performance.optimizer import (
    PerformanceMonitor,
    CacheManager,
    LazyLoader,
    get_monitor,
    get_cache,
    get_lazy_loader,
    performance_timer,
    cached_query,
    measure_performance,
    render_performance_panel,
)

__all__ = [
    "PerformanceMonitor",
    "CacheManager",
    "LazyLoader",
    "get_monitor",
    "get_cache",
    "get_lazy_loader",
    "performance_timer",
    "cached_query",
    "measure_performance",
    "render_performance_panel",
]
