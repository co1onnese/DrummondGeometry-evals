"""Query performance monitoring and profiling.

This module provides utilities to monitor and profile database query performance,
helping identify slow queries and optimization opportunities.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class QueryMetrics:
    """Metrics for a single database query."""
    query: str
    execution_time_ms: float
    row_count: int
    timestamp: float
    success: bool
    error_message: Optional[str] = None


@dataclass
class SlowQuery:
    """Represents a slow query that exceeds threshold."""
    query: str
    execution_time_ms: float
    timestamp: float
    query_preview: str
    frequency: int = 1


@dataclass
class QueryPerformanceReport:
    """Summary report of query performance statistics."""
    total_queries: int
    slow_queries_count: int
    avg_execution_time_ms: float
    p95_execution_time_ms: float
    p99_execution_time_ms: float
    total_execution_time_ms: float
    slow_query_threshold_ms: float
    top_slow_queries: List[SlowQuery] = field(default_factory=list)
    query_frequency: Dict[str, int] = field(default_factory=dict)


class QueryPerformanceMonitor:
    """
    Monitor and profile database query performance.

    Tracks query execution times, identifies slow queries, and generates
    performance reports for optimization efforts.
    """

    def __init__(
        self,
        slow_query_threshold_ms: float = 500.0,
        max_history: int = 10000,
    ):
        """
        Initialize performance monitor.

        Args:
            slow_query_threshold_ms: Threshold in ms for considering a query 'slow'
            max_history: Maximum number of query metrics to keep in history
        """
        self.slow_query_threshold_ms = slow_query_threshold_ms
        self.max_history = max_history
        self._query_history: deque[QueryMetrics] = deque(maxlen=max_history)
        self._query_counts: defaultdict[str, int] = defaultdict(int)
        self._slow_queries: list[SlowQuery] = []
        self._enabled = True

    def record_query(
        self,
        query: str,
        execution_time_ms: float,
        row_count: int,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Record metrics for a database query.

        Args:
            query: SQL query string (or identifier)
            execution_time_ms: Query execution time in milliseconds
            row_count: Number of rows affected/returned
            success: Whether the query succeeded
            error_message: Error message if query failed
        """
        if not self._enabled:
            return

        metrics = QueryMetrics(
            query=query,
            execution_time_ms=execution_time_ms,
            row_count=row_count,
            timestamp=time.time(),
            success=success,
            error_message=error_message,
        )

        self._query_history.append(metrics)
        self._query_counts[query] += 1

        # Track slow queries
        if execution_time_ms >= self.slow_query_threshold_ms:
            self._track_slow_query(query, execution_time_ms)

    def _track_slow_query(
        self,
        query: str,
        execution_time_ms: float,
    ) -> None:
        """
        Track a slow query for reporting.

        Args:
            query: SQL query string
            execution_time_ms: Execution time in milliseconds
        """
        # Create a preview of the query (first 100 chars)
        query_preview = query[:100] + "..." if len(query) > 100 else query

        # Check if we've seen this query before
        for slow_query in self._slow_queries:
            if slow_query.query_preview == query_preview:
                slow_query.frequency += 1
                # Update execution time if this one is slower
                if execution_time_ms > slow_query.execution_time_ms:
                    slow_query.execution_time_ms = execution_time_ms
                return

        # New slow query
        self._slow_queries.append(
            SlowQuery(
                query=query,
                execution_time_ms=execution_time_ms,
                timestamp=time.time(),
                query_preview=query_preview,
            )
        )

        # Keep only top 50 slow queries
        if len(self._slow_queries) > 50:
            self._slow_queries.sort(
                key=lambda q: (q.frequency, q.execution_time_ms),
                reverse=True,
            )
            self._slow_queries = self._slow_queries[:50]

    def get_performance_report(
        self,
        lookback_seconds: Optional[int] = None,
    ) -> QueryPerformanceReport:
        """
        Generate a performance report for recent queries.

        Args:
            lookback_seconds: Only consider queries from this many seconds ago.
                             If None, considers all history.

        Returns:
            QueryPerformanceReport with summary statistics
        """
        if not self._query_history:
            return QueryPerformanceReport(
                total_queries=0,
                slow_queries_count=0,
                avg_execution_time_ms=0.0,
                p95_execution_time_ms=0.0,
                p99_execution_time_ms=0.0,
                total_execution_time_ms=0.0,
                slow_query_threshold_ms=self.slow_query_threshold_ms,
            )

        # Filter by lookback time if specified
        if lookback_seconds is not None:
            cutoff_time = time.time() - lookback_seconds
            history = [
                m for m in self._query_history
                if m.timestamp >= cutoff_time and m.success
            ]
        else:
            history = [m for m in self._query_history if m.success]

        if not history:
            return QueryPerformanceReport(
                total_queries=0,
                slow_queries_count=0,
                avg_execution_time_ms=0.0,
                p95_execution_time_ms=0.0,
                p99_execution_time_ms=0.0,
                total_execution_time_ms=0.0,
                slow_query_threshold_ms=self.slow_query_threshold_ms,
            )

        # Calculate statistics
        total_queries = len(history)
        total_time = sum(m.execution_time_ms for m in history)
        avg_time = total_time / total_queries if total_queries > 0 else 0.0

        # Calculate percentiles
        execution_times = sorted(m.execution_time_ms for m in history)
        p95_idx = int(0.95 * (len(execution_times) - 1))
        p99_idx = int(0.99 * (len(execution_times) - 1))
        p95_time = execution_times[p95_idx] if p95_idx < len(execution_times) else 0.0
        p99_time = execution_times[p99_idx] if p99_idx < len(execution_times) else 0.0

        # Count slow queries
        slow_count = sum(
            1 for m in history if m.execution_time_ms >= self.slow_query_threshold_ms
        )

        # Get top slow queries
        top_slow = sorted(
            self._slow_queries,
            key=lambda q: (q.frequency, q.execution_time_ms),
            reverse=True,
        )[:10]

        return QueryPerformanceReport(
            total_queries=total_queries,
            slow_queries_count=slow_count,
            avg_execution_time_ms=avg_time,
            p95_execution_time_ms=p95_time,
            p99_execution_time_ms=p99_time,
            total_execution_time_ms=total_time,
            slow_query_threshold_ms=self.slow_query_threshold_ms,
            top_slow_queries=top_slow,
            query_frequency=dict(self._query_counts),
        )

    def get_recent_slow_queries(
        self,
        limit: int = 20,
    ) -> List[SlowQuery]:
        """
        Get recent slow queries.

        Args:
            limit: Maximum number of queries to return

        Returns:
            List of SlowQuery objects
        """
        sorted_queries = sorted(
            self._slow_queries,
            key=lambda q: (q.frequency, q.execution_time_ms),
            reverse=True,
        )
        return sorted_queries[:limit]

    def clear_history(self) -> None:
        """Clear all query history and statistics."""
        self._query_history.clear()
        self._query_counts.clear()
        self._slow_queries.clear()

    def enable(self) -> None:
        """Enable performance monitoring."""
        self._enabled = True

    def disable(self) -> None:
        """Disable performance monitoring."""
        self._enabled = False

    def get_query_stats(self, query: str) -> Dict[str, Any]:
        """
        Get statistics for a specific query.

        Args:
            query: SQL query string

        Returns:
            Dictionary with query statistics
        """
        matching_metrics = [m for m in self._query_history if m.query == query]

        if not matching_metrics:
            return {
                "query": query,
                "count": 0,
                "avg_time_ms": 0.0,
                "min_time_ms": 0.0,
                "max_time_ms": 0.0,
                "success_rate": 0.0,
            }

        execution_times = [m.execution_time_ms for m in matching_metrics]
        successes = [m for m in matching_metrics if m.success]
        total = len(matching_metrics)
        success_count = len(successes)

        return {
            "query": query,
            "count": total,
            "avg_time_ms": sum(execution_times) / len(execution_times),
            "min_time_ms": min(execution_times),
            "max_time_ms": max(execution_times),
            "success_rate": (success_count / total * 100) if total > 0 else 0.0,
        }


def profile_query(
    monitor: QueryPerformanceMonitor,
    query_name: str,
) -> Callable:
    """
    Decorator to profile database query execution time.

    Usage:
        monitor = QueryPerformanceMonitor()

        @profile_query(monitor, "get_recent_signals")
        def get_recent_signals(conn, ...):
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()

    Args:
        monitor: QueryPerformanceMonitor instance
        query_name: Identifier for the query

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            error_msg = None
            row_count = 0

            try:
                result = func(*args, **kwargs)

                # Try to get row count
                if hasattr(result, "__len__"):
                    row_count = len(result)
                elif isinstance(result, (list, tuple)):
                    row_count = len(result)

                success = True
                return result

            except Exception as e:
                error_msg = str(e)
                raise

            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                monitor.record_query(
                    query=query_name,
                    execution_time_ms=execution_time_ms,
                    row_count=row_count,
                    success=success,
                    error_message=error_msg,
                )

        return wrapper
    return decorator


# Global performance monitor instance
_performance_monitor: Optional[QueryPerformanceMonitor] = None


def get_performance_monitor() -> QueryPerformanceMonitor:
    """
    Get the global performance monitor instance.

    Returns:
        QueryPerformanceMonitor instance
    """
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = QueryPerformanceMonitor()
    return _performance_monitor


__all__ = [
    "QueryMetrics",
    "SlowQuery",
    "QueryPerformanceReport",
    "QueryPerformanceMonitor",
    "profile_query",
    "get_performance_monitor",
]
