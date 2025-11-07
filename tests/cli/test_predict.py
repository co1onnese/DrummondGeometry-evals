"""
Unit tests for predict CLI command.
"""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, Mock, patch

import pytest
from rich.console import Console

from dgas.calculations.states import TrendDirection
from dgas.cli.predict import (
    _calc_pct,
    _display_detailed,
    _display_json,
    _display_summary,
    _get_symbols,
    run_predict_command,
    setup_predict_parser,
)
from dgas.prediction.engine import GeneratedSignal, SignalType


@pytest.fixture
def mock_settings():
    """Create mock Settings object."""
    settings = Mock()
    settings.scheduler_symbols = ["AAPL", "MSFT", "GOOGL"]
    settings.default_watchlist = ["AAPL", "MSFT", "GOOGL"]
    return settings


@pytest.fixture
def mock_result():
    """Create mock PredictionRunResult."""
    result = Mock()
    result.symbols_processed = 3
    result.signals_generated = 2
    result.execution_time_ms = 1500
    result.data_fetch_ms = 500
    result.indicator_calc_ms = 600
    result.signal_generation_ms = 400
    result.errors = []
    result.signals = []
    return result


@pytest.fixture
def mock_signals():
    """Create mock trading signals."""
    return [
        GeneratedSignal(
            symbol="AAPL",
            signal_timestamp=datetime(2025, 1, 6, 10, 0, 0),
            signal_type=SignalType.LONG,
            entry_price=Decimal("175.50"),
            stop_loss=Decimal("172.00"),
            target_price=Decimal("180.00"),
            confidence=0.85,
            signal_strength=0.90,
            timeframe_alignment=0.85,
            risk_reward_ratio=2.5,
            htf_trend=TrendDirection.UP,
            trading_tf_state="bullish",
            confluence_zones_count=2,
            pattern_context={"indicator": "drummond"},
            htf_timeframe="4h",
            trading_timeframe="1h",
        ),
        GeneratedSignal(
            symbol="MSFT",
            signal_timestamp=datetime(2025, 1, 6, 10, 0, 0),
            signal_type=SignalType.SHORT,
            entry_price=Decimal("380.00"),
            stop_loss=Decimal("383.00"),
            target_price=Decimal("375.00"),
            confidence=0.72,
            signal_strength=0.75,
            timeframe_alignment=0.70,
            risk_reward_ratio=1.67,
            htf_trend=TrendDirection.DOWN,
            trading_tf_state="bearish",
            confluence_zones_count=1,
            pattern_context={"indicator": "drummond"},
            htf_timeframe="4h",
            trading_timeframe="1h",
        ),
    ]


class TestSetupPredictParser:
    """Test setup_predict_parser function."""

    def test_parser_creation(self):
        """Test that parser is created with correct arguments."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        predict_parser = setup_predict_parser(subparsers)

        assert predict_parser is not None

        # Test parsing with symbols
        args = parser.parse_args(["predict", "AAPL", "MSFT"])
        assert args.symbols == ["AAPL", "MSFT"]
        assert args.format == "summary"
        assert args.save is False
        assert args.notify is False

    def test_parser_with_options(self):
        """Test parser with various options."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_predict_parser(subparsers)

        args = parser.parse_args([
            "predict",
            "AAPL",
            "--format", "json",
            "--save",
            "--notify",
            "--min-confidence", "0.75",
        ])

        assert args.symbols == ["AAPL"]
        assert args.format == "json"
        assert args.save is True
        assert args.notify is True
        assert args.min_confidence == 0.75

    def test_parser_with_watchlist(self):
        """Test parser with watchlist file."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_predict_parser(subparsers)

        args = parser.parse_args([
            "predict",
            "--watchlist", "/path/to/watchlist.txt",
        ])

        assert args.watchlist == "/path/to/watchlist.txt"


class TestGetSymbols:
    """Test _get_symbols function."""

    def test_command_line_symbols(self, mock_settings):
        """Test that command line symbols take priority."""
        args = Namespace(symbols=["AAPL", "msft"], watchlist=None)
        console = Console()

        symbols = _get_symbols(args, mock_settings, console)

        assert symbols == ["AAPL", "MSFT"]

    def test_watchlist_file(self, mock_settings, tmp_path):
        """Test loading symbols from watchlist file."""
        watchlist_path = tmp_path / "watchlist.txt"
        watchlist_path.write_text("AAPL\nMSFT\nGOOGL\n")

        args = Namespace(symbols=[], watchlist=str(watchlist_path))
        console = Console()

        symbols = _get_symbols(args, mock_settings, console)

        assert symbols == ["AAPL", "MSFT", "GOOGL"]

    def test_watchlist_file_with_empty_lines(self, mock_settings, tmp_path):
        """Test loading symbols from watchlist file with empty lines."""
        watchlist_path = tmp_path / "watchlist.txt"
        watchlist_path.write_text("AAPL\n\nMSFT\n  \nGOOGL\n")

        args = Namespace(symbols=[], watchlist=str(watchlist_path))
        console = Console()

        symbols = _get_symbols(args, mock_settings, console)

        assert symbols == ["AAPL", "MSFT", "GOOGL"]

    def test_watchlist_file_not_found(self, mock_settings):
        """Test handling of missing watchlist file."""
        args = Namespace(symbols=[], watchlist="/nonexistent/watchlist.txt")
        console = Console()

        symbols = _get_symbols(args, mock_settings, console)

        # Should fall back to default watchlist
        assert symbols == ["AAPL", "MSFT", "GOOGL"]

    def test_default_watchlist(self, mock_settings):
        """Test using default watchlist from settings."""
        args = Namespace(symbols=[], watchlist=None)
        console = Console()

        symbols = _get_symbols(args, mock_settings, console)

        assert symbols == ["AAPL", "MSFT", "GOOGL"]

    def test_no_symbols(self):
        """Test when no symbols are available."""
        settings = Mock()
        settings.scheduler_symbols = None  # Explicitly set to None
        settings.default_watchlist = None
        args = Namespace(symbols=[], watchlist=None)
        console = Console()

        symbols = _get_symbols(args, settings, console)

        assert symbols == []


class TestCalcPct:
    """Test _calc_pct function."""

    def test_positive_change(self):
        """Test positive percentage change."""
        result = _calc_pct(100.0, 110.0)
        assert result == pytest.approx(0.10)

    def test_negative_change(self):
        """Test negative percentage change."""
        result = _calc_pct(100.0, 95.0)
        assert result == pytest.approx(-0.05)

    def test_no_change(self):
        """Test zero percentage change."""
        result = _calc_pct(100.0, 100.0)
        assert result == pytest.approx(0.0)


class TestDisplayFunctions:
    """Test display functions."""

    def test_display_summary(self, mock_result, mock_signals):
        """Test summary display format."""
        mock_result.signals = mock_signals
        console = Console(file=StringIO())

        _display_summary(console, mock_result, mock_signals, 0.6)

        output = console.file.getvalue()
        assert "Prediction Summary" in output
        assert "Symbols processed: 3" in output
        assert "Signals generated: 2" in output
        assert "AAPL" in output
        assert "MSFT" in output

    def test_display_summary_no_signals(self, mock_result):
        """Test summary display with no signals."""
        console = Console(file=StringIO())

        _display_summary(console, mock_result, [], 0.6)

        output = console.file.getvalue()
        assert "No signals generated" in output

    def test_display_summary_with_errors(self, mock_result, mock_signals):
        """Test summary display with errors."""
        mock_result.errors = ["Error 1", "Error 2"]
        console = Console(file=StringIO())

        _display_summary(console, mock_result, mock_signals, 0.6)

        output = console.file.getvalue()
        assert "Errors: 2" in output

    def test_display_detailed(self, mock_result, mock_signals):
        """Test detailed display format."""
        mock_result.signals = mock_signals
        console = Console(file=StringIO())

        _display_detailed(console, mock_result, mock_signals, 0.6)

        output = console.file.getvalue()
        assert "Timing Breakdown" in output
        assert "Data fetch: 500ms" in output
        assert "Indicator calculation: 600ms" in output
        assert "Signal generation: 400ms" in output
        assert "Detailed Signal Information" in output

    def test_display_json(self, mock_result, mock_signals):
        """Test JSON display format."""
        mock_result.signals = mock_signals
        console = Console(file=StringIO())

        _display_json(console, mock_result, mock_signals)

        output = console.file.getvalue()
        data = json.loads(output)

        assert data["summary"]["symbols_processed"] == 3
        assert data["summary"]["signals_generated"] == 2
        assert len(data["signals"]) == 2
        assert data["signals"][0]["symbol"] == "AAPL"
        assert data["signals"][0]["type"] == "LONG"  # SignalType.LONG.value
        assert data["signals"][0]["confidence"] == 0.85


class TestRunPredictCommand:
    """Test run_predict_command function."""

    @patch("dgas.cli.predict.Settings")
    @patch("dgas.cli.predict.PredictionEngine")
    @patch("dgas.cli.predict.PredictionPersistence")
    def test_successful_prediction(
        self,
        mock_persistence_cls,
        mock_engine_cls,
        mock_settings_cls,
        mock_result,
        mock_signals,
    ):
        """Test successful prediction execution."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.default_watchlist = ["AAPL"]
        mock_settings_cls.return_value = mock_settings

        mock_result.signals = mock_signals
        mock_engine = Mock()
        mock_engine.run.return_value = mock_result
        mock_engine_cls.return_value = mock_engine

        mock_persistence = Mock()
        mock_persistence_cls.return_value = mock_persistence

        # Create args
        args = Namespace(
            symbols=["AAPL"],
            format="summary",
            save=False,
            notify=False,
            watchlist=None,
            min_confidence=0.6,
        )

        # Run command
        exit_code = run_predict_command(args)

        assert exit_code == 0
        mock_engine.run.assert_called_once_with(["AAPL"])

    @patch("dgas.cli.predict.Settings")
    @patch("dgas.cli.predict.PredictionEngine")
    @patch("dgas.cli.predict.PredictionPersistence")
    def test_prediction_with_save(
        self,
        mock_persistence_cls,
        mock_engine_cls,
        mock_settings_cls,
        mock_result,
        mock_signals,
    ):
        """Test prediction with database save."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings_cls.return_value = mock_settings

        mock_result.signals = mock_signals
        mock_engine = Mock()
        mock_engine.run.return_value = mock_result
        mock_engine_cls.return_value = mock_engine

        mock_persistence = Mock()
        mock_persistence.save_prediction_run.return_value = 123
        mock_persistence_cls.return_value = mock_persistence

        # Create args
        args = Namespace(
            symbols=["AAPL"],
            format="summary",
            save=True,
            notify=False,
            watchlist=None,
            min_confidence=0.6,
        )

        # Run command
        exit_code = run_predict_command(args)

        assert exit_code == 0
        mock_persistence.save_prediction_run.assert_called_once()
        assert mock_persistence.save_signal.call_count == 2

    @patch("dgas.cli.predict.Settings")
    @patch("dgas.cli.predict.PredictionEngine")
    @patch("dgas.cli.predict.PredictionPersistence")
    @patch("dgas.cli.predict.NotificationRouter")
    def test_prediction_with_notifications(
        self,
        mock_router_cls,
        mock_persistence_cls,
        mock_engine_cls,
        mock_settings_cls,
        mock_result,
        mock_signals,
    ):
        """Test prediction with notifications."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings_cls.return_value = mock_settings

        mock_result.signals = mock_signals
        mock_engine = Mock()
        mock_engine.run.return_value = mock_result
        mock_engine_cls.return_value = mock_engine

        mock_persistence = Mock()
        mock_persistence_cls.return_value = mock_persistence

        mock_router = Mock()
        mock_router.send_signals.return_value = []
        mock_router_cls.return_value = mock_router

        # Create args
        args = Namespace(
            symbols=["AAPL"],
            format="summary",
            save=False,
            notify=True,
            watchlist=None,
            min_confidence=0.6,
        )

        # Run command
        exit_code = run_predict_command(args)

        assert exit_code == 0
        mock_router.send_signals.assert_called_once()

    @patch("dgas.cli.predict.Settings")
    @patch("dgas.cli.predict.PredictionEngine")
    @patch("dgas.cli.predict.PredictionPersistence")
    def test_prediction_no_symbols(
        self,
        mock_persistence_cls,
        mock_engine_cls,
        mock_settings_cls,
    ):
        """Test prediction with no symbols."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.default_watchlist = None
        mock_settings_cls.return_value = mock_settings

        # Create args
        args = Namespace(
            symbols=[],
            format="summary",
            save=False,
            notify=False,
            watchlist=None,
            min_confidence=0.6,
        )

        # Run command
        exit_code = run_predict_command(args)

        assert exit_code == 1

    @patch("dgas.cli.predict.Settings")
    def test_prediction_error(self, mock_settings_cls):
        """Test prediction with error."""
        # Setup mocks to raise exception
        mock_settings_cls.side_effect = Exception("Test error")

        # Create args
        args = Namespace(
            symbols=["AAPL"],
            format="summary",
            save=False,
            notify=False,
            watchlist=None,
            min_confidence=0.6,
        )

        # Run command
        exit_code = run_predict_command(args)

        assert exit_code == 1

    @patch("dgas.cli.predict.Settings")
    @patch("dgas.cli.predict.PredictionEngine")
    @patch("dgas.cli.predict.PredictionPersistence")
    def test_prediction_filters_by_confidence(
        self,
        mock_persistence_cls,
        mock_engine_cls,
        mock_settings_cls,
        mock_result,
    ):
        """Test that signals are filtered by confidence threshold."""
        # Create signals with different confidence levels
        signals = [
            GeneratedSignal(
                symbol="AAPL",
                signal_timestamp=datetime.now(),
                signal_type=SignalType.LONG,
                entry_price=Decimal("175.50"),
                stop_loss=Decimal("172.00"),
                target_price=Decimal("180.00"),
                confidence=0.85,
                signal_strength=0.90,
                timeframe_alignment=0.85,
                risk_reward_ratio=2.5,
                htf_trend=TrendDirection.UP,
                trading_tf_state="bullish",
                confluence_zones_count=2,
                pattern_context={},
                htf_timeframe="4h",
                trading_timeframe="1h",
            ),
            GeneratedSignal(
                symbol="MSFT",
                signal_timestamp=datetime.now(),
                signal_type=SignalType.LONG,
                entry_price=Decimal("380.00"),
                stop_loss=Decimal("377.00"),
                target_price=Decimal("385.00"),
                confidence=0.55,  # Below threshold
                signal_strength=0.60,
                timeframe_alignment=0.55,
                risk_reward_ratio=1.5,
                htf_trend=TrendDirection.UP,
                trading_tf_state="bullish",
                confluence_zones_count=1,
                pattern_context={},
                htf_timeframe="4h",
                trading_timeframe="1h",
            ),
        ]

        # Setup mocks
        mock_settings = Mock()
        mock_settings_cls.return_value = mock_settings

        mock_result.signals = signals
        mock_engine = Mock()
        mock_engine.run.return_value = mock_result
        mock_engine_cls.return_value = mock_engine

        mock_persistence = Mock()
        mock_persistence.save_prediction_run.return_value = 123
        mock_persistence_cls.return_value = mock_persistence

        # Create args with min confidence 0.6
        args = Namespace(
            symbols=["AAPL", "MSFT"],
            format="summary",
            save=True,
            notify=False,
            watchlist=None,
            min_confidence=0.6,
        )

        # Run command
        exit_code = run_predict_command(args)

        assert exit_code == 0
        # Only one signal should be saved (confidence >= 0.6)
        assert mock_persistence.save_signal.call_count == 1
