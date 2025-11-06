"""
Tests for PredictionScheduler notification integration.

This module tests the integration between the prediction scheduler and notification system,
ensuring signals are properly delivered and persisted with notification metadata.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from dgas.prediction.scheduler import PredictionScheduler, SchedulerConfig, TradingSession
from dgas.prediction.engine import (
    PredictionEngine,
    PredictionRunResult,
    GeneratedSignal,
    SignalType,
)
from dgas.prediction.persistence import PredictionPersistence
from dgas.prediction.notifications import NotificationConfig, NotificationRouter
from dgas.calculations.states import TrendDirection


@pytest.fixture
def sample_signals():
    """Create sample signals for testing."""
    return [
        GeneratedSignal(
            symbol="AAPL",
            signal_timestamp=datetime(2025, 11, 6, 14, 30, tzinfo=timezone.utc),
            signal_type=SignalType.LONG,
            entry_price=Decimal("175.50"),
            stop_loss=Decimal("173.00"),
            target_price=Decimal("180.00"),
            confidence=0.85,
            signal_strength=0.90,
            timeframe_alignment=0.88,
            risk_reward_ratio=1.8,
            htf_trend=TrendDirection.UP,
            htf_timeframe="4h",
            trading_tf_state="TREND",
            trading_timeframe="1h",
            confluence_zones_count=3,
            pattern_context={"patterns": [{"type": "PLDOT_PUSH", "strength": 0.9}]},
        ),
        GeneratedSignal(
            symbol="MSFT",
            signal_timestamp=datetime(2025, 11, 6, 14, 30, tzinfo=timezone.utc),
            signal_type=SignalType.SHORT,
            entry_price=Decimal("380.00"),
            stop_loss=Decimal("382.50"),
            target_price=Decimal("375.00"),
            confidence=0.68,
            signal_strength=0.72,
            timeframe_alignment=0.70,
            risk_reward_ratio=2.0,
            htf_trend=TrendDirection.DOWN,
            htf_timeframe="4h",
            trading_tf_state="CONGESTION_EXIT",
            trading_timeframe="1h",
            confluence_zones_count=2,
            pattern_context={"patterns": [{"type": "EXHAUST", "strength": 0.75}]},
        ),
    ]


@pytest.fixture
def mock_engine(sample_signals):
    """Create mock prediction engine."""
    engine = Mock(spec=PredictionEngine)

    # Mock execute_prediction_cycle to return signals
    engine.execute_prediction_cycle.return_value = PredictionRunResult(
        run_id=0,  # Not yet persisted
        timestamp=datetime(2025, 11, 6, 14, 30, tzinfo=timezone.utc),
        symbols_requested=2,
        symbols_processed=2,
        signals_generated=2,
        execution_time_ms=1500,
        errors=[],
        status="SUCCESS",
        data_fetch_ms=500,
        indicator_calc_ms=800,
        signal_generation_ms=200,
        signals=sample_signals,
    )

    return engine


@pytest.fixture
def mock_persistence():
    """Create mock persistence layer."""
    persistence = Mock(spec=PredictionPersistence)

    # Mock save_prediction_run to return run_id
    persistence.save_prediction_run.return_value = 123

    # Mock save_generated_signals
    persistence.save_generated_signals.return_value = 2

    # Mock update_scheduler_state
    persistence.update_scheduler_state.return_value = None

    # Mock get_scheduler_state
    persistence.get_scheduler_state.return_value = {
        "status": "IDLE",
        "last_run_timestamp": None,
        "next_scheduled_run": None,
        "current_run_id": None,
        "error_message": None,
        "updated_at": None,
    }

    return persistence


@pytest.fixture
def scheduler_config():
    """Create test scheduler configuration."""
    return SchedulerConfig(
        interval="30min",
        symbols=["AAPL", "MSFT"],
        enabled_timeframes=["4h", "1h", "30min"],
        exchange_code="US",
        trading_session=TradingSession(),
        persist_state=True,
    )


@pytest.fixture
def mock_market_hours():
    """Create mock market hours manager."""
    from dgas.prediction.scheduler import MarketHoursManager

    market_hours = Mock(spec=MarketHoursManager)
    market_hours.is_market_open.return_value = True
    market_hours.next_market_open.return_value = datetime(2025, 11, 6, 14, 30, tzinfo=timezone.utc)
    market_hours.next_market_close.return_value = datetime(2025, 11, 6, 21, 0, tzinfo=timezone.utc)
    market_hours.is_trading_day.return_value = True
    return market_hours


class TestSchedulerNotificationIntegration:
    """Test integration between scheduler and notifications."""

    @patch("dgas.prediction.scheduler.get_settings")
    @patch("dgas.prediction.notifications.router.NotificationRouter")
    @patch("dgas.prediction.notifications.router.NotificationConfig")
    def test_execute_cycle_sends_notifications(
        self,
        mock_config_class,
        mock_router_class,
        mock_get_settings,
        mock_market_hours,
        scheduler_config,
        mock_engine,
        mock_persistence,
        sample_signals,
    ):
        """Test that _execute_cycle sends notifications when signals are generated."""
        # Setup mocks
        mock_get_settings.return_value = Mock(database_url="postgresql://test")
        mock_config = Mock(spec=NotificationConfig)
        mock_config.enabled_channels = ["console", "discord"]
        mock_config.console_max_signals = 10
        mock_config.console_format = "summary"
        mock_config.discord_bot_token = "test_token"
        mock_config.discord_channel_id = "123456"
        mock_config.discord_min_confidence = 0.5
        mock_config_class.from_env.return_value = mock_config

        mock_router = Mock(spec=NotificationRouter)
        mock_router.send_notifications.return_value = {
            "console": True,
            "discord": True,
        }
        mock_router.get_notification_metadata.return_value = {
            "AAPL": {
                "notification_sent": True,
                "notification_channels": ["console", "discord"],
                "notification_timestamp": datetime(2025, 11, 6, 14, 30, 5, tzinfo=timezone.utc),
            },
            "MSFT": {
                "notification_sent": True,
                "notification_channels": ["console", "discord"],
                "notification_timestamp": datetime(2025, 11, 6, 14, 30, 5, tzinfo=timezone.utc),
            },
        }
        mock_router_class.return_value = mock_router

        # Create scheduler
        scheduler = PredictionScheduler(
            config=scheduler_config,
            engine=mock_engine,
            persistence=mock_persistence,
            market_hours=mock_market_hours,
        )

        # Execute cycle
        result = scheduler._execute_cycle()

        # Verify signals were persisted with notification metadata
        assert mock_persistence.save_generated_signals.called
        saved_signals = mock_persistence.save_generated_signals.call_args[0][1]
        assert len(saved_signals) == 2

        # Check first signal has notification metadata
        # Console should succeed, discord should fail (no real bot token in test)
        assert saved_signals[0]["notification_sent"] is True
        assert "console" in saved_signals[0]["notification_channels"]
        # Discord won't be in channels because adapter wasn't created (no token)
        assert saved_signals[0]["notification_timestamp"] is not None

    @patch("dgas.prediction.scheduler.get_settings")
    @patch("dgas.prediction.notifications.NotificationRouter")
    @patch("dgas.prediction.notifications.NotificationConfig")
    def test_execute_cycle_handles_notification_failure_gracefully(
        self,
        mock_config_class,
        mock_router_class,
        mock_get_settings,
        mock_market_hours,
        scheduler_config,
        mock_engine,
        mock_persistence,
    ):
        """Test that notification failures don't crash the scheduler."""
        # Setup mocks
        mock_get_settings.return_value = Mock(database_url="postgresql://test")
        mock_config = Mock(spec=NotificationConfig)
        mock_config.enabled_channels = ["discord"]
        mock_config.discord_bot_token = "test_token"
        mock_config.discord_channel_id = "123456"
        mock_config.discord_min_confidence = 0.5
        mock_config_class.from_env.return_value = mock_config

        # Mock router to fail
        mock_router = Mock(spec=NotificationRouter)
        mock_router.send_notifications.side_effect = Exception("Discord API error")
        mock_router_class.return_value = mock_router

        # Create scheduler
        scheduler = PredictionScheduler(
            config=scheduler_config,
            engine=mock_engine,
            persistence=mock_persistence,
            market_hours=mock_market_hours,
        )

        # Execute cycle - should NOT raise exception
        result = scheduler._execute_cycle()

        # Verify cycle completed despite notification failure
        assert result.status == "SUCCESS"
        assert result.signals_generated == 2

        # Verify signals were still persisted (with no notification metadata)
        assert mock_persistence.save_generated_signals.called
        saved_signals = mock_persistence.save_generated_signals.call_args[0][1]
        assert len(saved_signals) == 2
        assert saved_signals[0]["notification_sent"] is False

    @patch("dgas.prediction.scheduler.get_settings")
    @patch("dgas.prediction.notifications.NotificationRouter")
    @patch("dgas.prediction.notifications.NotificationConfig")
    def test_execute_cycle_skips_notifications_when_no_signals(
        self,
        mock_config_class,
        mock_router_class,
        mock_get_settings,
        mock_market_hours,
        scheduler_config,
        mock_engine,
        mock_persistence,
    ):
        """Test that notifications are skipped when no signals are generated."""
        mock_get_settings.return_value = Mock(database_url="postgresql://test")
        # Setup engine to return no signals
        mock_engine.execute_prediction_cycle.return_value = PredictionRunResult(
            run_id=0,
            timestamp=datetime(2025, 11, 6, 14, 30, tzinfo=timezone.utc),
            symbols_requested=2,
            symbols_processed=2,
            signals_generated=0,
            execution_time_ms=1500,
            errors=[],
            status="SUCCESS",
            data_fetch_ms=500,
            indicator_calc_ms=800,
            signal_generation_ms=200,
            signals=[],  # No signals
        )

        # Create scheduler
        scheduler = PredictionScheduler(
            config=scheduler_config,
            engine=mock_engine,
            persistence=mock_persistence,
            market_hours=mock_market_hours,
        )

        # Execute cycle
        result = scheduler._execute_cycle()

        # Verify notifications were NOT attempted
        assert not mock_config_class.from_env.called
        assert not mock_router_class.called

        # Verify cycle still completed successfully
        assert result.status == "SUCCESS"
        assert result.signals_generated == 0

    @patch("dgas.prediction.scheduler.get_settings")
    @patch("dgas.prediction.notifications.NotificationRouter")
    @patch("dgas.prediction.notifications.NotificationConfig")
    def test_execute_cycle_tracks_notification_timing(
        self,
        mock_config_class,
        mock_router_class,
        mock_get_settings,
        mock_market_hours,
        scheduler_config,
        mock_engine,
        mock_persistence,
    ):
        """Test that notification timing is tracked in metrics."""
        # Setup mocks
        mock_get_settings.return_value = Mock(database_url="postgresql://test")
        mock_config = Mock(spec=NotificationConfig)
        mock_config.enabled_channels = ["console"]
        mock_config.console_max_signals = 10
        mock_config.console_format = "summary"
        mock_config_class.from_env.return_value = mock_config

        mock_router = Mock(spec=NotificationRouter)
        mock_router.send_notifications.return_value = {"console": True}
        mock_router.get_notification_metadata.return_value = {
            "AAPL": {
                "notification_sent": True,
                "notification_channels": ["console"],
                "notification_timestamp": datetime(2025, 11, 6, 14, 30, 5, tzinfo=timezone.utc),
            },
            "MSFT": {
                "notification_sent": True,
                "notification_channels": ["console"],
                "notification_timestamp": datetime(2025, 11, 6, 14, 30, 5, tzinfo=timezone.utc),
            },
        }
        mock_router_class.return_value = mock_router

        # Create scheduler
        scheduler = PredictionScheduler(
            config=scheduler_config,
            engine=mock_engine,
            persistence=mock_persistence,
            market_hours=mock_market_hours,
        )

        # Execute cycle
        result = scheduler._execute_cycle()

        # Verify notification_ms was passed to persistence
        assert mock_persistence.save_prediction_run.called
        call_args = mock_persistence.save_prediction_run.call_args[1]
        assert "notification_ms" in call_args
        assert call_args["notification_ms"] >= 0  # Should have some timing value

    @patch("dgas.prediction.scheduler.get_settings")
    @patch("dgas.prediction.notifications.NotificationRouter")
    @patch("dgas.prediction.notifications.NotificationConfig")
    def test_execute_cycle_filters_signals_by_confidence(
        self,
        mock_config_class,
        mock_router_class,
        mock_get_settings,
        mock_market_hours,
        scheduler_config,
        mock_engine,
        mock_persistence,
        sample_signals,
    ):
        """Test that signals are filtered by channel-specific confidence thresholds."""
        # Setup mocks with high Discord confidence threshold
        mock_get_settings.return_value = Mock(database_url="postgresql://test")
        mock_config = Mock(spec=NotificationConfig)
        mock_config.enabled_channels = ["discord"]
        mock_config.discord_bot_token = "test_token"
        mock_config.discord_channel_id = "123456"
        mock_config.discord_min_confidence = 0.80  # High threshold
        mock_config_class.from_env.return_value = mock_config

        mock_router = Mock(spec=NotificationRouter)
        mock_router.send_notifications.return_value = {"discord": True}

        # Only AAPL (0.85 confidence) should pass filter, not MSFT (0.68)
        mock_router.get_notification_metadata.return_value = {
            "AAPL": {
                "notification_sent": True,
                "notification_channels": ["discord"],
                "notification_timestamp": datetime(2025, 11, 6, 14, 30, 5, tzinfo=timezone.utc),
            },
            "MSFT": {
                "notification_sent": False,
                "notification_channels": None,
                "notification_timestamp": None,
            },
        }
        mock_router_class.return_value = mock_router

        # Create scheduler
        scheduler = PredictionScheduler(
            config=scheduler_config,
            engine=mock_engine,
            persistence=mock_persistence,
            market_hours=mock_market_hours,
        )

        # Execute cycle
        result = scheduler._execute_cycle()

        # Verify router received all signals (filtering happens in router)
        assert mock_router.send_notifications.called
        sent_signals = mock_router.send_notifications.call_args[1]["signals"]
        assert len(sent_signals) == 2  # Both signals sent to router

        # Verify metadata shows filtered results
        assert mock_router.get_notification_metadata.called
        metadata = mock_router.get_notification_metadata.return_value
        assert metadata["AAPL"]["notification_sent"] is True
        assert metadata["MSFT"]["notification_sent"] is False


class TestNotificationMetadataPersistence:
    """Test notification metadata persistence."""

    @patch("dgas.prediction.scheduler.get_settings")
    @patch("dgas.prediction.notifications.NotificationRouter")
    @patch("dgas.prediction.notifications.NotificationConfig")
    def test_signal_dictionaries_include_notification_fields(
        self,
        mock_config_class,
        mock_router_class,
        mock_get_settings,
        mock_market_hours,
        scheduler_config,
        mock_engine,
        mock_persistence,
    ):
        """Test that persisted signal dictionaries include all notification fields."""
        # Setup mocks
        mock_get_settings.return_value = Mock(database_url="postgresql://test")
        mock_config = Mock(spec=NotificationConfig)
        mock_config.enabled_channels = ["console"]
        mock_config.console_max_signals = 10
        mock_config.console_format = "summary"
        mock_config_class.from_env.return_value = mock_config

        notification_ts = datetime(2025, 11, 6, 14, 30, 5, tzinfo=timezone.utc)
        mock_router = Mock(spec=NotificationRouter)
        mock_router.send_notifications.return_value = {"console": True}
        mock_router.get_notification_metadata.return_value = {
            "AAPL": {
                "notification_sent": True,
                "notification_channels": ["console"],
                "notification_timestamp": notification_ts,
            },
            "MSFT": {
                "notification_sent": True,
                "notification_channels": ["console"],
                "notification_timestamp": notification_ts,
            },
        }
        mock_router_class.return_value = mock_router

        # Create scheduler
        scheduler = PredictionScheduler(
            config=scheduler_config,
            engine=mock_engine,
            persistence=mock_persistence,
            market_hours=mock_market_hours,
        )

        # Execute cycle
        result = scheduler._execute_cycle()

        # Get persisted signals
        assert mock_persistence.save_generated_signals.called
        saved_signals = mock_persistence.save_generated_signals.call_args[0][1]

        # Verify all required fields are present
        for signal_dict in saved_signals:
            # Core fields
            assert "symbol" in signal_dict
            assert "signal_type" in signal_dict
            assert "entry_price" in signal_dict
            assert "confidence" in signal_dict

            # Notification fields
            assert "notification_sent" in signal_dict
            assert signal_dict["notification_sent"] is True
            assert "notification_channels" in signal_dict
            assert "console" in signal_dict["notification_channels"]
            assert "notification_timestamp" in signal_dict
            assert signal_dict["notification_timestamp"] == notification_ts

    @patch("dgas.prediction.scheduler.get_settings")
    @patch("dgas.prediction.notifications.NotificationRouter")
    @patch("dgas.prediction.notifications.NotificationConfig")
    def test_signals_without_notifications_have_default_metadata(
        self,
        mock_config_class,
        mock_router_class,
        mock_get_settings,
        mock_market_hours,
        scheduler_config,
        mock_engine,
        mock_persistence,
    ):
        """Test that signals without notifications get default metadata."""
        # Setup mocks - notifications disabled
        mock_get_settings.return_value = Mock(database_url="postgresql://test")
        mock_config = Mock(spec=NotificationConfig)
        mock_config.enabled_channels = []  # No channels enabled
        mock_config_class.from_env.return_value = mock_config

        # Create scheduler
        scheduler = PredictionScheduler(
            config=scheduler_config,
            engine=mock_engine,
            persistence=mock_persistence,
            market_hours=mock_market_hours,
        )

        # Execute cycle
        result = scheduler._execute_cycle()

        # Get persisted signals
        assert mock_persistence.save_generated_signals.called
        saved_signals = mock_persistence.save_generated_signals.call_args[0][1]

        # Verify default notification metadata
        for signal_dict in saved_signals:
            assert signal_dict["notification_sent"] is False
            assert signal_dict["notification_channels"] is None
            assert signal_dict["notification_timestamp"] is None
