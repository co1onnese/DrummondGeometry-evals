"""Database query optimization utilities.

This module provides tools for optimizing database performance including
index creation, query analysis, and performance tuning.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import psycopg

from .connection_pool import get_pool_manager
from .performance_monitor import get_performance_monitor

logger = logging.getLogger(__name__)


class DatabaseOptimizer:
    """
    Database query optimization manager.

    Provides methods to add missing indexes, analyze slow queries,
    and optimize database performance.
    """

    def __init__(self):
        """Initialize database optimizer."""
        self.pool_manager = get_pool_manager()
        self.performance_monitor = get_performance_monitor()

    def add_missing_indexes(self) -> Dict[str, Any]:
        """
        Add missing indexes for optimal query performance.

        Based on common query patterns in the application, adds indexes
        that are not present in the base schema.

        Returns:
            Dictionary with results of index creation attempts
        """
        results = {
            "attempted": 0,
            "created": 0,
            "skipped": 0,
            "errors": 0,
            "indexes": [],
        }

        # List of indexes to create
        indexes_to_create = [
            {
                "name": "idx_market_symbols_symbol_active",
                "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_symbols_symbol_active
                ON market_symbols(symbol, is_active)
                WHERE is_active = true;
                """,
                "description": "Optimize lookups of active symbols by symbol name"
            },
            {
                "name": "idx_market_data_interval_timestamp",
                "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_data_interval_timestamp
                ON market_data(interval_type, timestamp DESC, symbol_id);
                """,
                "description": "Optimize queries filtering by interval and timestamp"
            },
            {
                "name": "idx_generated_signals_notification_status",
                "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_generated_signals_notification_status
                ON generated_signals(notification_sent, signal_timestamp DESC)
                WHERE notification_sent = false;
                """,
                "description": "Optimize queries for unsent notifications"
            },
            {
                "name": "idx_prediction_runs_interval_status",
                "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prediction_runs_interval_status
                ON prediction_runs(interval_type, status, run_timestamp DESC);
                """,
                "description": "Optimize queries filtering by interval and status"
            },
            {
                "name": "idx_pldot_calculations_period",
                "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pldot_calculations_period
                ON pldot_calculations(calculation_period, symbol_id, timestamp DESC);
                """,
                "description": "Optimize PLdot queries by period and symbol"
            },
            {
                "name": "idx_market_state_trend",
                "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_state_trend
                ON market_state(symbol_id, trend_state, timestamp DESC);
                """,
                "description": "Optimize market state queries by symbol and trend"
            },
        ]

        with self.pool_manager.get_connection() as conn:
            with conn.cursor() as cur:
                for index_info in indexes_to_create:
                    results["attempted"] += 1
                    index_name = index_info["name"]
                    sql = index_info["sql"]
                    description = index_info["description"]

                    try:
                        # Check if index already exists
                        cur.execute(
                            """
                            SELECT 1 FROM pg_indexes
                            WHERE indexname = %s
                            """,
                            (index_name,)
                        )

                        if cur.fetchone():
                            results["skipped"] += 1
                            results["indexes"].append({
                                "name": index_name,
                                "status": "skipped",
                                "reason": "already exists",
                                "description": description,
                            })
                            logger.info(f"Index {index_name} already exists, skipping")
                            continue

                        # Create the index
                        cur.execute(sql)
                        conn.commit()

                        results["created"] += 1
                        results["indexes"].append({
                            "name": index_name,
                            "status": "created",
                            "description": description,
                        })
                        logger.info(f"Created index: {index_name} - {description}")

                    except Exception as e:
                        conn.rollback()
                        results["errors"] += 1
                        results["indexes"].append({
                            "name": index_name,
                            "status": "error",
                            "error": str(e),
                            "description": description,
                        })
                        logger.error(f"Failed to create index {index_name}: {e}")

        return results

    def analyze_slow_queries(self) -> Dict[str, Any]:
        """
        Analyze slow queries from performance monitor.

        Returns:
            Dictionary with slow query analysis
        """
        report = self.performance_monitor.get_performance_report()

        analysis = {
            "summary": {
                "total_queries": report.total_queries,
                "slow_queries_count": report.slow_queries_count,
                "slow_query_percentage": (
                    (report.slow_queries_count / report.total_queries * 100)
                    if report.total_queries > 0 else 0
                ),
                "avg_execution_time_ms": report.avg_execution_time_ms,
                "p95_execution_time_ms": report.p95_execution_time_ms,
                "p99_execution_time_ms": report.p99_execution_time_ms,
            },
            "slow_queries": [
                {
                    "query": sq.query,
                    "execution_time_ms": sq.execution_time_ms,
                    "frequency": sq.frequency,
                    "query_preview": sq.query_preview,
                }
                for sq in report.top_slow_queries
            ],
            "recommendations": self._generate_recommendations(report),
        }

        return analysis

    def _generate_recommendations(self, report) -> List[str]:
        """
        Generate optimization recommendations based on performance data.

        Args:
            report: QueryPerformanceReport instance

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Check for high average execution time
        if report.avg_execution_time_ms > 200:
            recommendations.append(
                f"Average query time is {report.avg_execution_time_ms:.1f}ms. "
                "Consider adding more specific indexes or reviewing query patterns."
            )

        # Check for high P95
        if report.p95_execution_time_ms > 500:
            recommendations.append(
                f"P95 query time is {report.p95_execution_time_ms:.1f}ms. "
                "Some queries are consistently slow. Review and optimize."
            )

        # Check for slow query count
        if report.slow_queries_count > 0 and report.total_queries > 0:
            slow_pct = (report.slow_queries_count / report.total_queries * 100)
            if slow_pct > 10:
                recommendations.append(
                    f"{slow_pct:.1f}% of queries are slow. "
                    "Focus on optimizing the top slow queries listed below."
                )

        # Check for high-frequency slow queries
        for sq in report.top_slow_queries[:5]:
            if sq.frequency > 10:
                recommendations.append(
                    f"Query '{sq.query_preview[:50]}...' runs frequently "
                    f"({sq.frequency} times) and is slow ({sq.execution_time_ms:.1f}ms). "
                    "Optimize this query first."
                )

        return recommendations

    def get_index_stats(self) -> Dict[str, Any]:
        """
        Get statistics about database indexes.

        Returns:
            Dictionary with index statistics
        """
        stats = {
            "total_indexes": 0,
            "indexes": [],
            "unused_indexes": [],
        }

        with self.pool_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Get all indexes with usage statistics
                cur.execute(
                    """
                    SELECT
                        schemaname,
                        tablename,
                        indexname,
                        idx_scan as index_scans,
                        idx_tup_read as tuples_read,
                        idx_tup_fetch as tuples_fetched,
                        pg_size_pretty(pg_relation_size(indexrelid)) as index_size
                    FROM pg_stat_user_indexes
                    ORDER BY idx_scan DESC;
                    """
                )

                for row in cur.fetchall():
                    (
                        schema,
                        table,
                        index_name,
                        scans,
                        read,
                        fetched,
                        size,
                    ) = row

                    stats["indexes"].append({
                        "schema": schema,
                        "table": table,
                        "name": index_name,
                        "scans": scans,
                        "size": size,
                    })

                stats["total_indexes"] = len(stats["indexes"])

                # Find unused indexes (never scanned)
                unused = [idx for idx in stats["indexes"] if idx["scans"] == 0]
                stats["unused_indexes"] = unused

        return stats

    def vacuum_analyze_tables(self, tables: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run VACUUM ANALYZE on specified tables to update statistics.

        Args:
            tables: List of table names to vacuum. If None, vacuuums main tables.

        Returns:
            Dictionary with results
        """
        if tables is None:
            tables = [
                "market_data",
                "generated_signals",
                "prediction_runs",
                "prediction_metrics",
                "pldot_calculations",
                "envelope_bands",
                "market_state",
            ]

        results = {
            "attempted": 0,
            "successful": 0,
            "errors": 0,
            "tables": [],
        }

        with self.pool_manager.get_connection() as conn:
            with conn.cursor() as cur:
                for table in tables:
                    results["attempted"] += 1

                    try:
                        # Use VACUUM ANALYSE to update statistics
                        cur.execute(f"VACUUM ANALYZE {table}")
                        conn.commit()

                        results["successful"] += 1
                        results["tables"].append({
                            "name": table,
                            "status": "success",
                        })
                        logger.info(f"VACUUM ANALYZE completed for {table}")

                    except Exception as e:
                        conn.rollback()
                        results["errors"] += 1
                        results["tables"].append({
                            "name": table,
                            "status": "error",
                            "error": str(e),
                        })
                        logger.error(f"VACUUM ANALYZE failed for {table}: {e}")

        return results

    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get general database performance statistics.

        Returns:
            Dictionary with database statistics
        """
        stats = {
            "database_size": "",
            "table_sizes": [],
            "connection_stats": {},
        }

        with self.pool_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Get database size
                cur.execute(
                    "SELECT pg_size_pretty(pg_database_size(current_database()));"
                )
                stats["database_size"] = cur.fetchone()[0]

                # Get table sizes
                cur.execute(
                    """
                    SELECT
                        schemaname,
                        tablename,
                        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                    FROM pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                    LIMIT 20;
                    """
                )

                for row in cur.fetchall():
                    schema, table, size = row
                    stats["table_sizes"].append({
                        "schema": schema,
                        "table": table,
                        "size": size,
                    })

                # Get connection pool stats
                pool_stats = self.pool_manager.get_stats()
                stats["connection_stats"] = pool_stats

        return stats


# Global optimizer instance
_optimizer: Optional[DatabaseOptimizer] = None


def get_optimizer() -> DatabaseOptimizer:
    """
    Get the global database optimizer instance.

    Returns:
        DatabaseOptimizer instance
    """
    global _optimizer
    if _optimizer is None:
        _optimizer = DatabaseOptimizer()
    return _optimizer


__all__ = [
    "DatabaseOptimizer",
    "get_optimizer",
]
