"""
Monitor command for DGAS CLI.

Provides monitoring and reporting for the prediction system.
"""

from __future__ import annotations

import json
import logging
import time
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table

from dgas.config import load_settings
from dgas.prediction import PredictionPersistence
from dgas.prediction.monitoring import (
    CalibrationEngine,
    PerformanceTracker,
)
from dgas.settings import Settings

logger = logging.getLogger(__name__)


def setup_monitor_parser(subparsers) -> ArgumentParser:
    """
    Set up the monitor subcommand parser.

    Args:
        subparsers: The subparsers object from argparse

    Returns:
        The monitor subparser
    """
    parser = subparsers.add_parser(
        "monitor",
        help="Monitor prediction system performance and signals",
        description="View performance metrics, calibration reports, and generated signals",
    )

    monitor_subparsers = parser.add_subparsers(dest="monitor_command")

    # Performance command
    perf_parser = monitor_subparsers.add_parser(
        "performance",
        help="View performance metrics",
    )
    perf_parser.add_argument(
        "--lookback",
        type=int,
        default=24,
        help="Lookback window in hours (default: 24)",
    )
    perf_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    perf_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    perf_parser.set_defaults(func=_performance_command)

    # Calibration command
    calib_parser = monitor_subparsers.add_parser(
        "calibration",
        help="View signal calibration report",
    )
    calib_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)",
    )
    calib_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    calib_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    calib_parser.set_defaults(func=_calibration_command)

    # Signals command
    signals_parser = monitor_subparsers.add_parser(
        "signals",
        help="View recent generated signals",
    )
    signals_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of signals to show (default: 20)",
    )
    signals_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum confidence threshold (default: 0.0)",
    )
    signals_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    signals_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    signals_parser.set_defaults(func=_signals_command)

    # Dashboard command
    dashboard_parser = monitor_subparsers.add_parser(
        "dashboard",
        help="Live updating dashboard",
    )
    dashboard_parser.add_argument(
        "--refresh",
        type=int,
        default=5,
        help="Refresh interval in seconds (default: 5)",
    )
    dashboard_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    dashboard_parser.set_defaults(func=_dashboard_command)

    return parser


def _performance_command(args: Namespace) -> int:
    """
    Display performance metrics.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        settings = Settings()
        persistence = PredictionPersistence(settings)
        tracker = PerformanceTracker(persistence)

        # Get performance summary
        summary = tracker.get_performance_summary(lookback_hours=args.lookback)

        if args.format == "json":
            output = {
                "lookback_hours": args.lookback,
                "total_runs": summary.total_runs,
                "latency": {
                    "p50_ms": summary.latency_p50_ms,
                    "p95_ms": summary.latency_p95_ms,
                    "p99_ms": summary.latency_p99_ms,
                },
                "throughput": {
                    "avg_symbols_per_second": summary.avg_symbols_per_second,
                    "total_symbols_processed": summary.total_symbols_processed,
                    "total_signals_generated": summary.total_signals_generated,
                },
                "errors": {
                    "error_rate_pct": summary.error_rate_pct,
                    "total_errors": summary.total_errors,
                },
                "uptime_pct": summary.uptime_pct,
                "sla_compliant": summary.sla_compliant,
            }
            console.print(json.dumps(output, indent=2))
        else:
            _display_performance_table(console, summary, args.lookback)

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Performance command failed")
        return 1


def _calibration_command(args: Namespace) -> int:
    """
    Display calibration report.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        settings = Settings()
        persistence = PredictionPersistence(settings)
        engine = CalibrationEngine(persistence)

        # Get calibration report
        start_date = datetime.now() - timedelta(days=args.days)
        end_date = datetime.now()
        report = engine.get_calibration_report(date_range=(start_date, end_date))

        if args.format == "json":
            output = {
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": args.days,
                },
                "overall": {
                    "total_signals": report.total_signals,
                    "win_rate": report.overall_win_rate,
                    "avg_pnl_pct": report.avg_pnl_pct,
                    "target_hit_rate": report.target_hit_rate,
                    "stop_hit_rate": report.stop_hit_rate,
                },
                "by_confidence": [
                    {
                        "range": bucket.bucket_range,
                        "count": bucket.count,
                        "win_rate": bucket.win_rate,
                        "avg_pnl_pct": bucket.avg_pnl_pct,
                    }
                    for bucket in report.by_confidence_bucket
                ],
                "by_type": [
                    {
                        "type": sig_type.signal_type,
                        "count": sig_type.count,
                        "win_rate": sig_type.win_rate,
                        "avg_pnl_pct": sig_type.avg_pnl_pct,
                    }
                    for sig_type in report.by_signal_type
                ],
            }
            console.print(json.dumps(output, indent=2))
        else:
            _display_calibration_tables(console, report, args.days)

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Calibration command failed")
        return 1


def _signals_command(args: Namespace) -> int:
    """
    Display recent signals.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        settings = Settings()
        persistence = PredictionPersistence(settings)

        # Get recent signals
        signals = persistence.get_recent_signals(limit=args.limit)

        # Filter by confidence
        if args.min_confidence > 0.0:
            signals = [s for s in signals if s.get("confidence", 0.0) >= args.min_confidence]

        if args.format == "json":
            console.print(json.dumps(signals, indent=2, default=str))
        else:
            _display_signals_table(console, signals)

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Signals command failed")
        return 1


def _dashboard_command(args: Namespace) -> int:
    """
    Display live updating dashboard.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        settings = Settings()
        persistence = PredictionPersistence(settings)

        console.print("[cyan]Starting dashboard (Press Ctrl+C to exit)...[/cyan]\n")

        with Live(_generate_dashboard(persistence), console=console, refresh_per_second=1) as live:
            try:
                while True:
                    time.sleep(args.refresh)
                    live.update(_generate_dashboard(persistence))
            except KeyboardInterrupt:
                console.print("\n[yellow]Dashboard stopped[/yellow]")

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Dashboard command failed")
        return 1


# Display helper functions

def _display_performance_table(console: Console, summary: Any, lookback_hours: int) -> None:
    """Display performance metrics in table format."""
    console.print(f"\n[bold]Performance Summary (Last {lookback_hours} hours)[/bold]\n")

    # Overall metrics
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    table.add_row("Total Runs", str(summary.total_runs))
    table.add_row("Uptime", f"{summary.uptime_pct:.2f}%")
    table.add_row("SLA Compliant", "[green]Yes[/green]" if summary.sla_compliant else "[red]No[/red]")

    console.print(table)

    # Latency metrics
    console.print("\n[bold]Latency:[/bold]")
    latency_table = Table(show_header=True, header_style="bold cyan")
    latency_table.add_column("Percentile")
    latency_table.add_column("Latency (ms)", justify="right")

    latency_table.add_row("P50", f"{summary.latency_p50_ms:,}")
    latency_table.add_row("P95", f"{summary.latency_p95_ms:,}")
    latency_table.add_row("P99", f"{summary.latency_p99_ms:,}")

    console.print(latency_table)

    # Throughput metrics
    console.print("\n[bold]Throughput:[/bold]")
    throughput_table = Table(show_header=True, header_style="bold cyan")
    throughput_table.add_column("Metric")
    throughput_table.add_column("Value", justify="right")

    throughput_table.add_row("Symbols/Second", f"{summary.avg_symbols_per_second:.2f}")
    throughput_table.add_row("Total Symbols", f"{summary.total_symbols_processed:,}")
    throughput_table.add_row("Total Signals", f"{summary.total_signals_generated:,}")

    console.print(throughput_table)

    # Error metrics
    console.print("\n[bold]Errors:[/bold]")
    error_table = Table(show_header=True, header_style="bold cyan")
    error_table.add_column("Metric")
    error_table.add_column("Value", justify="right")

    error_table.add_row("Error Rate", f"{summary.error_rate_pct:.2f}%")
    error_table.add_row("Total Errors", str(summary.total_errors))

    console.print(error_table)


def _display_calibration_tables(console: Console, report: Any, days: int) -> None:
    """Display calibration report in table format."""
    console.print(f"\n[bold]Calibration Report (Last {days} days)[/bold]\n")

    # Overall metrics
    console.print("[bold]Overall Performance:[/bold]")
    overall_table = Table(show_header=True, header_style="bold cyan")
    overall_table.add_column("Metric")
    overall_table.add_column("Value", justify="right")

    overall_table.add_row("Total Signals", str(report.total_signals))
    overall_table.add_row("Win Rate", f"{report.overall_win_rate:.2%}")
    overall_table.add_row("Avg P&L", f"{report.avg_pnl_pct:+.2%}")
    overall_table.add_row("Target Hit Rate", f"{report.target_hit_rate:.2%}")
    overall_table.add_row("Stop Hit Rate", f"{report.stop_hit_rate:.2%}")

    console.print(overall_table)

    # By confidence bucket
    if report.by_confidence_bucket:
        console.print("\n[bold]By Confidence Bucket:[/bold]")
        conf_table = Table(show_header=True, header_style="bold cyan")
        conf_table.add_column("Range")
        conf_table.add_column("Count", justify="right")
        conf_table.add_column("Win Rate", justify="right")
        conf_table.add_column("Avg P&L", justify="right")

        for bucket in report.by_confidence_bucket:
            conf_table.add_row(
                bucket.bucket_range,
                str(bucket.count),
                f"{bucket.win_rate:.2%}",
                f"{bucket.avg_pnl_pct:+.2%}",
            )

        console.print(conf_table)

    # By signal type
    if report.by_signal_type:
        console.print("\n[bold]By Signal Type:[/bold]")
        type_table = Table(show_header=True, header_style="bold cyan")
        type_table.add_column("Type")
        type_table.add_column("Count", justify="right")
        type_table.add_column("Win Rate", justify="right")
        type_table.add_column("Avg P&L", justify="right")

        for sig_type in report.by_signal_type:
            type_table.add_row(
                sig_type.signal_type,
                str(sig_type.count),
                f"{sig_type.win_rate:.2%}",
                f"{sig_type.avg_pnl_pct:+.2%}",
            )

        console.print(type_table)


def _display_signals_table(console: Console, signals: List[Dict[str, Any]]) -> None:
    """Display signals in table format."""
    console.print(f"\n[bold]Recent Signals ({len(signals)})[/bold]\n")

    if not signals:
        console.print("[yellow]No signals found[/yellow]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Timestamp")
    table.add_column("Symbol")
    table.add_column("Type")
    table.add_column("Confidence")
    table.add_column("Entry")
    table.add_column("Target")
    table.add_column("Stop")
    table.add_column("Outcome")

    for signal in signals:
        outcome = signal.get("outcome", "PENDING") or "PENDING"
        outcome_color = {
            "WIN": "green",
            "LOSS": "red",
            "NEUTRAL": "yellow",
            "PENDING": "white",
        }.get(outcome, "white")

        table.add_row(
            signal.get("timestamp", "").split(".")[0] if signal.get("timestamp") else "N/A",
            signal.get("symbol", "N/A"),
            signal.get("signal_type", "N/A"),
            f"{signal.get('confidence', 0.0):.2%}",
            f"${signal.get('entry_price', 0.0):.2f}",
            f"${signal.get('target_price', 0.0):.2f}",
            f"${signal.get('stop_loss', 0.0):.2f}",
            f"[{outcome_color}]{outcome}[/{outcome_color}]",
        )

    console.print(table)


def _generate_dashboard(persistence: PredictionPersistence) -> Table:
    """Generate dashboard layout."""
    # Create performance tracker and calibration engine
    perf_tracker = PerformanceTracker(persistence)
    calib_engine = CalibrationEngine(persistence)

    # Get data
    perf_summary = perf_tracker.get_performance_summary(lookback_hours=24)
    signals = persistence.get_recent_signals(limit=10)

    # Create dashboard table
    dashboard = Table(title=f"DGAS Prediction Dashboard - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Performance column
    perf_table = Table(show_header=False, box=None)
    perf_table.add_column("Metric")
    perf_table.add_column("Value", justify="right")

    perf_table.add_row("[bold cyan]Performance (24h)[/bold cyan]", "")
    perf_table.add_row("Runs", str(perf_summary.total_runs))
    perf_table.add_row("P95 Latency", f"{perf_summary.latency_p95_ms:,}ms")
    perf_table.add_row("Error Rate", f"{perf_summary.error_rate_pct:.2f}%")
    perf_table.add_row("SLA", "[green]OK[/green]" if perf_summary.sla_compliant else "[red]FAIL[/red]")

    # Signals column
    signals_table = Table(show_header=False, box=None)
    signals_table.add_column("Symbol")
    signals_table.add_column("Type")
    signals_table.add_column("Conf")

    signals_table.add_row("[bold cyan]Recent Signals[/bold cyan]", "", "")
    for signal in signals[:5]:
        signals_table.add_row(
            signal.get("symbol", "N/A"),
            signal.get("signal_type", "N/A"),
            f"{signal.get('confidence', 0.0):.0%}",
        )

    # Combine columns
    dashboard.add_column("Performance", style="cyan")
    dashboard.add_column("Signals", style="cyan")

    dashboard.add_row(perf_table, signals_table)

    return dashboard
