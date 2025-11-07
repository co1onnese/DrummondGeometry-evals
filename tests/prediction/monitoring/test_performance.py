"""Unit tests for performance tracking."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from dgas.prediction.monitoring.performance import (
    LatencyMetrics,
    ThroughputMetrics,
    PerformanceSummary,
    PerformanceTracker,
)


class TestLatencyMetrics:
    """Tests for LatencyMetrics dataclass."""

    def test_create_valid_metrics(self):
        """Test creating valid latency metrics."""
        metrics = LatencyMetrics(
            data_fetch_ms=1000,
            indicator_calc_ms=2000,
            signal_generation_ms=1500,
            notification_ms=500,
            total_ms=5000,
        )

        assert metrics.data_fetch_ms == 1000
        assert metrics.indicator_calc_ms == 2000
        assert metrics.signal_generation_ms == 1500
        assert metrics.notification_ms == 500
        assert metrics.total_ms == 5000

    def test_total_calculated_property(self):
        """Test total_calculated property sums components."""
        metrics = LatencyMetrics(
            data_fetch_ms=1000,
            indicator_calc_ms=2000,
            signal_generation_ms=1500,
            notification_ms=500,
            total_ms=5000,
        )

        assert metrics.total_calculated == 5000

    def test_immutable(self):
        """Test that LatencyMetrics is immutable."""
        metrics = LatencyMetrics(
            data_fetch_ms=1000,
            indicator_calc_ms=2000,
            signal_generation_ms=1500,
            notification_ms=500,
            total_ms=5000,
        )

        with pytest.raises(AttributeError):
            metrics.total_ms = 6000

    def test_negative_values_rejected(self):
        """Test that negative values raise ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            LatencyMetrics(
                data_fetch_ms=-100,
                indicator_calc_ms=2000,
                signal_generation_ms=1500,
                notification_ms=500,
                total_ms=5000,
            )


class TestThroughputMetrics:
    """Tests for ThroughputMetrics dataclass."""

    def test_create_valid_metrics(self):
        """Test creating valid throughput metrics."""
        metrics = ThroughputMetrics(
            symbols_processed=50,
            signals_generated=10,
            execution_time_ms=5000,
            symbols_per_second=10.0,
        )

        assert metrics.symbols_processed == 50
        assert metrics.signals_generated == 10
        assert metrics.execution_time_ms == 5000
        assert metrics.symbols_per_second == 10.0

    def test_calculate_factory_method(self):
        """Test calculate() factory method computes symbols_per_second."""
        metrics = ThroughputMetrics.calculate(
            symbols_processed=50,
            signals_generated=10,
            execution_time_ms=5000,
        )

        assert metrics.symbols_processed == 50
        assert metrics.signals_generated == 10
        assert metrics.execution_time_ms == 5000
        assert metrics.symbols_per_second == 10.0  # 50 / (5000/1000)

    def test_calculate_with_zero_time(self):
        """Test calculate() handles zero execution time."""
        metrics = ThroughputMetrics.calculate(
            symbols_processed=50,
            signals_generated=10,
            execution_time_ms=0,
        )

        assert metrics.symbols_per_second == 0.0

    def test_immutable(self):
        """Test that ThroughputMetrics is immutable."""
        metrics = ThroughputMetrics.calculate(
            symbols_processed=50,
            signals_generated=10,
            execution_time_ms=5000,
        )

        with pytest.raises(AttributeError):
            metrics.symbols_processed = 100

    def test_negative_symbols_rejected(self):
        """Test that negative symbols_processed raises ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            ThroughputMetrics(
                symbols_processed=-10,
                signals_generated=5,
                execution_time_ms=5000,
                symbols_per_second=2.0,
            )

    def test_negative_execution_time_rejected(self):
        """Test that negative execution_time_ms raises ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            ThroughputMetrics(
                symbols_processed=50,
                signals_generated=10,
                execution_time_ms=-5000,
                symbols_per_second=10.0,
            )


class TestPerformanceTracker:
    """Tests for PerformanceTracker class."""

    @pytest.fixture
    def mock_persistence(self):
        """Create mock PredictionPersistence."""
        return MagicMock()

    @pytest.fixture
    def tracker(self, mock_persistence):
        """Create PerformanceTracker with mock persistence."""
        return PerformanceTracker(persistence=mock_persistence)

    def test_init(self, mock_persistence):
        """Test PerformanceTracker initialization."""
        tracker = PerformanceTracker(persistence=mock_persistence)
        assert tracker.persistence is mock_persistence

    def test_track_cycle_persists_all_metrics(self, tracker, mock_persistence):
        """Test track_cycle() persists all latency and throughput metrics."""
        latency = LatencyMetrics(
            data_fetch_ms=1000,
            indicator_calc_ms=2000,
            signal_generation_ms=1500,
            notification_ms=500,
            total_ms=5000,
        )

        throughput = ThroughputMetrics.calculate(
            symbols_processed=50,
            signals_generated=10,
            execution_time_ms=5000,
        )

        errors = ["Error 1", "Error 2"]

        tracker.track_cycle(
            run_id=123,
            latency=latency,
            throughput=throughput,
            errors=errors,
        )

        # Verify all metric types were saved
        assert mock_persistence.save_metric.call_count == 9

        # Check specific metrics
        calls = mock_persistence.save_metric.call_args_list

        # Verify latency metrics
        assert any(
            call[1]["metric_type"] == "latency_total"
            and call[1]["metric_value"] == 5000
            for call in calls
        )
        assert any(
            call[1]["metric_type"] == "latency_data_fetch"
            and call[1]["metric_value"] == 1000
            for call in calls
        )

        # Verify throughput metrics
        assert any(
            call[1]["metric_type"] == "throughput_symbols_per_second"
            and call[1]["metric_value"] == 10.0
            for call in calls
        )

        # Verify error count
        assert any(
            call[1]["metric_type"] == "error_count"
            and call[1]["metric_value"] == 2
            for call in calls
        )

    def test_track_cycle_handles_exceptions(self, tracker, mock_persistence):
        """Test track_cycle() handles persistence exceptions gracefully."""
        mock_persistence.save_metric.side_effect = Exception("DB error")

        latency = LatencyMetrics(
            data_fetch_ms=1000,
            indicator_calc_ms=2000,
            signal_generation_ms=1500,
            notification_ms=500,
            total_ms=5000,
        )

        throughput = ThroughputMetrics.calculate(
            symbols_processed=50,
            signals_generated=10,
            execution_time_ms=5000,
        )

        # Should not raise exception
        tracker.track_cycle(
            run_id=123,
            latency=latency,
            throughput=throughput,
            errors=[],
        )

    def test_get_performance_summary_with_data(self, tracker, mock_persistence):
        """Test get_performance_summary() calculates correct statistics."""
        now = datetime.now(timezone.utc)

        # Mock prediction runs
        mock_runs = [
            {
                "run_id": 1,
                "run_timestamp": now - timedelta(hours=1),
                "execution_time_ms": 5000,
                "symbols_processed": 50,
                "signals_generated": 10,
                "status": "SUCCESS",
                "errors": [],
            },
            {
                "run_id": 2,
                "run_timestamp": now - timedelta(hours=2),
                "execution_time_ms": 6000,
                "symbols_processed": 60,
                "signals_generated": 12,
                "status": "SUCCESS",
                "errors": [],
            },
            {
                "run_id": 3,
                "run_timestamp": now - timedelta(hours=3),
                "execution_time_ms": 7000,
                "symbols_processed": 55,
                "signals_generated": 8,
                "status": "PARTIAL",
                "errors": ["Error 1"],
            },
        ]

        mock_persistence.get_recent_runs.return_value = mock_runs

        summary = tracker.get_performance_summary(lookback_hours=24)

        assert summary.total_cycles == 3
        assert summary.successful_cycles == 2
        assert summary.total_symbols_processed == 165
        assert summary.total_signals_generated == 30
        assert summary.avg_latency_ms == 6000.0  # (5000 + 6000 + 7000) / 3
        assert summary.error_rate == pytest.approx(33.33, rel=0.01)  # 1/3
        assert summary.uptime_pct == pytest.approx(66.67, rel=0.01)  # 2/3

    def test_get_performance_summary_filters_by_lookback(self, tracker, mock_persistence):
        """Test get_performance_summary() filters runs by lookback window."""
        now = datetime.now(timezone.utc)

        # Some runs within window, some outside
        mock_runs = [
            {
                "run_id": 1,
                "run_timestamp": now - timedelta(hours=1),
                "execution_time_ms": 5000,
                "symbols_processed": 50,
                "signals_generated": 10,
                "status": "SUCCESS",
                "errors": [],
            },
            {
                "run_id": 2,
                "run_timestamp": now - timedelta(hours=50),  # Outside 24h window
                "execution_time_ms": 6000,
                "symbols_processed": 60,
                "signals_generated": 12,
                "status": "SUCCESS",
                "errors": [],
            },
        ]

        mock_persistence.get_recent_runs.return_value = mock_runs

        summary = tracker.get_performance_summary(lookback_hours=24)

        # Should only count run 1
        assert summary.total_cycles == 1
        assert summary.total_symbols_processed == 50

    def test_get_performance_summary_empty_data(self, tracker, mock_persistence):
        """Test get_performance_summary() with no data."""
        mock_persistence.get_recent_runs.return_value = []

        summary = tracker.get_performance_summary(lookback_hours=24)

        assert summary.total_cycles == 0
        assert summary.successful_cycles == 0
        assert summary.avg_latency_ms == 0.0
        assert summary.sla_compliant is True  # No data means no violations

    def test_percentile_calculation(self, tracker):
        """Test _percentile() method calculates correctly."""
        values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

        p50 = tracker._percentile(values, 50)
        p95 = tracker._percentile(values, 95)
        p99 = tracker._percentile(values, 99)

        # P50 index = 10 * 50 / 100 = 5 -> values[5] = 60
        assert p50 == 60
        # P95 index = 10 * 95 / 100 = 9 (capped at 9) -> values[9] = 100
        assert p95 == 100
        # P99 index = 10 * 99 / 100 = 9 (capped at 9) -> values[9] = 100
        assert p99 == 100

    def test_percentile_empty_list(self, tracker):
        """Test _percentile() handles empty list."""
        assert tracker._percentile([], 50) == 0.0

    def test_check_sla_compliance_all_pass(self, tracker, mock_persistence):
        """Test check_sla_compliance() when all SLA targets met."""
        now = datetime.now(timezone.utc)

        # Runs with good performance
        mock_runs = [
            {
                "run_id": i,
                "run_timestamp": now - timedelta(hours=i),
                "execution_time_ms": 30000,  # 30s - well under 60s P95 target
                "symbols_processed": 50,
                "signals_generated": 10,
                "status": "SUCCESS",
                "errors": [],
            }
            for i in range(1, 21)  # 20 successful runs
        ]

        mock_persistence.get_recent_runs.return_value = mock_runs

        assert tracker.check_sla_compliance() is True

    def test_check_sla_compliance_p95_violation(self, tracker, mock_persistence):
        """Test check_sla_compliance() detects P95 latency violation."""
        now = datetime.now(timezone.utc)

        # Most runs fast, but P95 will exceed threshold
        mock_runs = []
        for i in range(1, 20):
            mock_runs.append({
                "run_id": i,
                "run_timestamp": now - timedelta(hours=i),
                "execution_time_ms": 30000 if i < 19 else 70000,  # Last one is slow
                "symbols_processed": 50,
                "signals_generated": 10,
                "status": "SUCCESS",
                "errors": [],
            })

        mock_persistence.get_recent_runs.return_value = mock_runs

        summary = tracker.get_performance_summary(lookback_hours=24)

        assert summary.sla_compliant is False
        assert "p95_latency" in summary.sla_violations

    def test_check_sla_compliance_error_rate_violation(self, tracker, mock_persistence):
        """Test check_sla_compliance() detects error rate violation."""
        now = datetime.now(timezone.utc)

        # 10% error rate (exceeds 1% threshold)
        mock_runs = []
        for i in range(1, 11):
            mock_runs.append({
                "run_id": i,
                "run_timestamp": now - timedelta(hours=i),
                "execution_time_ms": 30000,
                "symbols_processed": 50,
                "signals_generated": 10,
                "status": "SUCCESS",
                "errors": ["Error"] if i == 1 else [],  # 1/10 has errors
            })

        mock_persistence.get_recent_runs.return_value = mock_runs

        summary = tracker.get_performance_summary(lookback_hours=24)

        assert summary.sla_compliant is False
        assert "error_rate" in summary.sla_violations

    def test_check_sla_compliance_uptime_violation(self, tracker, mock_persistence):
        """Test check_sla_compliance() detects uptime violation."""
        now = datetime.now(timezone.utc)

        # 90% uptime (below 99% threshold)
        mock_runs = []
        for i in range(1, 11):
            mock_runs.append({
                "run_id": i,
                "run_timestamp": now - timedelta(hours=i),
                "execution_time_ms": 30000,
                "symbols_processed": 50,
                "signals_generated": 10,
                "status": "SUCCESS" if i > 1 else "FAILED",  # 1/10 failed
                "errors": [],
            })

        mock_persistence.get_recent_runs.return_value = mock_runs

        summary = tracker.get_performance_summary(lookback_hours=24)

        assert summary.sla_compliant is False
        assert "uptime" in summary.sla_violations
