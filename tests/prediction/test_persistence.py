"""Tests for prediction persistence layer."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from dgas.prediction.persistence import PredictionPersistence


class TestPredictionRunPersistence:
    """Test prediction run persistence operations."""

    def test_save_prediction_run_basic(self, test_persistence):
        """Test saving a basic prediction run."""
        run_id = test_persistence.save_prediction_run(
            interval_type="30min",
            symbols_requested=10,
            symbols_processed=10,
            signals_generated=5,
            execution_time_ms=5000,
            status="SUCCESS",
        )

        assert run_id > 0

        # Verify run was saved
        runs = test_persistence.get_recent_runs(limit=1)
        assert len(runs) == 1
        assert runs[0]["run_id"] == run_id
        assert runs[0]["status"] == "SUCCESS"
        assert runs[0]["symbols_requested"] == 10
        assert runs[0]["symbols_processed"] == 10
        assert runs[0]["signals_generated"] == 5

    def test_save_prediction_run_with_latency(self, test_persistence):
        """Test saving prediction run with latency breakdown."""
        run_id = test_persistence.save_prediction_run(
            interval_type="1h",
            symbols_requested=50,
            symbols_processed=48,
            signals_generated=12,
            execution_time_ms=45000,
            status="PARTIAL",
            data_fetch_ms=15000,
            indicator_calc_ms=20000,
            signal_generation_ms=8000,
            notification_ms=2000,
        )

        runs = test_persistence.get_recent_runs(limit=1)
        assert runs[0]["run_id"] == run_id
        assert runs[0]["data_fetch_ms"] == 15000
        assert runs[0]["indicator_calc_ms"] == 20000
        assert runs[0]["signal_generation_ms"] == 8000
        assert runs[0]["notification_ms"] == 2000

    def test_save_prediction_run_with_errors(self, test_persistence):
        """Test saving prediction run with errors."""
        errors = ["Symbol XYZ not found", "API timeout"]
        run_id = test_persistence.save_prediction_run(
            interval_type="30min",
            symbols_requested=10,
            symbols_processed=8,
            signals_generated=3,
            execution_time_ms=30000,
            status="FAILED",
            errors=errors,
        )

        runs = test_persistence.get_recent_runs(limit=1)
        assert runs[0]["run_id"] == run_id
        assert runs[0]["status"] == "FAILED"
        assert runs[0]["errors"] == errors

    def test_get_recent_runs_filter_by_status(self, test_persistence):
        """Test filtering runs by status."""
        # Create runs with different statuses
        test_persistence.save_prediction_run(
            interval_type="30min",
            symbols_requested=10,
            symbols_processed=10,
            signals_generated=5,
            execution_time_ms=5000,
            status="SUCCESS",
        )
        test_persistence.save_prediction_run(
            interval_type="30min",
            symbols_requested=10,
            symbols_processed=8,
            signals_generated=2,
            execution_time_ms=5000,
            status="FAILED",
        )

        success_runs = test_persistence.get_recent_runs(status="SUCCESS")
        failed_runs = test_persistence.get_recent_runs(status="FAILED")

        assert len(success_runs) >= 1
        assert len(failed_runs) >= 1
        assert all(r["status"] == "SUCCESS" for r in success_runs)
        assert all(r["status"] == "FAILED" for r in failed_runs)


class TestSignalPersistence:
    """Test generated signal persistence operations."""

    def test_save_generated_signals_basic(self, test_persistence, test_symbol_id):
        """Test saving generated signals."""
        # Create a prediction run first
        run_id = test_persistence.save_prediction_run(
            interval_type="30min",
            symbols_requested=1,
            symbols_processed=1,
            signals_generated=1,
            execution_time_ms=5000,
            status="SUCCESS",
        )

        # Create signal
        signals = [{
            "symbol": "AAPL",
            "signal_timestamp": datetime.now(timezone.utc),
            "signal_type": "LONG",
            "entry_price": Decimal("150.50"),
            "stop_loss": Decimal("148.00"),
            "target_price": Decimal("155.00"),
            "confidence": 0.75,
            "signal_strength": 0.80,
            "timeframe_alignment": 0.85,
            "risk_reward_ratio": 1.8,
            "htf_trend": "UP",
            "trading_tf_state": "TREND",
            "confluence_zones_count": 2,
            "pattern_context": {"patterns": ["PLDOT_PUSH"], "indicators": {}},
            "notification_sent": True,
            "notification_channels": ["console", "email"],
            "notification_timestamp": datetime.now(timezone.utc),
        }]

        count = test_persistence.save_generated_signals(run_id, signals)
        assert count == 1

        # Verify signal was saved
        saved_signals = test_persistence.get_recent_signals(symbol="AAPL", limit=1)
        assert len(saved_signals) == 1
        assert saved_signals[0]["symbol"] == "AAPL"
        assert saved_signals[0]["signal_type"] == "LONG"
        assert saved_signals[0]["confidence"] == 0.75
        assert saved_signals[0]["htf_trend"] == "UP"

    def test_save_multiple_signals(self, test_persistence, test_symbol_id):
        """Test saving multiple signals at once."""
        run_id = test_persistence.save_prediction_run(
            interval_type="1h",
            symbols_requested=2,
            symbols_processed=2,
            signals_generated=2,
            execution_time_ms=8000,
            status="SUCCESS",
        )

        signals = [
            {
                "symbol": "AAPL",
                "signal_timestamp": datetime.now(timezone.utc),
                "signal_type": "LONG",
                "entry_price": Decimal("150.00"),
                "stop_loss": Decimal("148.00"),
                "target_price": Decimal("155.00"),
                "confidence": 0.70,
                "signal_strength": 0.75,
                "timeframe_alignment": 0.80,
            },
            {
                "symbol": "AAPL",
                "signal_timestamp": datetime.now(timezone.utc),
                "signal_type": "SHORT",
                "entry_price": Decimal("149.50"),
                "stop_loss": Decimal("151.00"),
                "target_price": Decimal("145.00"),
                "confidence": 0.65,
                "signal_strength": 0.70,
                "timeframe_alignment": 0.60,
            },
        ]

        count = test_persistence.save_generated_signals(run_id, signals)
        assert count == 2

    def test_get_recent_signals_with_filters(self, test_persistence, test_symbol_id):
        """Test filtering signals by various criteria."""
        run_id = test_persistence.save_prediction_run(
            interval_type="30min",
            symbols_requested=1,
            symbols_processed=1,
            signals_generated=2,
            execution_time_ms=5000,
            status="SUCCESS",
        )

        signals = [
            {
                "symbol": "AAPL",
                "signal_timestamp": datetime.now(timezone.utc),
                "signal_type": "LONG",
                "entry_price": Decimal("150.00"),
                "stop_loss": Decimal("148.00"),
                "target_price": Decimal("155.00"),
                "confidence": 0.80,  # High confidence
                "signal_strength": 0.85,
                "timeframe_alignment": 0.90,
            },
            {
                "symbol": "AAPL",
                "signal_timestamp": datetime.now(timezone.utc),
                "signal_type": "SHORT",
                "entry_price": Decimal("149.50"),
                "stop_loss": Decimal("151.00"),
                "target_price": Decimal("145.00"),
                "confidence": 0.50,  # Low confidence
                "signal_strength": 0.55,
                "timeframe_alignment": 0.60,
            },
        ]

        test_persistence.save_generated_signals(run_id, signals)

        # Filter by minimum confidence
        high_conf_signals = test_persistence.get_recent_signals(
            symbol="AAPL",
            min_confidence=0.7,
            limit=10
        )

        assert len(high_conf_signals) >= 1
        assert all(s["confidence"] >= 0.7 for s in high_conf_signals)

    def test_update_signal_outcome(self, test_persistence, test_symbol_id):
        """Test updating signal with outcome data."""
        run_id = test_persistence.save_prediction_run(
            interval_type="30min",
            symbols_requested=1,
            symbols_processed=1,
            signals_generated=1,
            execution_time_ms=5000,
            status="SUCCESS",
        )

        signals = [{
            "symbol": "AAPL",
            "signal_timestamp": datetime.now(timezone.utc),
            "signal_type": "LONG",
            "entry_price": Decimal("150.00"),
            "stop_loss": Decimal("148.00"),
            "target_price": Decimal("155.00"),
            "confidence": 0.75,
            "signal_strength": 0.80,
            "timeframe_alignment": 0.85,
        }]

        test_persistence.save_generated_signals(run_id, signals)

        # Get the signal ID
        saved_signals = test_persistence.get_recent_signals(symbol="AAPL", limit=1)
        signal_id = saved_signals[0]["signal_id"]

        # Update with outcome
        test_persistence.update_signal_outcome(
            signal_id=signal_id,
            outcome="WIN",
            actual_high=Decimal("156.00"),
            actual_low=Decimal("149.50"),
            actual_close=Decimal("155.50"),
            pnl_pct=3.67,
        )

        # Verify outcome was saved
        updated_signals = test_persistence.get_recent_signals(symbol="AAPL", limit=1)
        assert updated_signals[0]["outcome"] == "WIN"
        assert updated_signals[0]["pnl_pct"] == pytest.approx(3.67, rel=1e-2)


class TestMetricsPersistence:
    """Test metrics persistence operations."""

    def test_save_metric_basic(self, test_persistence):
        """Test saving a basic metric."""
        metric_id = test_persistence.save_metric(
            metric_type="latency_p95",
            metric_value=45.5,
        )

        assert metric_id > 0

        # Verify metric was saved
        metrics = test_persistence.get_metrics(metric_type="latency_p95", limit=1)
        assert len(metrics) == 1
        assert metrics[0]["metric_type"] == "latency_p95"
        assert metrics[0]["metric_value"] == pytest.approx(45.5, rel=1e-6)

    def test_save_metric_with_metadata(self, test_persistence):
        """Test saving metric with metadata."""
        metadata = {
            "confidence_bucket": "0.7-0.8",
            "symbol": "AAPL",
            "interval": "30min",
        }

        metric_id = test_persistence.save_metric(
            metric_type="win_rate",
            metric_value=0.65,
            aggregation_period="daily",
            metadata=metadata,
        )

        metrics = test_persistence.get_metrics(metric_type="win_rate", limit=1)
        assert metrics[0]["metadata"] == metadata
        assert metrics[0]["aggregation_period"] == "daily"

    def test_get_metrics_with_filters(self, test_persistence):
        """Test filtering metrics by type and aggregation."""
        # Save different metric types
        test_persistence.save_metric(
            metric_type="latency_p95",
            metric_value=45.0,
            aggregation_period="hourly",
        )
        test_persistence.save_metric(
            metric_type="win_rate",
            metric_value=0.62,
            aggregation_period="daily",
        )

        # Filter by type
        latency_metrics = test_persistence.get_metrics(metric_type="latency_p95")
        assert len(latency_metrics) >= 1
        assert all(m["metric_type"] == "latency_p95" for m in latency_metrics)

        # Filter by aggregation
        daily_metrics = test_persistence.get_metrics(aggregation_period="daily")
        assert len(daily_metrics) >= 1
        assert all(m["aggregation_period"] == "daily" for m in daily_metrics)


class TestSchedulerState:
    """Test scheduler state management."""

    def test_get_scheduler_state_initial(self, test_persistence):
        """Test getting initial scheduler state."""
        state = test_persistence.get_scheduler_state()

        assert state["status"] in ["IDLE", "RUNNING", "STOPPED", "ERROR"]
        assert "last_run_timestamp" in state
        assert "next_scheduled_run" in state

    def test_update_scheduler_state(self, test_persistence):
        """Test updating scheduler state."""
        test_persistence.update_scheduler_state(
            status="RUNNING",
            next_scheduled_run=datetime.now(timezone.utc),
        )

        state = test_persistence.get_scheduler_state()
        assert state["status"] == "RUNNING"
        assert state["next_scheduled_run"] is not None

    def test_update_scheduler_state_with_error(self, test_persistence):
        """Test updating scheduler state with error."""
        error_msg = "Database connection failed"
        test_persistence.update_scheduler_state(
            status="ERROR",
            error_message=error_msg,
        )

        state = test_persistence.get_scheduler_state()
        assert state["status"] == "ERROR"
        assert state["error_message"] == error_msg


# Fixtures

@pytest.fixture
def test_persistence(test_db):
    """Create a PredictionPersistence instance for testing."""
    from dgas.settings import Settings

    settings = Settings()
    persistence = PredictionPersistence(settings)

    yield persistence

    persistence.close()


@pytest.fixture
def test_symbol_id(test_persistence):
    """Ensure test symbol exists in database."""
    conn = test_persistence._get_connection()
    cursor = conn.cursor()

    try:
        # Insert test symbol if not exists
        cursor.execute(
            """
            INSERT INTO market_symbols (symbol, exchange)
            VALUES ('AAPL', 'NASDAQ')
            ON CONFLICT (symbol) DO NOTHING
            RETURNING symbol_id
            """
        )
        result = cursor.fetchone()

        if result is None:
            # Symbol already exists, fetch it
            cursor.execute(
                "SELECT symbol_id FROM market_symbols WHERE symbol = 'AAPL'"
            )
            result = cursor.fetchone()

        conn.commit()
        symbol_id = result[0]

    finally:
        cursor.close()

    return symbol_id


@pytest.fixture
def test_db():
    """
    Placeholder for database fixture.
    In actual implementation, this would set up a test database
    with migrations applied.
    """
    # This would normally set up a test database
    # For now, assume migrations are applied to dev database
    pass
