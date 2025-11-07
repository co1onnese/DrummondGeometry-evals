"""
Performance tracking for prediction system.

This module provides real-time monitoring of prediction cycle performance,
including latency tracking, throughput measurement, and SLA compliance validation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..persistence import PredictionPersistence


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LatencyMetrics:
    """
    Latency measurements for prediction cycle stages.

    All times are in milliseconds for consistency with database schema.
    """
    data_fetch_ms: int
    indicator_calc_ms: int
    signal_generation_ms: int
    notification_ms: int
    total_ms: int

    @property
    def total_calculated(self) -> int:
        """Calculate total from components (for validation)."""
        return (
            self.data_fetch_ms
            + self.indicator_calc_ms
            + self.signal_generation_ms
            + self.notification_ms
        )

    def __post_init__(self):
        """Validate latency metrics."""
        if any(
            x < 0
            for x in [
                self.data_fetch_ms,
                self.indicator_calc_ms,
                self.signal_generation_ms,
                self.notification_ms,
                self.total_ms,
            ]
        ):
            raise ValueError("All latency values must be non-negative")


@dataclass(frozen=True)
class ThroughputMetrics:
    """Throughput measurements for prediction cycle."""
    symbols_processed: int
    signals_generated: int
    execution_time_ms: int
    symbols_per_second: float

    @classmethod
    def calculate(
        cls,
        symbols_processed: int,
        signals_generated: int,
        execution_time_ms: int,
    ) -> ThroughputMetrics:
        """
        Calculate throughput metrics from raw counts.

        Args:
            symbols_processed: Number of symbols successfully processed
            signals_generated: Number of signals generated
            execution_time_ms: Total execution time in milliseconds

        Returns:
            ThroughputMetrics instance with calculated symbols_per_second
        """
        sps = (
            symbols_processed / (execution_time_ms / 1000.0)
            if execution_time_ms > 0
            else 0.0
        )
        return cls(
            symbols_processed=symbols_processed,
            signals_generated=signals_generated,
            execution_time_ms=execution_time_ms,
            symbols_per_second=sps,
        )

    def __post_init__(self):
        """Validate throughput metrics."""
        if self.symbols_processed < 0:
            raise ValueError("symbols_processed must be non-negative")
        if self.signals_generated < 0:
            raise ValueError("signals_generated must be non-negative")
        if self.execution_time_ms < 0:
            raise ValueError("execution_time_ms must be non-negative")


@dataclass(frozen=True)
class PerformanceSummary:
    """Summary statistics for performance tracking."""
    lookback_hours: int
    total_cycles: int
    successful_cycles: int

    # Latency statistics (milliseconds)
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float

    # Throughput statistics
    avg_throughput: float  # symbols/second
    total_symbols_processed: int
    total_signals_generated: int

    # Reliability
    error_rate: float  # Percentage of cycles with errors
    uptime_pct: float  # Percentage of successful cycles

    # SLA compliance
    sla_compliant: bool
    sla_violations: Dict[str, Any]  # Details of any SLA violations


class PerformanceTracker:
    """
    Tracks and reports system performance metrics.

    Monitors prediction cycle performance, calculates aggregated statistics,
    and validates SLA compliance according to defined thresholds.
    """

    # SLA Thresholds
    SLA_P95_LATENCY_MS = 60_000  # 60 seconds
    SLA_ERROR_RATE_PCT = 1.0  # 1%
    SLA_UPTIME_PCT = 99.0  # 99%

    def __init__(self, persistence: PredictionPersistence):
        """
        Initialize with database persistence.

        Args:
            persistence: PredictionPersistence instance for database access
        """
        self.persistence = persistence
        self.logger = logging.getLogger(__name__)

    def track_cycle(
        self,
        run_id: int,
        latency: LatencyMetrics,
        throughput: ThroughputMetrics,
        errors: List[str],
    ) -> None:
        """
        Record metrics for a prediction cycle.

        This method is called by PredictionScheduler after each cycle completes.
        Metrics are persisted to prediction_metrics table for time-series analysis.

        Args:
            run_id: ID of the prediction run
            latency: Latency breakdown for the cycle
            throughput: Throughput metrics for the cycle
            errors: List of error messages (if any)
        """
        try:
            # Persist latency metrics
            self.persistence.save_metric(
                metric_type="latency_total",
                metric_value=latency.total_ms,
                metadata={"run_id": run_id},
            )

            self.persistence.save_metric(
                metric_type="latency_data_fetch",
                metric_value=latency.data_fetch_ms,
                metadata={"run_id": run_id},
            )

            self.persistence.save_metric(
                metric_type="latency_indicator_calc",
                metric_value=latency.indicator_calc_ms,
                metadata={"run_id": run_id},
            )

            self.persistence.save_metric(
                metric_type="latency_signal_generation",
                metric_value=latency.signal_generation_ms,
                metadata={"run_id": run_id},
            )

            self.persistence.save_metric(
                metric_type="latency_notification",
                metric_value=latency.notification_ms,
                metadata={"run_id": run_id},
            )

            # Persist throughput metrics
            self.persistence.save_metric(
                metric_type="throughput_symbols_per_second",
                metric_value=throughput.symbols_per_second,
                metadata={"run_id": run_id},
            )

            self.persistence.save_metric(
                metric_type="throughput_symbols_processed",
                metric_value=throughput.symbols_processed,
                metadata={"run_id": run_id},
            )

            self.persistence.save_metric(
                metric_type="throughput_signals_generated",
                metric_value=throughput.signals_generated,
                metadata={"run_id": run_id},
            )

            # Track error count
            error_count = len(errors)
            self.persistence.save_metric(
                metric_type="error_count",
                metric_value=error_count,
                metadata={"run_id": run_id, "error_sample": errors[:5]},  # Sample errors
            )

            self.logger.debug(
                f"Tracked metrics for run {run_id}: "
                f"{latency.total_ms}ms, {throughput.symbols_per_second:.2f} sym/s"
            )

        except Exception as e:
            self.logger.error(f"Failed to track metrics for run {run_id}: {e}")
            # Don't raise - metrics tracking should not break the prediction cycle

    def get_performance_summary(
        self,
        lookback_hours: int = 24,
    ) -> PerformanceSummary:
        """
        Get performance summary statistics for the lookback period.

        Calculates aggregated metrics from prediction_runs table.

        Args:
            lookback_hours: Number of hours to look back from now

        Returns:
            PerformanceSummary with aggregated statistics
        """
        # Query recent runs from database
        runs = self.persistence.get_recent_runs(limit=1000)

        # Filter to lookback window
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        recent_runs = [r for r in runs if r["run_timestamp"] >= cutoff]

        if not recent_runs:
            return self._empty_summary(lookback_hours)

        # Calculate statistics
        total_cycles = len(recent_runs)
        successful = [r for r in recent_runs if r["status"] == "SUCCESS"]
        successful_count = len(successful)

        # Latency statistics
        latencies = [
            r["execution_time_ms"] for r in recent_runs if r["execution_time_ms"]
        ]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        p50_latency = self._percentile(latencies, 50)
        p95_latency = self._percentile(latencies, 95)
        p99_latency = self._percentile(latencies, 99)

        # Throughput statistics
        symbols_processed = sum(r["symbols_processed"] for r in recent_runs)
        signals_generated = sum(r["signals_generated"] for r in recent_runs)

        # Calculate average throughput (symbols/second)
        throughput_values = []
        for run in recent_runs:
            if run["execution_time_ms"] > 0:
                sps = run["symbols_processed"] / (run["execution_time_ms"] / 1000.0)
                throughput_values.append(sps)
        avg_throughput = (
            sum(throughput_values) / len(throughput_values) if throughput_values else 0.0
        )

        # Reliability metrics
        cycles_with_errors = len(
            [r for r in recent_runs if r["errors"] and len(r["errors"]) > 0]
        )
        error_rate = (cycles_with_errors / total_cycles * 100) if total_cycles > 0 else 0.0
        uptime_pct = (successful_count / total_cycles * 100) if total_cycles > 0 else 0.0

        # SLA compliance check
        sla_compliant, violations = self._check_sla(
            p95_latency=p95_latency,
            error_rate=error_rate,
            uptime_pct=uptime_pct,
        )

        return PerformanceSummary(
            lookback_hours=lookback_hours,
            total_cycles=total_cycles,
            successful_cycles=successful_count,
            avg_latency_ms=avg_latency,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            avg_throughput=avg_throughput,
            total_symbols_processed=symbols_processed,
            total_signals_generated=signals_generated,
            error_rate=error_rate,
            uptime_pct=uptime_pct,
            sla_compliant=sla_compliant,
            sla_violations=violations,
        )

    def check_sla_compliance(self) -> bool:
        """
        Verify system meets SLA requirements (24-hour window).

        SLA Targets:
        - P95 total latency ≤ 60 seconds (60,000 ms)
        - Error rate ≤ 1%
        - Uptime ≥ 99% during market hours

        Returns:
            True if all SLA targets are met, False otherwise
        """
        summary = self.get_performance_summary(lookback_hours=24)
        return summary.sla_compliant

    def _check_sla(
        self,
        p95_latency: float,
        error_rate: float,
        uptime_pct: float,
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check SLA compliance and return violations.

        Args:
            p95_latency: P95 latency in milliseconds
            error_rate: Error rate as percentage
            uptime_pct: Uptime as percentage

        Returns:
            Tuple of (compliant, violations_dict)
        """
        violations = {}

        if p95_latency > self.SLA_P95_LATENCY_MS:
            violations["p95_latency"] = {
                "actual": p95_latency,
                "threshold": self.SLA_P95_LATENCY_MS,
                "message": f"P95 latency {p95_latency:.0f}ms exceeds {self.SLA_P95_LATENCY_MS}ms",
            }

        if error_rate > self.SLA_ERROR_RATE_PCT:
            violations["error_rate"] = {
                "actual": error_rate,
                "threshold": self.SLA_ERROR_RATE_PCT,
                "message": f"Error rate {error_rate:.2f}% exceeds {self.SLA_ERROR_RATE_PCT}%",
            }

        if uptime_pct < self.SLA_UPTIME_PCT:
            violations["uptime"] = {
                "actual": uptime_pct,
                "threshold": self.SLA_UPTIME_PCT,
                "message": f"Uptime {uptime_pct:.2f}% below {self.SLA_UPTIME_PCT}%",
            }

        compliant = len(violations) == 0
        return compliant, violations

    @staticmethod
    def _percentile(values: List[float], percentile: int) -> float:
        """
        Calculate percentile from list of values.

        Args:
            values: List of numeric values
            percentile: Percentile to calculate (0-100)

        Returns:
            Percentile value
        """
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    def _empty_summary(self, lookback_hours: int) -> PerformanceSummary:
        """
        Return empty summary when no data available.

        Args:
            lookback_hours: Lookback period

        Returns:
            PerformanceSummary with zero values
        """
        return PerformanceSummary(
            lookback_hours=lookback_hours,
            total_cycles=0,
            successful_cycles=0,
            avg_latency_ms=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
            p99_latency_ms=0.0,
            avg_throughput=0.0,
            total_symbols_processed=0,
            total_signals_generated=0,
            error_rate=0.0,
            uptime_pct=0.0,
            sla_compliant=True,
            sla_violations={},
        )


__all__ = [
    "LatencyMetrics",
    "ThroughputMetrics",
    "PerformanceSummary",
    "PerformanceTracker",
]
