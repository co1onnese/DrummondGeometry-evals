"""Database persistence for prediction system (signals, runs, metrics)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

try:
    import psycopg2
    from psycopg2.extras import execute_values, Json
    HAS_PSYCOPG2 = True
except ImportError:
    # Fall back to psycopg (psycopg3)
    import psycopg
    HAS_PSYCOPG2 = False

from ..settings import Settings


class PredictionPersistence:
    """Handle database persistence for prediction system."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize persistence layer with database connection."""
        if settings is None:
            from ..settings import get_settings
            settings = get_settings()
        self.settings = settings
        self._conn: Optional[psycopg2.extensions.connection] = None

    def _get_connection(self) -> psycopg2.extensions.connection:
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=self.settings.db_host,
                port=self.settings.db_port,
                dbname=self.settings.db_name,
                user=self.settings.db_user,
                password=self.settings.db_password,
            )
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # ================================================================================
    # Prediction Run Persistence
    # ================================================================================

    def save_prediction_run(
        self,
        interval_type: str,
        symbols_requested: int,
        symbols_processed: int,
        signals_generated: int,
        execution_time_ms: int,
        status: str,
        data_fetch_ms: Optional[int] = None,
        indicator_calc_ms: Optional[int] = None,
        signal_generation_ms: Optional[int] = None,
        notification_ms: Optional[int] = None,
        errors: Optional[List[str]] = None,
        run_timestamp: Optional[datetime] = None,
    ) -> int:
        """
        Save prediction run metadata.

        Args:
            interval_type: Interval for this run (e.g., "30min")
            symbols_requested: Number of symbols requested
            symbols_processed: Number successfully processed
            signals_generated: Number of signals created
            execution_time_ms: Total execution time
            status: Run status (SUCCESS, PARTIAL, FAILED)
            data_fetch_ms: Time for data fetch
            indicator_calc_ms: Time for indicator calculation
            signal_generation_ms: Time for signal generation
            notification_ms: Time for notifications
            errors: List of error messages
            run_timestamp: Timestamp of run (defaults to now)

        Returns:
            run_id of the saved record
        """
        if run_timestamp is None:
            run_timestamp = datetime.now(timezone.utc)

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO prediction_runs (
                    run_timestamp, interval_type, symbols_requested,
                    symbols_processed, signals_generated, execution_time_ms,
                    status, data_fetch_ms, indicator_calc_ms,
                    signal_generation_ms, notification_ms, errors
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING run_id
                """,
                (
                    run_timestamp,
                    interval_type,
                    symbols_requested,
                    symbols_processed,
                    signals_generated,
                    execution_time_ms,
                    status,
                    data_fetch_ms,
                    indicator_calc_ms,
                    signal_generation_ms,
                    notification_ms,
                    errors if errors else [],
                )
            )

            result = cursor.fetchone()
            if result is None:
                raise ValueError("Failed to insert prediction run")
            run_id = result[0]

            conn.commit()
            return run_id

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    def get_recent_runs(
        self,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent prediction runs.

        Args:
            limit: Maximum number of runs to return
            status: Optional filter by status

        Returns:
            List of run dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = """
                SELECT
                    run_id, run_timestamp, interval_type, symbols_requested,
                    symbols_processed, signals_generated, execution_time_ms,
                    status, data_fetch_ms, indicator_calc_ms,
                    signal_generation_ms, notification_ms, errors
                FROM prediction_runs
            """
            params: List = []

            if status is not None:
                query += " WHERE status = %s"
                params.append(status)

            query += " ORDER BY run_timestamp DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)

            runs = []
            for row in cursor.fetchall():
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

        finally:
            cursor.close()

    # ================================================================================
    # Generated Signal Persistence
    # ================================================================================

    def save_generated_signals(
        self,
        run_id: int,
        signals: Sequence[Dict[str, Any]],
    ) -> int:
        """
        Save generated trading signals.

        Args:
            run_id: ID of the prediction run
            signals: Sequence of signal dictionaries with keys:
                - symbol: str
                - signal_timestamp: datetime
                - signal_type: str (LONG, SHORT, EXIT_LONG, EXIT_SHORT)
                - entry_price: Decimal
                - stop_loss: Decimal
                - target_price: Decimal
                - confidence: float
                - signal_strength: float
                - timeframe_alignment: float
                - risk_reward_ratio: Optional[float]
                - htf_trend: Optional[str]
                - trading_tf_state: Optional[str]
                - confluence_zones_count: int
                - pattern_context: Optional[Dict]
                - notification_sent: bool
                - notification_channels: Optional[List[str]]
                - notification_timestamp: Optional[datetime]

        Returns:
            Number of signals inserted
        """
        if not signals:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Prepare values for bulk insert
            values = []
            for signal in signals:
                # Get symbol_id
                cursor.execute(
                    "SELECT symbol_id FROM market_symbols WHERE symbol = %s",
                    (signal["symbol"],)
                )
                result = cursor.fetchone()
                if result is None:
                    raise ValueError(f"Symbol {signal['symbol']} not found in database")
                symbol_id = result[0]

                values.append((
                    run_id,
                    symbol_id,
                    signal["signal_timestamp"],
                    signal["signal_type"],
                    float(signal["entry_price"]),
                    float(signal["stop_loss"]),
                    float(signal["target_price"]),
                    signal["confidence"],
                    signal["signal_strength"],
                    signal["timeframe_alignment"],
                    signal.get("risk_reward_ratio"),
                    signal.get("htf_trend"),
                    signal.get("trading_tf_state"),
                    signal.get("confluence_zones_count", 0),
                    Json(signal.get("pattern_context")) if signal.get("pattern_context") else None,
                    signal.get("notification_sent", False),
                    signal.get("notification_channels"),
                    signal.get("notification_timestamp"),
                ))

            # Bulk insert
            execute_values(
                cursor,
                """
                INSERT INTO generated_signals (
                    run_id, symbol_id, signal_timestamp, signal_type,
                    entry_price, stop_loss, target_price,
                    confidence, signal_strength, timeframe_alignment,
                    risk_reward_ratio, htf_trend, trading_tf_state,
                    confluence_zones_count, pattern_context,
                    notification_sent, notification_channels, notification_timestamp
                ) VALUES %s
                """,
                values
            )

            conn.commit()
            return len(values)

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    def get_recent_signals(
        self,
        symbol: Optional[str] = None,
        lookback_hours: int = 24,
        min_confidence: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get recent generated signals.

        Args:
            symbol: Optional filter by symbol
            lookback_hours: Hours to look back from now
            min_confidence: Optional minimum confidence filter
            limit: Maximum number of signals to return

        Returns:
            List of signal dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
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

            cursor.execute(query, params)

            signals = []
            for row in cursor.fetchall():
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

        finally:
            cursor.close()

    def update_signal_outcome(
        self,
        signal_id: int,
        outcome: str,
        actual_high: Decimal,
        actual_low: Decimal,
        actual_close: Decimal,
        pnl_pct: float,
    ) -> None:
        """
        Update signal with actual outcome data.

        Args:
            signal_id: ID of the signal
            outcome: Outcome (WIN, LOSS, NEUTRAL, PENDING)
            actual_high: Highest price during evaluation window
            actual_low: Lowest price during evaluation window
            actual_close: Closing price at evaluation end
            pnl_pct: Percentage P&L if signal was taken
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE generated_signals
                SET
                    outcome = %s,
                    actual_high = %s,
                    actual_low = %s,
                    actual_close = %s,
                    pnl_pct = %s,
                    evaluated_at = %s
                WHERE signal_id = %s
                """,
                (
                    outcome,
                    float(actual_high),
                    float(actual_low),
                    float(actual_close),
                    pnl_pct,
                    datetime.now(timezone.utc),
                    signal_id,
                )
            )

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    # ================================================================================
    # Metrics Persistence
    # ================================================================================

    def save_metric(
        self,
        metric_type: str,
        metric_value: float,
        aggregation_period: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        metric_timestamp: Optional[datetime] = None,
    ) -> int:
        """
        Save a performance or calibration metric.

        Args:
            metric_type: Type of metric (e.g., "latency_p95", "win_rate")
            metric_value: Numeric value of the metric
            aggregation_period: Optional aggregation period
            metadata: Optional metadata dictionary
            metric_timestamp: Timestamp (defaults to now)

        Returns:
            metric_id of the saved record
        """
        if metric_timestamp is None:
            metric_timestamp = datetime.now(timezone.utc)

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO prediction_metrics (
                    metric_timestamp, metric_type, metric_value,
                    aggregation_period, metadata
                ) VALUES (
                    %s, %s, %s, %s, %s
                )
                RETURNING metric_id
                """,
                (
                    metric_timestamp,
                    metric_type,
                    metric_value,
                    aggregation_period,
                    Json(metadata) if metadata else None,
                )
            )

            result = cursor.fetchone()
            if result is None:
                raise ValueError("Failed to insert metric")
            metric_id = result[0]

            conn.commit()
            return metric_id

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    def get_metrics(
        self,
        metric_type: Optional[str] = None,
        lookback_hours: int = 24,
        aggregation_period: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get metrics for analysis.

        Args:
            metric_type: Optional filter by metric type
            lookback_hours: Hours to look back
            aggregation_period: Optional filter by aggregation period
            limit: Maximum number of metrics to return

        Returns:
            List of metric dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
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

            cursor.execute(query, params)

            metrics = []
            for row in cursor.fetchall():
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

        finally:
            cursor.close()

    # ================================================================================
    # Scheduler State Management
    # ================================================================================

    def update_scheduler_state(
        self,
        status: str,
        last_run_timestamp: Optional[datetime] = None,
        next_scheduled_run: Optional[datetime] = None,
        current_run_id: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Update scheduler state (singleton record).

        Args:
            status: Scheduler status (IDLE, RUNNING, STOPPED, ERROR)
            last_run_timestamp: Optional last run timestamp
            next_scheduled_run: Optional next scheduled run time
            current_run_id: Optional current run ID
            error_message: Optional error message
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE scheduler_state
                SET
                    status = %s,
                    last_run_timestamp = COALESCE(%s, last_run_timestamp),
                    next_scheduled_run = %s,
                    current_run_id = %s,
                    error_message = %s,
                    updated_at = %s
                WHERE state_id = 1
                """,
                (
                    status,
                    last_run_timestamp,
                    next_scheduled_run,
                    current_run_id,
                    error_message,
                    datetime.now(timezone.utc),
                )
            )

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    def get_scheduler_state(self) -> Dict[str, Any]:
        """
        Get current scheduler state.

        Returns:
            Dictionary with scheduler state
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT
                    last_run_timestamp, next_scheduled_run, status,
                    current_run_id, error_message, updated_at
                FROM scheduler_state
                WHERE state_id = 1
                """
            )

            row = cursor.fetchone()
            if row is None:
                return {
                    "status": "IDLE",
                    "last_run_timestamp": None,
                    "next_scheduled_run": None,
                    "current_run_id": None,
                    "error_message": None,
                    "updated_at": None,
                }

            (last_run, next_run, status, current_run, error, updated) = row

            return {
                "last_run_timestamp": last_run,
                "next_scheduled_run": next_run,
                "status": status,
                "current_run_id": current_run,
                "error_message": error,
                "updated_at": updated,
            }

        finally:
            cursor.close()


__all__ = ["PredictionPersistence"]
