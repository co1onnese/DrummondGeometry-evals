"""Enhanced database persistence with performance optimizations.

This module provides an enhanced version of the persistence layer with:
- Connection pooling
- Query result caching
- Performance monitoring
- Query profiling
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

import psycopg
from psycopg.types.json import Json

from ..settings import Settings
from .connection_pool import get_pool_manager
from .query_cache import get_cache_manager
from .performance_monitor import get_performance_monitor, profile_query

from ..prediction.persistence import PredictionPersistence


class OptimizedPredictionPersistence(PredictionPersistence):
    """
    Enhanced prediction persistence with performance optimizations.

    Features:
    - Connection pooling for reduced connection overhead
    - Query result caching for frequently-accessed data
    - Performance monitoring and profiling
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize enhanced persistence layer.

        Args:
            settings: Application settings (uses default if None)
        """
        super().__init__(settings)
        self.pool_manager = get_pool_manager()
        self.cache_manager = get_cache_manager()
        self.performance_monitor = get_performance_monitor()

    def get_recent_runs(
        self,
        limit: int = 20,
        status: Optional[str] = None,
        use_cache: bool = True,
        cache_ttl_seconds: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get recent prediction runs with caching and monitoring.

        Args:
            limit: Maximum number of runs to return
            status: Optional filter by status
            use_cache: Whether to use query cache
            cache_ttl_seconds: Cache TTL in seconds

        Returns:
            List of run dictionaries
        """
        # Create cache key
        query = "get_recent_runs"
        params = (limit, status)

        # Try cache first
        if use_cache:
            cache = self.cache_manager.get_cache("dashboard")
            if cache is not None:
                cached_result = cache.get(query, params)
                if cached_result is not None:
                    return cached_result

        # Execute query with profiling
        result = self._execute_with_profiling(
            query_name="get_recent_runs",
            query_func=lambda: self._get_recent_runs_impl(limit, status),
        )

        # Cache result
        if use_cache and cache is not None:
            cache.set(query, params, result, cache_ttl_seconds)

        return result

    def _get_recent_runs_impl(
        self,
        limit: int,
        status: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        Implementation of get_recent_runs query.

        Args:
            limit: Maximum number of runs
            status: Optional status filter

        Returns:
            List of run dictionaries
        """
        from ..db.connection_pool import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                query_builder = [
                    "SELECT",
                    "    run_id, run_timestamp, interval_type, symbols_requested,",
                    "    symbols_processed, signals_generated, execution_time_ms,",
                    "    status, data_fetch_ms, indicator_calc_ms,",
                    "    signal_generation_ms, notification_ms, errors",
                    "FROM prediction_runs"
                ]
                params: List = []

                if status is not None:
                    query_builder.append("WHERE status = %s")
                    params.append(status)

                query_builder.append("ORDER BY run_timestamp DESC LIMIT %s")
                params.append(limit)

                sql = "\n".join(query_builder)
                cur.execute(sql, params)

                runs = []
                for row in cur.fetchall():
                    (
                        run_id, timestamp, interval_type, requested, processed,
                        signals, exec_time, status, data_ms, calc_ms,
                        signal_ms, notif_ms, errors
                    ) = row

                    runs.append({
                        "run_id": run_id,
                        "run_timestamp": timestamp,
                        "interval_type": interval_type,
                        "symbols_requested": requested,
                        "symbols_processed": processed,
                        "signals_generated": signals,
                        "execution_time_ms": exec_time,
                        "status": status,
                        "data_fetch_ms": data_ms,
                        "indicator_calc_ms": calc_ms,
                        "signal_generation_ms": signal_ms,
                        "notification_ms": notif_ms,
                        "errors": errors,
                    })

                return runs

    @profile_query(get_performance_monitor(), "get_recent_signals")
    def get_recent_signals(
        self,
        symbol: Optional[str] = None,
        lookback_hours: int = 24,
        min_confidence: Optional[float] = None,
        limit: int = 100,
        use_cache: bool = True,
        cache_ttl_seconds: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Get recent generated signals with caching and monitoring.

        Args:
            symbol: Optional filter by symbol
            lookback_hours: Hours to look back from now
            min_confidence: Optional minimum confidence filter
            limit: Maximum number of signals to return
            use_cache: Whether to use query cache
            cache_ttl_seconds: Cache TTL in seconds

        Returns:
            List of signal dictionaries
        """
        # Create cache key
        query = "get_recent_signals"
        params = (symbol, lookback_hours, min_confidence, limit)

        # Try cache first
        if use_cache:
            cache = self.cache_manager.get_cache("signals")
            if cache is not None:
                cached_result = cache.get(query, params)
                if cached_result is not None:
                    return cached_result

        # Execute query
        result = self._get_recent_signals_impl(
            symbol, lookback_hours, min_confidence, limit
        )

        # Cache result
        if use_cache and cache is not None:
            cache.set(query, params, result, cache_ttl_seconds)

        return result

    def _get_recent_signals_impl(
        self,
        symbol: Optional[str],
        lookback_hours: int,
        min_confidence: Optional[float],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        Implementation of get_recent_signals query.

        Args:
            symbol: Optional symbol filter
            lookback_hours: Hours to look back
            min_confidence: Optional minimum confidence
            limit: Maximum number of results

        Returns:
            List of signal dictionaries
        """
        from ..db.connection_pool import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT
                        gs.signal_id, gs.run_id, ms.symbol, gs.signal_timestamp,
                        gs.signal_type, gs.entry_price, gs.stop_loss, gs.target_price,
                        gs.confidence, gs.signal_strength, gs.timeframe_alignment,
                        gs.risk_reward_ratio, gs.htf_trend, gs.trading_tf_state,
                        gs.confluence_zones_count, gs.pattern_context,
                        gs.notification_sent, gs.notification_channels,
                        gs.notification_timestamp, gs.outcome, gs.pnl_pct
                    FROM generated_signals gs
                    JOIN market_symbols ms ON gs.symbol_id = ms.symbol_id
                    WHERE gs.signal_timestamp >= NOW() - INTERVAL '%s hours'
                """
                params: List = [lookback_hours]

                if symbol is not None:
                    query += " AND ms.symbol = %s"
                    params.append(symbol)

                if min_confidence is not None:
                    query += " AND gs.confidence >= %s"
                    params.append(min_confidence)

                query += " ORDER BY gs.signal_timestamp DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)

                signals = []
                for row in cur.fetchall():
                    (
                        signal_id, run_id, symbol, timestamp, signal_type,
                        entry, stop, target, confidence, strength, alignment,
                        rr_ratio, htf_trend, tf_state, zones_count, pattern_ctx,
                        notif_sent, notif_channels, notif_ts, outcome, pnl
                    ) = row

                    signals.append({
                        "signal_id": signal_id,
                        "run_id": run_id,
                        "symbol": symbol,
                        "signal_timestamp": timestamp,
                        "signal_type": signal_type,
                        "entry_price": Decimal(str(entry)),
                        "stop_loss": Decimal(str(stop)),
                        "target_price": Decimal(str(target)),
                        "confidence": float(confidence),
                        "signal_strength": float(strength),
                        "timeframe_alignment": float(alignment),
                        "risk_reward_ratio": float(rr_ratio) if rr_ratio else None,
                        "htf_trend": htf_trend,
                        "trading_tf_state": tf_state,
                        "confluence_zones_count": zones_count,
                        "pattern_context": pattern_ctx,
                        "notification_sent": notif_sent,
                        "notification_channels": notif_channels,
                        "notification_timestamp": notif_ts,
                        "outcome": outcome,
                        "pnl_pct": float(pnl) if pnl else None,
                    })

                return signals

    def get_metrics(
        self,
        metric_type: Optional[str] = None,
        lookback_hours: int = 24,
        aggregation_period: Optional[str] = None,
        limit: int = 1000,
        use_cache: bool = True,
        cache_ttl_seconds: int = 300,
    ) -> List[Dict[str, Any]]:
        """
        Get metrics with caching and monitoring.

        Args:
            metric_type: Optional filter by metric type
            lookback_hours: Hours to look back
            aggregation_period: Optional filter by aggregation period
            limit: Maximum number of metrics to return
            use_cache: Whether to use query cache
            cache_ttl_seconds: Cache TTL in seconds

        Returns:
            List of metric dictionaries
        """
        # Create cache key
        query = "get_metrics"
        params = (metric_type, lookback_hours, aggregation_period, limit)

        # Try cache first
        if use_cache:
            cache = self.cache_manager.get_cache("metrics")
            if cache is not None:
                cached_result = cache.get(query, params)
                if cached_result is not None:
                    return cached_result

        # Execute query
        result = self._get_metrics_impl(
            metric_type, lookback_hours, aggregation_period, limit
        )

        # Cache result
        if use_cache and cache is not None:
            cache.set(query, params, result, cache_ttl_seconds)

        return result

    def _get_metrics_impl(
        self,
        metric_type: Optional[str],
        lookback_hours: int,
        aggregation_period: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        Implementation of get_metrics query.

        Args:
            metric_type: Optional metric type filter
            lookback_hours: Hours to look back
            aggregation_period: Optional aggregation period
            limit: Maximum number of results

        Returns:
            List of metric dictionaries
        """
        from ..db.connection_pool import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT
                        metric_id, metric_timestamp, metric_type,
                        metric_value, aggregation_period, metadata
                    FROM prediction_metrics
                    WHERE metric_timestamp >= NOW() - INTERVAL '%s hours'
                """
                params: List = [lookback_hours]

                if metric_type is not None:
                    query += " AND metric_type = %s"
                    params.append(metric_type)

                if aggregation_period is not None:
                    query += " AND aggregation_period = %s"
                    params.append(aggregation_period)

                query += " ORDER BY metric_timestamp DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)

                metrics = []
                for row in cur.fetchall():
                    (metric_id, timestamp, mtype, value, agg_period, metadata) = row

                    metrics.append({
                        "metric_id": metric_id,
                        "metric_timestamp": timestamp,
                        "metric_type": mtype,
                        "metric_value": float(value),
                        "aggregation_period": agg_period,
                        "metadata": metadata,
                    })

                return metrics

    def _execute_with_profiling(
        self,
        query_name: str,
        query_func: callable,
    ) -> Any:
        """
        Execute a query function with performance profiling.

        Args:
            query_name: Name for the query
            query_func: Function to execute

        Returns:
            Query result
        """
        start_time = time.time()
        success = False
        error_msg = None
        row_count = 0

        try:
            result = query_func()
            success = True

            # Try to count rows
            if isinstance(result, (list, tuple)):
                row_count = len(result)

            return result

        except Exception as e:
            error_msg = str(e)
            raise

        finally:
            execution_time_ms = (time.time() - start_time) * 1000
            self.performance_monitor.record_query(
                query=query_name,
                execution_time_ms=execution_time_ms,
                row_count=row_count,
                success=success,
                error_message=error_msg,
            )


# Export as the default persistence class
__all__ = [
    "OptimizedPredictionPersistence",
]
