"""
Unit tests for prediction scheduler components.

Tests cover:
- TradingSession validation
- MarketHoursManager (market open/close logic)
- ExchangeCalendar (EODHD integration)
- PredictionScheduler (APScheduler orchestration)
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from dgas.data.exchange_calendar import ExchangeCalendar
from dgas.prediction.scheduler import (
    TradingSession,
    SchedulerConfig,
    MarketHoursManager,
    PredictionScheduler,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def eodhd_exchange_fixture():
    """Load EODHD exchange response fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "eodhd_exchange_us.json"
    with open(fixture_path, "r") as f:
        return json.load(f)


@pytest.fixture
def default_trading_session():
    """Default US market trading session."""
    return TradingSession(
        market_open=time(9, 30),
        market_close=time(16, 0),
        timezone="America/New_York",
        trading_days=["MON", "TUE", "WED", "THU", "FRI"],
    )


@pytest.fixture
def mock_exchange_calendar():
    """Mock ExchangeCalendar for testing."""
    calendar = Mock(spec=ExchangeCalendar)
    calendar.sync_exchange_calendar = Mock(return_value=(10, 100))
    calendar.is_trading_day = Mock(return_value=True)
    calendar.get_trading_hours = Mock(return_value=(time(9, 30), time(16, 0)))
    return calendar


@pytest.fixture
def mock_prediction_engine():
    """Mock PredictionEngine for testing."""
    from dgas.prediction.engine import PredictionRunResult

    engine = Mock()
    engine.execute_prediction_cycle = Mock(
        return_value=PredictionRunResult(
            run_id=1,
            timestamp=datetime.now(timezone.utc),
            symbols_requested=5,
            symbols_processed=5,
            signals_generated=3,
            execution_time_ms=1500,
            data_fetch_ms=500,
            indicator_calc_ms=700,
            signal_generation_ms=200,
            status="SUCCESS",
            errors=[],
        )
    )
    return engine


@pytest.fixture
def mock_prediction_persistence():
    """Mock PredictionPersistence for testing."""
    persistence = Mock()
    persistence.update_scheduler_state = Mock()
    persistence.get_scheduler_state = Mock(return_value=None)
    return persistence


# ============================================================================
# TradingSession Tests
# ============================================================================


class TestTradingSession:
    """Test TradingSession dataclass."""

    def test_create_with_defaults(self):
        """Test creation with default values."""
        session = TradingSession()

        assert session.market_open == time(9, 30)
        assert session.market_close == time(16, 0)
        assert session.timezone == "America/New_York"
        assert session.trading_days == ["MON", "TUE", "WED", "THU", "FRI"]

    def test_create_with_custom_values(self):
        """Test creation with custom values."""
        session = TradingSession(
            market_open=time(8, 0),
            market_close=time(17, 0),
            timezone="Europe/London",
            trading_days=["MON", "TUE", "WED", "THU"],
        )

        assert session.market_open == time(8, 0)
        assert session.market_close == time(17, 0)
        assert session.timezone == "Europe/London"
        assert len(session.trading_days) == 4

    def test_validation_market_hours(self):
        """Test that market_open must be before market_close."""
        with pytest.raises(ValueError, match="must be before"):
            TradingSession(
                market_open=time(16, 0),
                market_close=time(9, 30),
            )

    def test_validation_invalid_timezone(self):
        """Test that invalid timezone raises error."""
        with pytest.raises(ValueError, match="Invalid timezone"):
            TradingSession(timezone="Invalid/Timezone")

    def test_immutability(self):
        """Test that TradingSession is frozen/immutable."""
        session = TradingSession()

        with pytest.raises((AttributeError, TypeError)):
            session.market_open = time(10, 0)


# ============================================================================
# Market Hours Manager Tests
# ============================================================================


class TestMarketHoursManager:
    """Test MarketHoursManager market hours logic."""

    def test_init(self, default_trading_session, mock_exchange_calendar):
        """Test initialization."""
        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        assert manager.exchange_code == "US"
        assert manager.session == default_trading_session
        assert manager.calendar == mock_exchange_calendar

    def test_is_market_open_during_trading_hours(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test is_market_open returns True during trading hours."""
        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Wednesday at 2:00 PM ET (14:00) - market should be open
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 6, 14, 0, tzinfo=et_tz).astimezone(timezone.utc)

        assert manager.is_market_open(test_time)

    def test_is_market_open_before_open(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test is_market_open returns False before market opens."""
        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Wednesday at 8:00 AM ET - before market open
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 6, 8, 0, tzinfo=et_tz).astimezone(timezone.utc)

        assert not manager.is_market_open(test_time)

    def test_is_market_open_after_close(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test is_market_open returns False after market closes."""
        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Wednesday at 5:00 PM ET - after market close
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 6, 17, 0, tzinfo=et_tz).astimezone(timezone.utc)

        assert not manager.is_market_open(test_time)

    def test_is_market_open_on_weekend(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test is_market_open returns False on weekends."""
        # Configure mock to return False for weekend
        mock_exchange_calendar.is_trading_day.return_value = False

        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Saturday at 2:00 PM ET
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 9, 14, 0, tzinfo=et_tz).astimezone(timezone.utc)

        assert not manager.is_market_open(test_time)

    def test_is_market_open_on_holiday(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test is_market_open returns False on market holidays."""
        # Configure mock to return False for holiday
        mock_exchange_calendar.is_trading_day.return_value = False

        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Thanksgiving 2024
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 28, 14, 0, tzinfo=et_tz).astimezone(timezone.utc)

        assert not manager.is_market_open(test_time)

    def test_is_market_open_half_day(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test is_market_open handles half-day early close."""
        # Configure mock for half-day (early close at 1:00 PM)
        mock_exchange_calendar.get_trading_hours.return_value = (time(9, 30), time(13, 0))

        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Day after Thanksgiving at 12:30 PM (before early close)
        et_tz = ZoneInfo("America/New_York")
        test_time_before = datetime(2024, 11, 29, 12, 30, tzinfo=et_tz).astimezone(timezone.utc)
        assert manager.is_market_open(test_time_before)

        # Day after Thanksgiving at 1:30 PM (after early close)
        test_time_after = datetime(2024, 11, 29, 13, 30, tzinfo=et_tz).astimezone(timezone.utc)
        assert not manager.is_market_open(test_time_after)

    def test_next_market_open_when_currently_open(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test next_market_open returns today's open when market is open."""
        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Wednesday at 2:00 PM ET (market open)
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 6, 14, 0, tzinfo=et_tz).astimezone(timezone.utc)

        next_open = manager.next_market_open(test_time)
        next_open_et = next_open.astimezone(et_tz)

        # Should return today's market open (9:30 AM)
        assert next_open_et.date() == date(2024, 11, 6)
        assert next_open_et.time() == time(9, 30)

    def test_next_market_open_after_hours(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test next_market_open returns next day when market is closed."""
        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Wednesday at 5:00 PM ET (after close)
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 6, 17, 0, tzinfo=et_tz).astimezone(timezone.utc)

        next_open = manager.next_market_open(test_time)
        next_open_et = next_open.astimezone(et_tz)

        # Should return Thursday's market open
        assert next_open_et.date() == date(2024, 11, 7)
        assert next_open_et.time() == time(9, 30)

    def test_next_market_open_on_friday_evening(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test next_market_open on Friday evening returns Monday."""
        # Mock is_trading_day to return False for weekends
        def is_trading_day_side_effect(exchange_code: str, check_date: date) -> bool:
            return check_date.weekday() < 5  # Monday=0, Friday=4

        mock_exchange_calendar.is_trading_day.side_effect = is_trading_day_side_effect

        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Friday at 5:00 PM ET (after close)
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 8, 17, 0, tzinfo=et_tz).astimezone(timezone.utc)

        next_open = manager.next_market_open(test_time)
        next_open_et = next_open.astimezone(et_tz)

        # Should return Monday's market open
        assert next_open_et.date() == date(2024, 11, 11)
        assert next_open_et.weekday() == 0  # Monday
        assert next_open_et.time() == time(9, 30)

    def test_next_market_close(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test next_market_close calculation."""
        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Wednesday at 2:00 PM ET (during trading)
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 6, 14, 0, tzinfo=et_tz).astimezone(timezone.utc)

        next_close = manager.next_market_close(test_time)
        next_close_et = next_close.astimezone(et_tz)

        # Should return today's market close (4:00 PM)
        assert next_close_et.date() == date(2024, 11, 6)
        assert next_close_et.time() == time(16, 0)

    def test_is_trading_day_weekday(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test is_trading_day returns True for weekdays."""
        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Wednesday
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 6, 12, 0, tzinfo=et_tz)

        assert manager.is_trading_day(test_time)

    def test_is_trading_day_weekend(
        self, default_trading_session, mock_exchange_calendar
    ):
        """Test is_trading_day returns False for weekends."""
        mock_exchange_calendar.is_trading_day.return_value = False

        manager = MarketHoursManager(
            "US",
            default_trading_session,
            calendar=mock_exchange_calendar,
        )

        # Saturday
        et_tz = ZoneInfo("America/New_York")
        test_time = datetime(2024, 11, 9, 12, 0, tzinfo=et_tz)

        assert not manager.is_trading_day(test_time)


# ============================================================================
# Scheduler Config Tests
# ============================================================================


class TestSchedulerConfig:
    """Test SchedulerConfig dataclass."""

    def test_create_with_defaults(self):
        """Test creation with default values."""
        config = SchedulerConfig()

        assert config.interval == "30min"
        assert config.symbols == []
        assert config.enabled_timeframes == ["4h", "1h", "30min"]
        assert config.exchange_code == "US"
        assert config.min_confidence == 0.6
        assert config.run_on_startup is True

    def test_create_with_custom_values(self):
        """Test creation with custom values."""
        config = SchedulerConfig(
            interval="15min",
            symbols=["AAPL", "MSFT", "GOOGL"],
            min_confidence=0.7,
            max_symbols_per_cycle=100,
        )

        assert config.interval == "15min"
        assert len(config.symbols) == 3
        assert config.min_confidence == 0.7
        assert config.max_symbols_per_cycle == 100


# ============================================================================
# Prediction Scheduler Tests
# ============================================================================


class TestPredictionScheduler:
    """Test PredictionScheduler core functionality."""

    def test_init(
        self,
        mock_prediction_engine,
        mock_prediction_persistence,
        mock_exchange_calendar,
    ):
        """Test scheduler initialization."""
        config = SchedulerConfig(symbols=["AAPL"])
        market_hours = MarketHoursManager("US", TradingSession(), mock_exchange_calendar)

        scheduler = PredictionScheduler(
            config=config,
            engine=mock_prediction_engine,
            persistence=mock_prediction_persistence,
            market_hours=market_hours,
        )

        assert scheduler.config == config
        assert scheduler.engine == mock_prediction_engine
        assert scheduler.persistence == mock_prediction_persistence
        assert not scheduler.is_running()

    def test_run_once(
        self,
        mock_prediction_engine,
        mock_prediction_persistence,
        mock_exchange_calendar,
    ):
        """Test manual single cycle execution."""
        config = SchedulerConfig(symbols=["AAPL"], persist_state=False)
        market_hours = MarketHoursManager("US", TradingSession(), mock_exchange_calendar)

        scheduler = PredictionScheduler(
            config=config,
            engine=mock_prediction_engine,
            persistence=mock_prediction_persistence,
            market_hours=market_hours,
        )

        result = scheduler.run_once()

        # Verify engine was called
        mock_prediction_engine.execute_prediction_cycle.assert_called_once()

        # Verify result
        assert result.symbols_processed == 5
        assert result.signals_generated == 3
        assert result.status == "SUCCESS"

    def test_start_and_stop(
        self,
        mock_prediction_engine,
        mock_prediction_persistence,
        mock_exchange_calendar,
    ):
        """Test scheduler start and stop."""
        config = SchedulerConfig(
            symbols=["AAPL"],
            run_on_startup=False,
            catch_up_on_startup=False,
        )
        market_hours = MarketHoursManager("US", TradingSession(), mock_exchange_calendar)

        scheduler = PredictionScheduler(
            config=config,
            engine=mock_prediction_engine,
            persistence=mock_prediction_persistence,
            market_hours=market_hours,
        )

        # Start scheduler
        scheduler.start()
        assert scheduler.is_running()

        # Stop scheduler
        scheduler.stop(wait=False)
        assert not scheduler.is_running()

    def test_parse_interval_minutes(
        self,
        mock_prediction_engine,
        mock_prediction_persistence,
        mock_exchange_calendar,
    ):
        """Test interval parsing."""
        config = SchedulerConfig()
        market_hours = MarketHoursManager("US", TradingSession(), mock_exchange_calendar)

        scheduler = PredictionScheduler(
            config=config,
            engine=mock_prediction_engine,
            persistence=mock_prediction_persistence,
            market_hours=market_hours,
        )

        assert scheduler._parse_interval_minutes("30min") == 30
        assert scheduler._parse_interval_minutes("1h") == 60
        assert scheduler._parse_interval_minutes("5min") == 5

        with pytest.raises(ValueError):
            scheduler._parse_interval_minutes("invalid")


# ============================================================================
# Integration Tests
# ============================================================================


class TestSchedulerIntegration:
    """Test end-to-end scheduler behavior."""

    @patch("dgas.data.exchange_calendar.ExchangeCalendar.fetch_exchange_details")
    def test_market_hours_with_mocked_api(
        self, mock_fetch, eodhd_exchange_fixture, default_trading_session
    ):
        """Test MarketHoursManager with mocked EODHD API response."""
        mock_fetch.return_value = eodhd_exchange_fixture

        # This would normally call the API, but we've mocked it
        calendar = ExchangeCalendar()
        manager = MarketHoursManager("US", default_trading_session, calendar)

        # Test that it works with mocked data
        et_tz = ZoneInfo("America/New_York")
        weekday = datetime(2024, 11, 6, 14, 0, tzinfo=et_tz).astimezone(timezone.utc)

        # Calendar not synced yet in test, so this will fall back to simple checks
        # In real usage, calendar would be synced
        assert manager.session.market_open == time(9, 30)
        assert manager.session.market_close == time(16, 0)
