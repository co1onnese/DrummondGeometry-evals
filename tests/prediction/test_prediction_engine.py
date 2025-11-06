"""
Unit tests for PredictionEngine orchestration layer.

Tests the complete prediction cycle including:
- Market data refresh
- Indicator calculation
- Signal generation
- Persistence operations
- Error handling
- Performance metrics
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest

from dgas.calculations.multi_timeframe import TimeframeType
from dgas.data.models import IntervalData
from dgas.prediction.engine import (
    GeneratedSignal,
    PredictionEngine,
    PredictionRunResult,
    SignalGenerator,
    SignalType,
)
from dgas.calculations.states import TrendDirection


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_settings():
    """Mock Settings instance."""
    settings = Mock()
    settings.db_host = "localhost"
    settings.db_port = 5432
    settings.db_name = "test_db"
    settings.db_user = "test_user"
    settings.db_password = "test_pass"
    settings.eodhd_api_token = "test_token"
    return settings


@pytest.fixture
def mock_persistence():
    """Mock PredictionPersistence instance."""
    persistence = Mock()
    persistence.save_prediction_run = Mock(return_value=1)  # Returns run_id
    persistence.save_generated_signals = Mock(return_value=2)  # Returns signal count
    persistence.__enter__ = Mock(return_value=persistence)
    persistence.__exit__ = Mock(return_value=False)
    return persistence


@pytest.fixture
def sample_interval_data() -> List[IntervalData]:
    """Create sample market data for testing."""
    base_time = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

    data = []
    for i in range(100):  # 100 bars
        # Calculate timestamp and convert to Unix timestamp (int)
        timestamp_dt = base_time.replace(hour=10 + i // 12, minute=(i % 12) * 5)
        timestamp = int(timestamp_dt.timestamp())

        data.append(
            IntervalData(
                symbol="AAPL",
                interval="5m",
                timestamp=timestamp,  # Unix timestamp
                open=Decimal("180.00") + Decimal(str(i * 0.1)),
                high=Decimal("180.50") + Decimal(str(i * 0.1)),
                low=Decimal("179.50") + Decimal(str(i * 0.1)),
                close=Decimal("180.00") + Decimal(str(i * 0.1)),
                volume=1000000 + i * 1000,
            )
        )
    return data


@pytest.fixture
def sample_generated_signal() -> GeneratedSignal:
    """Create sample generated signal."""
    return GeneratedSignal(
        symbol="AAPL",
        signal_timestamp=datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc),
        signal_type=SignalType.LONG,
        entry_price=Decimal("182.50"),
        stop_loss=Decimal("181.00"),
        target_price=Decimal("185.00"),
        confidence=0.78,
        signal_strength=0.82,
        timeframe_alignment=0.75,
        risk_reward_ratio=1.67,
        htf_trend=TrendDirection.UP,
        trading_tf_state="TREND_UP",
        confluence_zones_count=3,
        pattern_context={
            "patterns": ["SUPPORT_CONFLUENCE"],
            "htf_phase": "EXPANSION",
            "ltf_confirmation": True,
        },
        htf_timeframe="4h",
        trading_timeframe="5m",
    )


# ============================================================================
# PredictionEngine Initialization Tests
# ============================================================================


class TestPredictionEngineInit:
    """Test PredictionEngine initialization."""

    def test_init_with_defaults(self, mock_settings, mock_persistence):
        """Test initialization with default parameters."""
        engine = PredictionEngine(
            settings=mock_settings,
            persistence=mock_persistence,
        )

        assert engine.settings == mock_settings
        assert engine.persistence == mock_persistence
        assert engine.lookback_bars == 200  # Default value
        assert engine.signal_generator is not None
        assert isinstance(engine.signal_generator, SignalGenerator)

    def test_init_with_custom_params(self, mock_settings, mock_persistence):
        """Test initialization with custom parameters."""
        engine = PredictionEngine(
            settings=mock_settings,
            persistence=mock_persistence,
            lookback_bars=300,
        )

        assert engine.lookback_bars == 300


# ============================================================================
# Data Loading Tests
# ============================================================================


class TestDataLoading:
    """Test market data loading from database."""

    @patch("dgas.db.get_connection")
    def test_load_market_data_success(
        self, mock_get_conn, mock_settings, mock_persistence, sample_interval_data
    ):
        """Test successful market data loading."""
        # Setup mock connection
        mock_cursor = Mock()
        # First call to fetchone() returns symbol_id (for symbol lookup)
        # Second call to fetchall() returns the interval data (6 fields as per SQL query)
        mock_cursor.fetchone.return_value = (1,)  # symbol_id = 1
        mock_cursor.fetchall.return_value = [
            (
                int(row.timestamp.timestamp()),  # Convert datetime back to int timestamp
                row.open,
                row.high,
                row.low,
                row.close,
                row.volume,
            )
            for row in sample_interval_data
        ]

        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_get_conn.return_value = mock_conn

        # Execute
        engine = PredictionEngine(settings=mock_settings, persistence=mock_persistence)
        result = engine._load_market_data("AAPL", "5m")

        # Verify
        assert len(result) == 100
        assert all(isinstance(row, IntervalData) for row in result)
        assert result[0].symbol == "AAPL"
        assert result[0].interval == "5m"

    @patch("dgas.db.get_connection")
    def test_load_market_data_empty(self, mock_get_conn, mock_settings, mock_persistence):
        """Test loading market data when symbol doesn't exist."""
        # Setup mock connection - symbol not found
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None  # Symbol not found

        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_get_conn.return_value = mock_conn

        # Execute - should raise ValueError
        engine = PredictionEngine(settings=mock_settings, persistence=mock_persistence)

        with pytest.raises(ValueError, match="Symbol UNKNOWN not found"):
            engine._load_market_data("UNKNOWN", "5m")


# ============================================================================
# Data Refresh Tests
# ============================================================================


class TestDataRefresh:
    """Test incremental market data refresh."""

    @patch("dgas.data.ingestion.incremental_update_intraday")
    def test_refresh_market_data_success(
        self, mock_incremental, mock_settings, mock_persistence
    ):
        """Test successful data refresh for all symbols."""
        # Setup mock to return successful updates
        mock_summary = Mock()
        mock_summary.stored = 10
        mock_summary.fetched = 10
        mock_incremental.return_value = mock_summary

        # Execute
        engine = PredictionEngine(settings=mock_settings, persistence=mock_persistence)
        errors = []
        updated = engine._refresh_market_data(
            symbols=["AAPL", "MSFT", "GOOGL"],
            interval="5m",
            errors=errors,
        )

        # Verify
        assert len(updated) == 3
        assert "AAPL" in updated
        assert "MSFT" in updated
        assert "GOOGL" in updated
        assert len(errors) == 0
        assert mock_incremental.call_count == 3

    @patch("dgas.data.ingestion.incremental_update_intraday")
    def test_refresh_market_data_partial_failure(
        self, mock_incremental, mock_settings, mock_persistence
    ):
        """Test data refresh with some symbols failing."""
        # Setup mock to fail on second symbol
        def side_effect(symbol, **kwargs):
            if symbol == "MSFT":
                raise ValueError("API rate limit exceeded")
            mock_summary = Mock()
            mock_summary.stored = 5
            mock_summary.fetched = 5
            return mock_summary

        mock_incremental.side_effect = side_effect

        # Execute
        engine = PredictionEngine(settings=mock_settings, persistence=mock_persistence)
        errors = []
        updated = engine._refresh_market_data(
            symbols=["AAPL", "MSFT", "GOOGL"],
            interval="5m",
            errors=errors,
        )

        # Verify
        assert len(updated) == 2  # Only AAPL and GOOGL succeeded
        assert "AAPL" in updated
        assert "GOOGL" in updated
        assert "MSFT" not in updated
        assert len(errors) == 1
        assert "MSFT" in errors[0]
        assert "API rate limit" in errors[0]

    @patch("dgas.data.ingestion.incremental_update_intraday")
    def test_refresh_market_data_no_new_data(
        self, mock_incremental, mock_settings, mock_persistence
    ):
        """Test data refresh when no new data is available."""
        # Setup mock to return zero updates
        mock_summary = Mock()
        mock_summary.stored = 0
        mock_summary.fetched = 0
        mock_incremental.return_value = mock_summary

        # Execute
        engine = PredictionEngine(settings=mock_settings, persistence=mock_persistence)
        errors = []
        updated = engine._refresh_market_data(
            symbols=["AAPL"],
            interval="5m",
            errors=errors,
        )

        # Verify - symbol not in updated list since no data was stored/fetched
        assert len(updated) == 0
        assert len(errors) == 0


# ============================================================================
# Indicator Calculation Tests
# ============================================================================


class TestIndicatorCalculation:
    """Test indicator calculation for timeframe data."""

    def test_calculate_timeframe_data_structure(
        self, mock_settings, mock_persistence, sample_interval_data
    ):
        """Test that calculated timeframe data has correct structure."""
        engine = PredictionEngine(settings=mock_settings, persistence=mock_persistence)

        # Execute
        result = engine._calculate_timeframe_data(
            intervals=sample_interval_data,
            timeframe="HTF",
            classification=TimeframeType.HIGHER,
        )

        # Verify structure
        assert result.classification == TimeframeType.HIGHER
        assert result.pldot_series is not None
        assert result.envelope_series is not None
        assert result.state_series is not None
        assert result.pattern_events is not None
        assert len(result.pldot_series) > 0
        assert len(result.envelope_series) > 0
        assert len(result.state_series) > 0

    def test_calculate_timeframe_data_indicators_valid(
        self, mock_settings, mock_persistence, sample_interval_data
    ):
        """Test that calculated indicators have valid values."""
        engine = PredictionEngine(settings=mock_settings, persistence=mock_persistence)

        # Execute
        result = engine._calculate_timeframe_data(
            intervals=sample_interval_data,
            timeframe="Trading",
            classification=TimeframeType.TRADING,
        )

        # Verify PLdot values are valid
        for pldot in result.pldot_series:
            assert pldot.value > Decimal(0)
            assert pldot.projected_value > Decimal(0)

        # Verify envelope values exist
        assert len(result.envelope_series) > 0


# ============================================================================
# Signal Conversion Tests
# ============================================================================


class TestSignalConversion:
    """Test signal conversion to dictionary format."""

    def test_signal_to_dict_complete(
        self, mock_settings, mock_persistence, sample_generated_signal
    ):
        """Test conversion of complete signal to dict."""
        engine = PredictionEngine(settings=mock_settings, persistence=mock_persistence)

        result = engine._signal_to_dict(sample_generated_signal)

        # Verify all required fields present
        assert result["symbol"] == "AAPL"
        assert result["signal_type"] == "LONG"
        assert result["entry_price"] == Decimal("182.50")
        assert result["stop_loss"] == Decimal("181.00")
        assert result["target_price"] == Decimal("185.00")
        assert result["confidence"] == 0.78
        assert result["signal_strength"] == 0.82
        assert result["timeframe_alignment"] == 0.75
        assert result["risk_reward_ratio"] == 1.67
        assert result["htf_trend"] == "up"  # TrendDirection.value is lowercase
        assert result["trading_tf_state"] == "TREND_UP"
        assert result["confluence_zones_count"] == 3
        assert isinstance(result["pattern_context"], dict)

    def test_signal_to_dict_timestamp_format(
        self, mock_settings, mock_persistence, sample_generated_signal
    ):
        """Test that timestamp is properly formatted."""
        engine = PredictionEngine(settings=mock_settings, persistence=mock_persistence)

        result = engine._signal_to_dict(sample_generated_signal)

        # Verify timestamp is datetime object
        assert isinstance(result["signal_timestamp"], datetime)
        assert result["signal_timestamp"].tzinfo is not None


# ============================================================================
# Integration Tests (Simplified)
# ============================================================================


class TestPredictionCycleIntegration:
    """Test prediction cycle with mocked dependencies."""

    @patch("dgas.data.ingestion.incremental_update_intraday")
    def test_execute_prediction_cycle_with_errors(
        self, mock_incremental, mock_settings, mock_persistence
    ):
        """Test prediction cycle handles errors gracefully."""
        # Mock data refresh to fail
        mock_incremental.side_effect = ValueError("API error")

        # Execute
        engine = PredictionEngine(settings=mock_settings, persistence=mock_persistence)
        result = engine.execute_prediction_cycle(
            symbols=["AAPL"],
            interval="5m",
            timeframes=["HTF", "Trading"],
            persist_results=True,
        )

        # Verify error handling
        assert result.status in ["PARTIAL", "FAILED"]
        assert result.symbols_processed == 0
        assert result.signals_generated == 0
        assert len(result.errors) > 0
