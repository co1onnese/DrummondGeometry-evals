"""
Unit tests for monitor CLI command.
"""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

import pytest
from rich.console import Console

from dgas.cli.monitor import (
    _calibration_command,
    _display_calibration_tables,
    _display_performance_table,
    _display_signals_table,
    _performance_command,
    _signals_command,
    setup_monitor_parser,
)


@pytest.fixture
def mock_perf_summary():
    """Create mock PerformanceSummary."""
    summary = Mock()
    summary.total_runs = 100
    summary.latency_p50_ms = 15000
    summary.latency_p95_ms = 45000
    summary.latency_p99_ms = 55000
    summary.avg_symbols_per_second = 12.5
    summary.total_symbols_processed = 500
    summary.total_signals_generated = 75
    summary.error_rate_pct = 0.5
    summary.total_errors = 2
    summary.uptime_pct = 99.5
    summary.sla_compliant = True
    return summary


@pytest.fixture
def mock_calib_report():
    """Create mock CalibrationReport."""
    report = Mock()
    report.total_signals = 50
    report.overall_win_rate = 0.65
    report.avg_pnl_pct = 1.2
    report.target_hit_rate = 0.70
    report.stop_hit_rate = 0.30

    # Mock confidence buckets
    bucket = Mock()
    bucket.bucket_range = "0.7-0.8"
    bucket.count = 20
    bucket.win_rate = 0.60
    bucket.avg_pnl_pct = 0.8
    report.by_confidence_bucket = [bucket]

    # Mock signal types
    sig_type = Mock()
    sig_type.signal_type = "LONG"
    sig_type.count = 30
    sig_type.win_rate = 0.67
    sig_type.avg_pnl_pct = 1.5
    report.by_signal_type = [sig_type]

    return report


@pytest.fixture
def mock_signals():
    """Create mock signals list."""
    return [
        {
            "timestamp": datetime(2025, 1, 6, 10, 0, 0).isoformat(),
            "symbol": "AAPL",
            "signal_type": "LONG",
            "confidence": 0.85,
            "entry_price": 175.50,
            "target_price": 180.00,
            "stop_loss": 172.00,
            "outcome": "WIN",
        },
        {
            "timestamp": datetime(2025, 1, 6, 11, 0, 0).isoformat(),
            "symbol": "MSFT",
            "signal_type": "SHORT",
            "confidence": 0.72,
            "entry_price": 380.00,
            "target_price": 375.00,
            "stop_loss": 383.00,
            "outcome": "PENDING",
        },
    ]


class TestSetupMonitorParser:
    """Test setup_monitor_parser function."""

    def test_parser_creation(self):
        """Test that parser is created with correct subcommands."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        monitor_parser = setup_monitor_parser(subparsers)

        assert monitor_parser is not None

        # Test performance command
        args = parser.parse_args(["monitor", "performance"])
        assert args.monitor_command == "performance"
        assert hasattr(args, "func")

        # Test calibration command
        args = parser.parse_args(["monitor", "calibration"])
        assert args.monitor_command == "calibration"
        assert hasattr(args, "func")

        # Test signals command
        args = parser.parse_args(["monitor", "signals"])
        assert args.monitor_command == "signals"
        assert hasattr(args, "func")

        # Test dashboard command
        args = parser.parse_args(["monitor", "dashboard"])
        assert args.monitor_command == "dashboard"
        assert hasattr(args, "func")

    def test_performance_with_options(self):
        """Test performance command with options."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_monitor_parser(subparsers)

        args = parser.parse_args([
            "monitor", "performance",
            "--lookback", "48",
            "--format", "json",
        ])

        assert args.monitor_command == "performance"
        assert args.lookback == 48
        assert args.format == "json"

    def test_calibration_with_options(self):
        """Test calibration command with options."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_monitor_parser(subparsers)

        args = parser.parse_args([
            "monitor", "calibration",
            "--days", "14",
            "--format", "json",
        ])

        assert args.monitor_command == "calibration"
        assert args.days == 14
        assert args.format == "json"

    def test_signals_with_options(self):
        """Test signals command with options."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_monitor_parser(subparsers)

        args = parser.parse_args([
            "monitor", "signals",
            "--limit", "50",
            "--min-confidence", "0.7",
            "--format", "json",
        ])

        assert args.monitor_command == "signals"
        assert args.limit == 50
        assert args.min_confidence == 0.7
        assert args.format == "json"


class TestPerformanceCommand:
    """Test _performance_command function."""

    @patch("dgas.cli.monitor.Settings")
    @patch("dgas.cli.monitor.PredictionPersistence")
    @patch("dgas.cli.monitor.PerformanceTracker")
    def test_performance_table_format(
        self,
        mock_tracker_cls,
        mock_persistence_cls,
        mock_settings_cls,
        mock_perf_summary,
    ):
        """Test performance command with table format."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings_cls.return_value = mock_settings

        mock_persistence = Mock()
        mock_persistence_cls.return_value = mock_persistence

        mock_tracker = Mock()
        mock_tracker.get_performance_summary.return_value = mock_perf_summary
        mock_tracker_cls.return_value = mock_tracker

        # Create args
        args = Namespace(
            lookback=24,
            format="table",
        )

        # Run command
        exit_code = _performance_command(args)

        assert exit_code == 0
        mock_tracker.get_performance_summary.assert_called_once_with(lookback_hours=24)

    @patch("dgas.cli.monitor.Settings")
    @patch("dgas.cli.monitor.PredictionPersistence")
    @patch("dgas.cli.monitor.PerformanceTracker")
    def test_performance_json_format(
        self,
        mock_tracker_cls,
        mock_persistence_cls,
        mock_settings_cls,
        mock_perf_summary,
    ):
        """Test performance command with JSON format."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings_cls.return_value = mock_settings

        mock_persistence = Mock()
        mock_persistence_cls.return_value = mock_persistence

        mock_tracker = Mock()
        mock_tracker.get_performance_summary.return_value = mock_perf_summary
        mock_tracker_cls.return_value = mock_tracker

        # Create args
        args = Namespace(
            lookback=48,
            format="json",
        )

        # Run command (capture output for validation)
        exit_code = _performance_command(args)

        assert exit_code == 0
        mock_tracker.get_performance_summary.assert_called_once_with(lookback_hours=48)

    @patch("dgas.cli.monitor.Settings")
    def test_performance_error(self, mock_settings_cls):
        """Test performance command with error."""
        mock_settings_cls.side_effect = Exception("Test error")

        args = Namespace(
            lookback=24,
            format="table",
        )

        exit_code = _performance_command(args)

        assert exit_code == 1


class TestCalibrationCommand:
    """Test _calibration_command function."""

    @patch("dgas.cli.monitor.Settings")
    @patch("dgas.cli.monitor.PredictionPersistence")
    @patch("dgas.cli.monitor.CalibrationEngine")
    def test_calibration_table_format(
        self,
        mock_engine_cls,
        mock_persistence_cls,
        mock_settings_cls,
        mock_calib_report,
    ):
        """Test calibration command with table format."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings_cls.return_value = mock_settings

        mock_persistence = Mock()
        mock_persistence_cls.return_value = mock_persistence

        mock_engine = Mock()
        mock_engine.get_calibration_report.return_value = mock_calib_report
        mock_engine_cls.return_value = mock_engine

        # Create args
        args = Namespace(
            days=7,
            format="table",
        )

        # Run command
        exit_code = _calibration_command(args)

        assert exit_code == 0
        mock_engine.get_calibration_report.assert_called_once()

    @patch("dgas.cli.monitor.Settings")
    @patch("dgas.cli.monitor.PredictionPersistence")
    @patch("dgas.cli.monitor.CalibrationEngine")
    def test_calibration_json_format(
        self,
        mock_engine_cls,
        mock_persistence_cls,
        mock_settings_cls,
        mock_calib_report,
    ):
        """Test calibration command with JSON format."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings_cls.return_value = mock_settings

        mock_persistence = Mock()
        mock_persistence_cls.return_value = mock_persistence

        mock_engine = Mock()
        mock_engine.get_calibration_report.return_value = mock_calib_report
        mock_engine_cls.return_value = mock_engine

        # Create args
        args = Namespace(
            days=14,
            format="json",
        )

        # Run command
        exit_code = _calibration_command(args)

        assert exit_code == 0


class TestSignalsCommand:
    """Test _signals_command function."""

    @patch("dgas.cli.monitor.Settings")
    @patch("dgas.cli.monitor.PredictionPersistence")
    def test_signals_table_format(
        self,
        mock_persistence_cls,
        mock_settings_cls,
        mock_signals,
    ):
        """Test signals command with table format."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings_cls.return_value = mock_settings

        mock_persistence = Mock()
        mock_persistence.get_recent_signals.return_value = mock_signals
        mock_persistence_cls.return_value = mock_persistence

        # Create args
        args = Namespace(
            limit=20,
            min_confidence=0.0,
            format="table",
        )

        # Run command
        exit_code = _signals_command(args)

        assert exit_code == 0
        mock_persistence.get_recent_signals.assert_called_once_with(limit=20)

    @patch("dgas.cli.monitor.Settings")
    @patch("dgas.cli.monitor.PredictionPersistence")
    def test_signals_with_confidence_filter(
        self,
        mock_persistence_cls,
        mock_settings_cls,
        mock_signals,
    ):
        """Test signals command with confidence filter."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings_cls.return_value = mock_settings

        mock_persistence = Mock()
        mock_persistence.get_recent_signals.return_value = mock_signals
        mock_persistence_cls.return_value = mock_persistence

        # Create args
        args = Namespace(
            limit=20,
            min_confidence=0.8,
            format="json",
        )

        # Run command
        exit_code = _signals_command(args)

        assert exit_code == 0


class TestDisplayFunctions:
    """Test display helper functions."""

    def test_display_performance_table(self, mock_perf_summary):
        """Test displaying performance table."""
        console = Console(file=StringIO())

        _display_performance_table(console, mock_perf_summary, 24)

        output = console.file.getvalue()
        assert "Performance Summary" in output
        assert "100" in output  # total runs
        assert "99.50%" in output  # uptime

    def test_display_calibration_tables(self, mock_calib_report):
        """Test displaying calibration tables."""
        console = Console(file=StringIO())

        _display_calibration_tables(console, mock_calib_report, 7)

        output = console.file.getvalue()
        assert "Calibration Report" in output
        assert "50" in output  # total signals
        assert "65.00%" in output  # win rate

    def test_display_signals_table(self, mock_signals):
        """Test displaying signals table."""
        console = Console(file=StringIO())

        _display_signals_table(console, mock_signals)

        output = console.file.getvalue()
        assert "Recent Signals" in output
        assert "AAPL" in output
        assert "MSFT" in output

    def test_display_signals_table_empty(self):
        """Test displaying empty signals table."""
        console = Console(file=StringIO())

        _display_signals_table(console, [])

        output = console.file.getvalue()
        assert "No signals found" in output
