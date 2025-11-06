from datetime import datetime, timezone
from pathlib import Path

import pytest

from dgas.__main__ import build_parser, main
from dgas.monitoring import SymbolIngestionStats


def test_data_report_cli(monkeypatch, capsys, tmp_path):
    stats = [
        SymbolIngestionStats(
            symbol="AAPL",
            exchange="US",
            interval="30min",
            bar_count=10,
            first_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            last_timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            estimated_missing_bars=0,
        )
    ]

    monkeypatch.setattr("dgas.__main__.generate_ingestion_report", lambda interval: stats)
    monkeypatch.setattr("dgas.__main__.write_report", lambda s, path: Path(path).write_text("written"))

    output_path = tmp_path / "report.md"
    exit_code = main(["data-report", "--interval", "30min", "--output", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "AAPL" in captured.out
    assert output_path.exists()


class TestAnalyzeCommand:
    """Test analyze command argument parsing."""

    def test_analyze_requires_symbols(self):
        """Test that analyze command requires at least one symbol."""
        parser = build_parser()
        args = parser.parse_args(["analyze", "AAPL"])
        assert args.command == "analyze"
        assert args.symbols == ["AAPL"]

    def test_analyze_multiple_symbols(self):
        """Test analyze command with multiple symbols."""
        parser = build_parser()
        args = parser.parse_args(["analyze", "AAPL", "MSFT", "GOOGL"])
        assert args.symbols == ["AAPL", "MSFT", "GOOGL"]

    def test_analyze_with_timeframes(self):
        """Test analyze command with custom timeframes."""
        parser = build_parser()
        args = parser.parse_args([
            "analyze", "AAPL",
            "--htf", "1d",
            "--trading", "4h"
        ])
        assert args.htf_interval == "1d"
        assert args.trading_interval == "4h"

    def test_analyze_defaults(self):
        """Test analyze command default values."""
        parser = build_parser()
        args = parser.parse_args(["analyze", "AAPL"])
        assert args.htf_interval == "4h"
        assert args.trading_interval == "1h"
        assert args.lookback == 200
        assert args.save is False
        assert args.format == "summary"

    def test_analyze_with_save_flag(self):
        """Test analyze command with --save flag."""
        parser = build_parser()
        args = parser.parse_args(["analyze", "AAPL", "--save"])
        assert args.save is True

    def test_analyze_output_formats(self):
        """Test analyze command with different output formats."""
        parser = build_parser()

        args = parser.parse_args(["analyze", "AAPL", "--format", "summary"])
        assert args.format == "summary"

        args = parser.parse_args(["analyze", "AAPL", "--format", "detailed"])
        assert args.format == "detailed"

        args = parser.parse_args(["analyze", "AAPL", "--format", "json"])
        assert args.format == "json"

    def test_analyze_custom_lookback(self):
        """Test analyze command with custom lookback."""
        parser = build_parser()
        args = parser.parse_args(["analyze", "AAPL", "--lookback", "500"])
        assert args.lookback == 500

    def test_analyze_short_flags(self):
        """Test analyze command with short flag aliases."""
        parser = build_parser()
        args = parser.parse_args([
            "analyze", "AAPL",
            "--htf", "1d",
            "--trading", "30min"
        ])
        assert args.htf_interval == "1d"
        assert args.trading_interval == "30min"
