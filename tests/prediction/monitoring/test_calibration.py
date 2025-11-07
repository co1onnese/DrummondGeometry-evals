"""Unit tests for signal calibration."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from dgas.data.models import IntervalData
from dgas.prediction.monitoring.calibration import (
    SignalOutcome,
    CalibrationReport,
    CalibrationEngine,
)


class TestSignalOutcome:
    """Tests for SignalOutcome dataclass."""

    def test_create_valid_outcome(self):
        """Test creating valid signal outcome."""
        outcome = SignalOutcome(
            signal_id=123,
            evaluation_timestamp=datetime.now(timezone.utc),
            actual_high=Decimal("105.50"),
            actual_low=Decimal("95.25"),
            close_price=Decimal("102.00"),
            hit_target=True,
            hit_stop=False,
            outcome="WIN",
            pnl_pct=5.5,
            evaluation_window_hours=24,
            signal_type="LONG",
        )

        assert outcome.signal_id == 123
        assert outcome.outcome == "WIN"
        assert outcome.pnl_pct == 5.5

    def test_immutable(self):
        """Test that SignalOutcome is immutable."""
        outcome = SignalOutcome(
            signal_id=123,
            evaluation_timestamp=datetime.now(timezone.utc),
            actual_high=Decimal("105.50"),
            actual_low=Decimal("95.25"),
            close_price=Decimal("102.00"),
            hit_target=True,
            hit_stop=False,
            outcome="WIN",
            pnl_pct=5.5,
            evaluation_window_hours=24,
            signal_type="LONG",
        )

        with pytest.raises(AttributeError):
            outcome.outcome = "LOSS"


class TestCalibrationEngine:
    """Tests for CalibrationEngine class."""

    @pytest.fixture
    def mock_persistence(self):
        """Create mock PredictionPersistence."""
        return MagicMock()

    @pytest.fixture
    def engine(self, mock_persistence):
        """Create CalibrationEngine with mock persistence."""
        return CalibrationEngine(
            persistence=mock_persistence,
            evaluation_window_hours=24,
        )

    def test_init(self, mock_persistence):
        """Test CalibrationEngine initialization."""
        engine = CalibrationEngine(
            persistence=mock_persistence,
            evaluation_window_hours=48,
        )
        assert engine.persistence is mock_persistence
        assert engine.evaluation_window_hours == 48

    def _create_price_bars(
        self,
        start_time: datetime,
        count: int,
        high: float,
        low: float,
        close: float,
    ) -> list[IntervalData]:
        """Helper to create test price bars."""
        bars = []
        for i in range(count):
            timestamp = start_time + timedelta(minutes=5 * i)
            bars.append(
                IntervalData(
                    symbol="AAPL",
                    exchange="US",
                    timestamp=timestamp.timestamp(),  # Convert to unix timestamp
                    interval="5min",
                    open=Decimal(str(close)),
                    high=Decimal(str(high)),
                    low=Decimal(str(low)),
                    close=Decimal(str(close)),
                    volume=100000,
                )
            )
        return bars

    def test_evaluate_signal_long_target_hit(self, engine):
        """Test evaluate_signal() for LONG signal that hits target."""
        signal = {
            "signal_id": 1,
            "signal_type": "LONG",
            "entry_price": Decimal("100.00"),
            "stop_loss": Decimal("95.00"),
            "target_price": Decimal("105.00"),
            "signal_timestamp": datetime.now(timezone.utc),
        }

        # Price moves up and hits target
        prices = self._create_price_bars(
            start_time=signal["signal_timestamp"] + timedelta(minutes=5),
            count=10,
            high=106.0,  # Exceeds target
            low=99.0,  # Above stop
            close=105.5,
        )

        outcome = engine.evaluate_signal(signal, prices)

        assert outcome.signal_id == 1
        assert outcome.outcome == "WIN"
        assert outcome.hit_target is True
        assert outcome.hit_stop is False
        assert outcome.pnl_pct == 5.0  # (105 - 100) / 100 * 100

    def test_evaluate_signal_long_stop_hit(self, engine):
        """Test evaluate_signal() for LONG signal that hits stop."""
        signal = {
            "signal_id": 2,
            "signal_type": "LONG",
            "entry_price": Decimal("100.00"),
            "stop_loss": Decimal("95.00"),
            "target_price": Decimal("105.00"),
            "signal_timestamp": datetime.now(timezone.utc),
        }

        # Price moves down and hits stop
        prices = self._create_price_bars(
            start_time=signal["signal_timestamp"] + timedelta(minutes=5),
            count=10,
            high=100.5,  # Below target
            low=94.0,  # Hits stop
            close=96.0,
        )

        outcome = engine.evaluate_signal(signal, prices)

        assert outcome.signal_id == 2
        assert outcome.outcome == "LOSS"
        assert outcome.hit_target is False
        assert outcome.hit_stop is True
        assert outcome.pnl_pct == -5.0  # (95 - 100) / 100 * 100

    def test_evaluate_signal_long_both_hit_stop_first(self, engine):
        """Test LONG signal where stop is hit before target."""
        signal = {
            "signal_id": 3,
            "signal_type": "LONG",
            "entry_price": Decimal("100.00"),
            "stop_loss": Decimal("95.00"),
            "target_price": Decimal("105.00"),
            "signal_timestamp": datetime.now(timezone.utc),
        }

        # Create bars where stop is hit first, then price recovers
        start_time = signal["signal_timestamp"] + timedelta(minutes=5)
        bars = [
            # Bar 1: hits stop
            IntervalData(
                symbol="AAPL",
                exchange="US",
                timestamp=start_time.timestamp(),  # Convert to unix timestamp
                interval="5min",
                open=Decimal("99.0"),
                high=Decimal("99.5"),
                low=Decimal("94.0"),  # Hits stop
                close=Decimal("96.0"),
                volume=100000,
            ),
            # Bar 2: price recovers and hits target
            IntervalData(
                symbol="AAPL",
                exchange="US",
                timestamp=(start_time + timedelta(minutes=5)).timestamp(),  # Convert to unix timestamp
                interval="5min",
                open=Decimal("96.0"),
                high=Decimal("106.0"),  # Hits target
                low=Decimal("95.5"),
                close=Decimal("105.5"),
                volume=100000,
            ),
        ]

        outcome = engine.evaluate_signal(signal, bars)

        assert outcome.outcome == "LOSS"  # Stop hit first
        assert outcome.hit_target is True
        assert outcome.hit_stop is True
        assert outcome.pnl_pct == -5.0

    def test_evaluate_signal_long_both_hit_target_first(self, engine):
        """Test LONG signal where target is hit before stop."""
        signal = {
            "signal_id": 4,
            "signal_type": "LONG",
            "entry_price": Decimal("100.00"),
            "stop_loss": Decimal("95.00"),
            "target_price": Decimal("105.00"),
            "signal_timestamp": datetime.now(timezone.utc),
        }

        # Create bars where target is hit first
        start_time = signal["signal_timestamp"] + timedelta(minutes=5)
        bars = [
            # Bar 1: hits target
            IntervalData(
                symbol="AAPL",
                exchange="US",
                timestamp=start_time.timestamp(),  # Convert to unix timestamp
                interval="5min",
                open=Decimal("100.0"),
                high=Decimal("106.0"),  # Hits target
                low=Decimal("99.5"),
                close=Decimal("105.5"),
                volume=100000,
            ),
            # Bar 2: price drops and hits stop
            IntervalData(
                symbol="AAPL",
                exchange="US",
                timestamp=(start_time + timedelta(minutes=5)).timestamp(),  # Convert to unix timestamp
                interval="5min",
                open=Decimal("105.0"),
                high=Decimal("105.5"),
                low=Decimal("94.0"),  # Hits stop
                close=Decimal("96.0"),
                volume=100000,
            ),
        ]

        outcome = engine.evaluate_signal(signal, bars)

        assert outcome.outcome == "WIN"  # Target hit first
        assert outcome.hit_target is True
        assert outcome.hit_stop is True
        assert outcome.pnl_pct == 5.0

    def test_evaluate_signal_long_neutral(self, engine):
        """Test LONG signal where neither target nor stop is hit."""
        signal = {
            "signal_id": 5,
            "signal_type": "LONG",
            "entry_price": Decimal("100.00"),
            "stop_loss": Decimal("95.00"),
            "target_price": Decimal("105.00"),
            "signal_timestamp": datetime.now(timezone.utc),
        }

        # Price stays in range
        prices = self._create_price_bars(
            start_time=signal["signal_timestamp"] + timedelta(minutes=5),
            count=10,
            high=103.0,  # Below target
            low=97.0,  # Above stop
            close=102.0,
        )

        outcome = engine.evaluate_signal(signal, prices)

        assert outcome.outcome == "NEUTRAL"
        assert outcome.hit_target is False
        assert outcome.hit_stop is False
        assert outcome.pnl_pct == 2.0  # (102 - 100) / 100 * 100

    def test_evaluate_signal_short_target_hit(self, engine):
        """Test evaluate_signal() for SHORT signal that hits target."""
        signal = {
            "signal_id": 6,
            "signal_type": "SHORT",
            "entry_price": Decimal("100.00"),
            "stop_loss": Decimal("105.00"),
            "target_price": Decimal("95.00"),
            "signal_timestamp": datetime.now(timezone.utc),
        }

        # Price moves down and hits target
        prices = self._create_price_bars(
            start_time=signal["signal_timestamp"] + timedelta(minutes=5),
            count=10,
            high=101.0,  # Below stop
            low=94.0,  # Hits target
            close=95.5,
        )

        outcome = engine.evaluate_signal(signal, prices)

        assert outcome.outcome == "WIN"
        assert outcome.hit_target is True
        assert outcome.hit_stop is False
        assert outcome.pnl_pct == 5.0  # (100 - 95) / 100 * 100

    def test_evaluate_signal_short_stop_hit(self, engine):
        """Test evaluate_signal() for SHORT signal that hits stop."""
        signal = {
            "signal_id": 7,
            "signal_type": "SHORT",
            "entry_price": Decimal("100.00"),
            "stop_loss": Decimal("105.00"),
            "target_price": Decimal("95.00"),
            "signal_timestamp": datetime.now(timezone.utc),
        }

        # Price moves up and hits stop
        prices = self._create_price_bars(
            start_time=signal["signal_timestamp"] + timedelta(minutes=5),
            count=10,
            high=106.0,  # Hits stop
            low=99.5,  # Above target
            close=104.0,
        )

        outcome = engine.evaluate_signal(signal, prices)

        assert outcome.outcome == "LOSS"
        assert outcome.hit_target is False
        assert outcome.hit_stop is True
        assert outcome.pnl_pct == -5.0  # (100 - 105) / 100 * 100

    def test_evaluate_signal_short_neutral(self, engine):
        """Test SHORT signal where neither target nor stop is hit."""
        signal = {
            "signal_id": 8,
            "signal_type": "SHORT",
            "entry_price": Decimal("100.00"),
            "stop_loss": Decimal("105.00"),
            "target_price": Decimal("95.00"),
            "signal_timestamp": datetime.now(timezone.utc),
        }

        # Price stays in range
        prices = self._create_price_bars(
            start_time=signal["signal_timestamp"] + timedelta(minutes=5),
            count=10,
            high=103.0,  # Below stop
            low=97.0,  # Above target
            close=98.0,
        )

        outcome = engine.evaluate_signal(signal, prices)

        assert outcome.outcome == "NEUTRAL"
        assert outcome.hit_target is False
        assert outcome.hit_stop is False
        assert outcome.pnl_pct == 2.0  # (100 - 98) / 100 * 100

    def test_evaluate_signal_pending_no_data(self, engine):
        """Test evaluate_signal() with insufficient price data."""
        signal = {
            "signal_id": 9,
            "signal_type": "LONG",
            "entry_price": Decimal("100.00"),
            "stop_loss": Decimal("95.00"),
            "target_price": Decimal("105.00"),
            "signal_timestamp": datetime.now(timezone.utc),
        }

        # No price data
        prices = []

        outcome = engine.evaluate_signal(signal, prices)

        assert outcome.outcome == "PENDING"
        assert outcome.hit_target is False
        assert outcome.hit_stop is False
        assert outcome.pnl_pct == 0.0

    def test_evaluate_signal_invalid_type(self, engine):
        """Test evaluate_signal() raises error for unsupported signal type."""
        signal = {
            "signal_id": 10,
            "signal_type": "INVALID",
            "entry_price": Decimal("100.00"),
            "stop_loss": Decimal("95.00"),
            "target_price": Decimal("105.00"),
            "signal_timestamp": datetime.now(timezone.utc),
        }

        prices = self._create_price_bars(
            start_time=signal["signal_timestamp"] + timedelta(minutes=5),
            count=5,
            high=103.0,
            low=97.0,
            close=102.0,
        )

        with pytest.raises(ValueError, match="Unsupported signal type"):
            engine.evaluate_signal(signal, prices)

    def test_batch_evaluate(self, engine, mock_persistence):
        """Test batch_evaluate() processes pending signals."""
        now = datetime.now(timezone.utc)

        # Mock signals pending evaluation (old enough)
        mock_signals = [
            {
                "signal_id": 1,
                "symbol": "AAPL",
                "signal_type": "LONG",
                "entry_price": Decimal("100.00"),
                "stop_loss": Decimal("95.00"),
                "target_price": Decimal("105.00"),
                "signal_timestamp": now - timedelta(hours=30),  # Old enough
                "outcome": None,
                "pnl_pct": None,
            },
            {
                "signal_id": 2,
                "symbol": "MSFT",
                "signal_type": "SHORT",
                "entry_price": Decimal("200.00"),
                "stop_loss": Decimal("210.00"),
                "target_price": Decimal("190.00"),
                "signal_timestamp": now - timedelta(hours=10),  # Too recent
                "outcome": None,
                "pnl_pct": None,
            },
        ]

        mock_persistence.get_recent_signals.return_value = mock_signals

        # Mock price fetching to return empty (will trigger PENDING)
        with patch.object(engine, "_fetch_actual_prices", return_value=[]):
            outcomes = engine.batch_evaluate(lookback_hours=48)

        # Should only evaluate signal 1 (signal 2 is too recent)
        assert len(outcomes) == 1
        assert outcomes[0].signal_id == 1
        assert outcomes[0].outcome == "PENDING"  # No price data

        # Verify update was called
        assert mock_persistence.update_signal_outcome.call_count == 1

    def test_batch_evaluate_skips_already_evaluated(self, engine, mock_persistence):
        """Test batch_evaluate() skips signals with outcomes."""
        now = datetime.now(timezone.utc)

        # Mock signals including already evaluated ones
        mock_signals = [
            {
                "signal_id": 1,
                "symbol": "AAPL",
                "signal_type": "LONG",
                "entry_price": Decimal("100.00"),
                "stop_loss": Decimal("95.00"),
                "target_price": Decimal("105.00"),
                "signal_timestamp": now - timedelta(hours=30),
                "outcome": "WIN",  # Already evaluated
                "pnl_pct": 5.0,
            },
            {
                "signal_id": 2,
                "symbol": "MSFT",
                "signal_type": "SHORT",
                "entry_price": Decimal("200.00"),
                "stop_loss": Decimal("210.00"),
                "target_price": Decimal("190.00"),
                "signal_timestamp": now - timedelta(hours=30),
                "outcome": None,  # Pending
                "pnl_pct": None,
            },
        ]

        mock_persistence.get_recent_signals.return_value = mock_signals

        with patch.object(engine, "_fetch_actual_prices", return_value=[]):
            outcomes = engine.batch_evaluate(lookback_hours=48)

        # Should only evaluate signal 2
        assert len(outcomes) == 1
        assert outcomes[0].signal_id == 2

    def test_get_calibration_report_with_data(self, engine, mock_persistence):
        """Test get_calibration_report() generates correct statistics."""
        now = datetime.now(timezone.utc)

        # Mock evaluated signals with various outcomes
        mock_signals = [
            # Wins
            {
                "signal_id": 1,
                "symbol": "AAPL",
                "signal_type": "LONG",
                "confidence": 0.75,
                "signal_timestamp": now - timedelta(days=1),
                "outcome": "WIN",
                "pnl_pct": 5.0,
            },
            {
                "signal_id": 2,
                "symbol": "MSFT",
                "signal_type": "LONG",
                "confidence": 0.85,
                "signal_timestamp": now - timedelta(days=2),
                "outcome": "WIN",
                "pnl_pct": 3.0,
            },
            # Losses
            {
                "signal_id": 3,
                "symbol": "GOOGL",
                "signal_type": "SHORT",
                "confidence": 0.65,
                "signal_timestamp": now - timedelta(days=3),
                "outcome": "LOSS",
                "pnl_pct": -2.5,
            },
            # Neutral
            {
                "signal_id": 4,
                "symbol": "TSLA",
                "signal_type": "LONG",
                "confidence": 0.70,
                "signal_timestamp": now - timedelta(days=4),
                "outcome": "NEUTRAL",
                "pnl_pct": 0.5,
            },
        ]

        mock_persistence.get_recent_signals.return_value = mock_signals

        report = engine.get_calibration_report()

        assert report.total_signals == 4
        assert report.evaluated_signals == 4
        assert report.win_rate == 0.5  # 2 wins out of 4
        assert report.avg_pnl_pct == 1.5  # (5.0 + 3.0 - 2.5 + 0.5) / 4
        assert report.target_hit_rate == 0.5
        assert report.stop_hit_rate == 0.25  # 1 loss

        # Check confidence buckets
        assert "0.6-0.7" in report.by_confidence
        assert "0.7-0.8" in report.by_confidence
        assert "0.8-0.9" in report.by_confidence

        # Check signal type grouping
        assert "LONG" in report.by_signal_type
        assert "SHORT" in report.by_signal_type

    def test_get_calibration_report_empty_data(self, engine, mock_persistence):
        """Test get_calibration_report() with no data."""
        mock_persistence.get_recent_signals.return_value = []

        report = engine.get_calibration_report()

        assert report.total_signals == 0
        assert report.evaluated_signals == 0
        assert report.win_rate == 0.0
        assert report.by_confidence == {}
        assert report.by_signal_type == {}

    def test_group_by_confidence(self, engine):
        """Test _group_by_confidence() groups signals correctly."""
        signals = [
            {"signal_id": 1, "confidence": 0.65, "outcome": "WIN", "pnl_pct": 5.0},
            {"signal_id": 2, "confidence": 0.75, "outcome": "WIN", "pnl_pct": 3.0},
            {"signal_id": 3, "confidence": 0.75, "outcome": "LOSS", "pnl_pct": -2.0},
            {"signal_id": 4, "confidence": 0.85, "outcome": "WIN", "pnl_pct": 4.0},
            {"signal_id": 5, "confidence": 0.95, "outcome": "WIN", "pnl_pct": 6.0},
        ]

        result = engine._group_by_confidence(signals)

        # Check 0.6-0.7 bucket
        assert result["0.6-0.7"]["count"] == 1
        assert result["0.6-0.7"]["win_rate"] == 1.0

        # Check 0.7-0.8 bucket
        assert result["0.7-0.8"]["count"] == 2
        assert result["0.7-0.8"]["win_rate"] == 0.5  # 1 win, 1 loss
        assert result["0.7-0.8"]["avg_pnl"] == 0.5  # (3.0 - 2.0) / 2

        # Check 0.8-0.9 bucket
        assert result["0.8-0.9"]["count"] == 1
        assert result["0.8-0.9"]["win_rate"] == 1.0

        # Check 0.9-1.0 bucket
        assert result["0.9-1.0"]["count"] == 1
        assert result["0.9-1.0"]["win_rate"] == 1.0

    def test_group_by_signal_type(self, engine):
        """Test _group_by_signal_type() groups signals correctly."""
        signals = [
            {"signal_id": 1, "signal_type": "LONG", "outcome": "WIN", "pnl_pct": 5.0},
            {"signal_id": 2, "signal_type": "LONG", "outcome": "LOSS", "pnl_pct": -2.0},
            {"signal_id": 3, "signal_type": "SHORT", "outcome": "WIN", "pnl_pct": 3.0},
            {"signal_id": 4, "signal_type": "SHORT", "outcome": "WIN", "pnl_pct": 4.0},
        ]

        result = engine._group_by_signal_type(signals)

        # Check LONG
        assert result["LONG"]["count"] == 2
        assert result["LONG"]["win_rate"] == 0.5
        assert result["LONG"]["avg_pnl"] == 1.5  # (5.0 - 2.0) / 2

        # Check SHORT
        assert result["SHORT"]["count"] == 2
        assert result["SHORT"]["win_rate"] == 1.0
        assert result["SHORT"]["avg_pnl"] == 3.5  # (3.0 + 4.0) / 2

    def test_fetch_actual_prices_no_data_source(self, engine):
        """Test _fetch_actual_prices() with no data source configured."""
        prices = engine._fetch_actual_prices(
            symbol="AAPL",
            start_time=datetime.now(timezone.utc),
            hours=24,
        )

        assert prices == []

    def test_fetch_actual_prices_not_implemented(self, engine):
        """Test _fetch_actual_prices() raises NotImplementedError with data source."""
        engine.data_source = MagicMock()

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            engine._fetch_actual_prices(
                symbol="AAPL",
                start_time=datetime.now(timezone.utc),
                hours=24,
            )
