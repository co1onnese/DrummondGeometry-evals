"""
Unit tests for scheduler CLI command.
"""

from __future__ import annotations

import os
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from dgas.cli.scheduler_cli import (
    _cleanup_pid_file,
    _format_uptime,
    _is_running,
    _process_exists,
    _read_pid_file,
    _restart_scheduler,
    _start_scheduler,
    _status_scheduler,
    _stop_scheduler,
    _write_pid_file,
    setup_scheduler_parser,
)


class TestSetupSchedulerParser:
    """Test setup_scheduler_parser function."""

    def test_parser_creation(self):
        """Test that parser is created with correct subcommands."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        scheduler_parser = setup_scheduler_parser(subparsers)

        assert scheduler_parser is not None

        # Test start command
        args = parser.parse_args(["scheduler", "start"])
        assert args.scheduler_command == "start"
        assert hasattr(args, "func")

        # Test stop command
        args = parser.parse_args(["scheduler", "stop"])
        assert args.scheduler_command == "stop"
        assert hasattr(args, "func")

        # Test status command
        args = parser.parse_args(["scheduler", "status"])
        assert args.scheduler_command == "status"
        assert hasattr(args, "func")

        # Test restart command
        args = parser.parse_args(["scheduler", "restart"])
        assert args.scheduler_command == "restart"
        assert hasattr(args, "func")

    def test_start_with_options(self):
        """Test start command with options."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_scheduler_parser(subparsers)

        args = parser.parse_args([
            "scheduler", "start",
            "--daemon",
            "--pid-file", "/tmp/test.pid",
        ])

        assert args.scheduler_command == "start"
        assert args.daemon is True
        assert args.pid_file == Path("/tmp/test.pid")

    def test_stop_with_force(self):
        """Test stop command with force option."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_scheduler_parser(subparsers)

        args = parser.parse_args([
            "scheduler", "stop",
            "--force",
        ])

        assert args.scheduler_command == "stop"
        assert args.force is True


class TestPidFileOperations:
    """Test PID file operations."""

    def test_write_and_read_pid_file(self, tmp_path):
        """Test writing and reading PID file."""
        pid_file = tmp_path / "test.pid"

        _write_pid_file(pid_file)

        assert pid_file.exists()

        pid = _read_pid_file(pid_file)
        assert pid == os.getpid()

    def test_read_nonexistent_pid_file(self, tmp_path):
        """Test reading nonexistent PID file."""
        pid_file = tmp_path / "nonexistent.pid"

        pid = _read_pid_file(pid_file)
        assert pid is None

    def test_read_invalid_pid_file(self, tmp_path):
        """Test reading invalid PID file."""
        pid_file = tmp_path / "invalid.pid"
        pid_file.write_text("not_a_number")

        pid = _read_pid_file(pid_file)
        assert pid is None

    def test_cleanup_pid_file(self, tmp_path):
        """Test cleaning up PID file."""
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("12345")

        _cleanup_pid_file(pid_file)

        assert not pid_file.exists()

    def test_cleanup_nonexistent_pid_file(self, tmp_path):
        """Test cleaning up nonexistent PID file (should not error)."""
        pid_file = tmp_path / "nonexistent.pid"

        # Should not raise exception
        _cleanup_pid_file(pid_file)


class TestProcessHelpers:
    """Test process helper functions."""

    def test_process_exists_current_process(self):
        """Test checking if current process exists."""
        assert _process_exists(os.getpid()) is True

    def test_process_exists_invalid_pid(self):
        """Test checking if invalid process exists."""
        # Use PID that is very unlikely to exist
        assert _process_exists(999999) is False

    def test_is_running_with_valid_pid(self, tmp_path):
        """Test checking if scheduler is running with valid PID."""
        pid_file = tmp_path / "test.pid"
        pid_file.write_text(str(os.getpid()))

        assert _is_running(pid_file) is True

    def test_is_running_with_invalid_pid(self, tmp_path):
        """Test checking if scheduler is running with invalid PID."""
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("999999")

        assert _is_running(pid_file) is False

    def test_is_running_without_pid_file(self, tmp_path):
        """Test checking if scheduler is running without PID file."""
        pid_file = tmp_path / "nonexistent.pid"

        assert _is_running(pid_file) is False


class TestFormatUptime:
    """Test _format_uptime function."""

    def test_format_seconds(self):
        """Test formatting seconds."""
        assert _format_uptime(45) == "45s"

    def test_format_minutes(self):
        """Test formatting minutes."""
        assert _format_uptime(125) == "2m 5s"

    def test_format_hours(self):
        """Test formatting hours."""
        assert _format_uptime(3665) == "1h 1m 5s"

    def test_format_days(self):
        """Test formatting days."""
        assert _format_uptime(90065) == "1d 1h 1m 5s"

    def test_format_zero(self):
        """Test formatting zero seconds."""
        assert _format_uptime(0) == "0s"


class TestStartScheduler:
    """Test _start_scheduler function."""

    @patch("dgas.cli.scheduler_cli.PredictionScheduler")
    @patch("dgas.cli.scheduler_cli.PredictionEngine")
    @patch("dgas.cli.scheduler_cli.PredictionPersistence")
    @patch("dgas.cli.scheduler_cli.PerformanceTracker")
    @patch("dgas.cli.scheduler_cli.Settings")
    @patch("dgas.cli.scheduler_cli._is_running")
    @patch("dgas.cli.scheduler_cli._write_pid_file")
    def test_start_scheduler_already_running(
        self,
        mock_write_pid,
        mock_is_running,
        mock_settings,
        mock_perf_tracker,
        mock_persistence,
        mock_engine,
        mock_scheduler_cls,
        tmp_path,
    ):
        """Test starting scheduler when already running."""
        mock_is_running.return_value = True

        args = Namespace(
            pid_file=tmp_path / "test.pid",
            daemon=False,
        )

        result = _start_scheduler(args)

        assert result == 1
        mock_write_pid.assert_not_called()

    @patch("dgas.cli.scheduler_cli.PredictionScheduler")
    @patch("dgas.cli.scheduler_cli.PredictionEngine")
    @patch("dgas.cli.scheduler_cli.PredictionPersistence")
    @patch("dgas.cli.scheduler_cli.PerformanceTracker")
    @patch("dgas.cli.scheduler_cli.Settings")
    @patch("dgas.cli.scheduler_cli._is_running")
    @patch("dgas.cli.scheduler_cli._write_pid_file")
    @patch("dgas.cli.scheduler_cli._cleanup_pid_file")
    def test_start_scheduler_error(
        self,
        mock_cleanup,
        mock_write_pid,
        mock_is_running,
        mock_settings,
        mock_perf_tracker,
        mock_persistence,
        mock_engine,
        mock_scheduler_cls,
        tmp_path,
    ):
        """Test starting scheduler with error."""
        mock_is_running.return_value = False
        mock_settings.side_effect = Exception("Test error")

        args = Namespace(
            pid_file=tmp_path / "test.pid",
            daemon=False,
        )

        result = _start_scheduler(args)

        assert result == 1
        mock_cleanup.assert_called_once_with(tmp_path / "test.pid")


class TestStopScheduler:
    """Test _stop_scheduler function."""

    @patch("dgas.cli.scheduler_cli._read_pid_file")
    def test_stop_scheduler_not_running(self, mock_read_pid, tmp_path):
        """Test stopping scheduler when not running."""
        mock_read_pid.return_value = None

        args = Namespace(
            pid_file=tmp_path / "test.pid",
            force=False,
        )

        result = _stop_scheduler(args)

        assert result == 1

    @patch("dgas.cli.scheduler_cli._read_pid_file")
    @patch("dgas.cli.scheduler_cli._process_exists")
    @patch("dgas.cli.scheduler_cli._cleanup_pid_file")
    def test_stop_scheduler_stale_pid(
        self,
        mock_cleanup,
        mock_exists,
        mock_read_pid,
        tmp_path,
    ):
        """Test stopping scheduler with stale PID file."""
        mock_read_pid.return_value = 12345
        mock_exists.return_value = False

        args = Namespace(
            pid_file=tmp_path / "test.pid",
            force=False,
        )

        result = _stop_scheduler(args)

        assert result == 1
        mock_cleanup.assert_called_once_with(tmp_path / "test.pid")

    @patch("dgas.cli.scheduler_cli._read_pid_file")
    @patch("dgas.cli.scheduler_cli._process_exists")
    @patch("dgas.cli.scheduler_cli._cleanup_pid_file")
    @patch("os.kill")
    def test_stop_scheduler_graceful(
        self,
        mock_kill,
        mock_cleanup,
        mock_exists,
        mock_read_pid,
        tmp_path,
    ):
        """Test graceful scheduler shutdown."""
        mock_read_pid.return_value = 12345
        # Process exists initially, then doesn't
        mock_exists.side_effect = [True, False]

        args = Namespace(
            pid_file=tmp_path / "test.pid",
            force=False,
        )

        result = _stop_scheduler(args)

        assert result == 0
        mock_cleanup.assert_called_once_with(tmp_path / "test.pid")


class TestStatusScheduler:
    """Test _status_scheduler function."""

    @patch("dgas.cli.scheduler_cli._read_pid_file")
    def test_status_not_running(self, mock_read_pid, tmp_path):
        """Test status when scheduler not running."""
        mock_read_pid.return_value = None

        args = Namespace(pid_file=tmp_path / "test.pid")

        result = _status_scheduler(args)

        assert result == 1

    @patch("dgas.cli.scheduler_cli._read_pid_file")
    @patch("dgas.cli.scheduler_cli._process_exists")
    def test_status_stale_pid(self, mock_exists, mock_read_pid, tmp_path):
        """Test status with stale PID file."""
        mock_read_pid.return_value = 12345
        mock_exists.return_value = False

        args = Namespace(pid_file=tmp_path / "test.pid")

        result = _status_scheduler(args)

        assert result == 1

    @patch("dgas.cli.scheduler_cli._read_pid_file")
    @patch("dgas.cli.scheduler_cli._process_exists")
    def test_status_running_no_psutil(
        self,
        mock_exists,
        mock_read_pid,
        tmp_path,
    ):
        """Test status when running (without psutil)."""
        mock_read_pid.return_value = os.getpid()
        mock_exists.return_value = True

        args = Namespace(pid_file=tmp_path / "test.pid")

        result = _status_scheduler(args)

        assert result == 0


class TestRestartScheduler:
    """Test _restart_scheduler function."""

    @patch("dgas.cli.scheduler_cli._is_running")
    @patch("dgas.cli.scheduler_cli._stop_scheduler")
    @patch("dgas.cli.scheduler_cli._start_scheduler")
    @patch("time.sleep")
    def test_restart_not_running(
        self,
        mock_sleep,
        mock_start,
        mock_stop,
        mock_is_running,
        tmp_path,
    ):
        """Test restarting when scheduler not running."""
        mock_is_running.return_value = False
        mock_start.return_value = 0

        args = Namespace(
            pid_file=tmp_path / "test.pid",
            daemon=False,
        )

        result = _restart_scheduler(args)

        assert result == 0
        mock_stop.assert_not_called()
        mock_start.assert_called_once()

    @patch("dgas.cli.scheduler_cli._is_running")
    @patch("dgas.cli.scheduler_cli._stop_scheduler")
    @patch("dgas.cli.scheduler_cli._start_scheduler")
    @patch("time.sleep")
    def test_restart_running(
        self,
        mock_sleep,
        mock_start,
        mock_stop,
        mock_is_running,
        tmp_path,
    ):
        """Test restarting when scheduler is running."""
        mock_is_running.return_value = True
        mock_stop.return_value = 0
        mock_start.return_value = 0

        args = Namespace(
            pid_file=tmp_path / "test.pid",
            daemon=False,
        )

        result = _restart_scheduler(args)

        assert result == 0
        mock_stop.assert_called_once()
        mock_start.assert_called_once()

    @patch("dgas.cli.scheduler_cli._is_running")
    @patch("dgas.cli.scheduler_cli._stop_scheduler")
    @patch("dgas.cli.scheduler_cli._start_scheduler")
    @patch("time.sleep")
    def test_restart_stop_fails(
        self,
        mock_sleep,
        mock_start,
        mock_stop,
        mock_is_running,
        tmp_path,
    ):
        """Test restarting when stop fails."""
        mock_is_running.return_value = True
        mock_stop.return_value = 1

        args = Namespace(
            pid_file=tmp_path / "test.pid",
            daemon=False,
        )

        result = _restart_scheduler(args)

        assert result == 1
        mock_stop.assert_called_once()
        mock_start.assert_not_called()
