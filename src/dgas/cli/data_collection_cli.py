"""
Data collection command for DGAS CLI.

Provides daemon lifecycle management for the data collection service.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from dgas.config import load_settings
from dgas.config.schema import DataCollectionConfig
from dgas.data.collection_scheduler import DataCollectionScheduler
from dgas.data.collection_service import DataCollectionService
from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import Settings

logger = logging.getLogger(__name__)

# Default PID file
DEFAULT_PID_FILE = Path(".dgas_data_collection.pid")


def setup_data_collection_parser(subparsers) -> ArgumentParser:
    """
    Set up the data-collection subcommand parser.

    Args:
        subparsers: The subparsers object from argparse

    Returns:
        The data-collection subparser
    """
    parser = subparsers.add_parser(
        "data-collection",
        help="Manage the data collection service daemon",
        description="Start, stop, and monitor the data collection service",
    )

    dc_subparsers = parser.add_subparsers(dest="dc_command")

    # Start command
    start_parser = dc_subparsers.add_parser(
        "start",
        help="Start the data collection service daemon",
    )
    start_parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as background daemon (default: foreground)",
    )
    start_parser.add_argument(
        "--pid-file",
        type=Path,
        default=DEFAULT_PID_FILE,
        help=f"Path to PID file (default: {DEFAULT_PID_FILE})",
    )
    start_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    start_parser.set_defaults(func=_start_data_collection)

    # Stop command
    stop_parser = dc_subparsers.add_parser(
        "stop",
        help="Stop the data collection service daemon",
    )
    stop_parser.add_argument(
        "--pid-file",
        type=Path,
        default=DEFAULT_PID_FILE,
        help=f"Path to PID file (default: {DEFAULT_PID_FILE})",
    )
    stop_parser.add_argument(
        "--force",
        action="store_true",
        help="Force kill if graceful shutdown fails",
    )
    stop_parser.set_defaults(func=_stop_data_collection)

    # Status command
    status_parser = dc_subparsers.add_parser(
        "status",
        help="Check data collection service daemon status",
    )
    status_parser.add_argument(
        "--pid-file",
        type=Path,
        default=DEFAULT_PID_FILE,
        help=f"Path to PID file (default: {DEFAULT_PID_FILE})",
    )
    status_parser.set_defaults(func=_status_data_collection)

    # Run-once command
    run_once_parser = dc_subparsers.add_parser(
        "run-once",
        help="Trigger immediate data collection cycle",
    )
    run_once_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    run_once_parser.set_defaults(func=_run_once_data_collection)

    # Stats command
    stats_parser = dc_subparsers.add_parser(
        "stats",
        help="Show data collection statistics",
    )
    stats_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    stats_parser.set_defaults(func=_stats_data_collection)

    return parser


def _is_running(pid_file: Path) -> bool:
    """Check if data collection service is running."""
    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # Check if process exists
        return True
    except (ValueError, OSError):
        return False


def _write_pid_file(pid_file: Path) -> None:
    """Write PID to file."""
    pid_file.write_text(str(os.getpid()))


def _cleanup_pid_file(pid_file: Path) -> None:
    """Remove PID file."""
    if pid_file.exists():
        pid_file.unlink()


def _daemonize(pid_file: Path) -> None:
    """Fork to background daemon."""
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Exit parent
    except OSError as e:
        sys.exit(f"Fork failed: {e}")

    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.exit(f"Second fork failed: {e}")

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    si = open(os.devnull, "r")
    so = open(os.devnull, "a+")
    se = open(os.devnull, "a+")
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


def _signal_handler(signum, frame):
    """Handle shutdown signals."""
    sys.exit(0)


def _start_data_collection(args: Namespace) -> int:
    """Start the data collection service daemon."""
    console = Console()

    # Check if already running
    if _is_running(args.pid_file):
        console.print("[yellow]Data collection service is already running[/yellow]")
        return 1

    try:
        if args.daemon:
            console.print("[cyan]Starting data collection service as daemon...[/cyan]")
            _daemonize(args.pid_file)

        # Write PID file
        _write_pid_file(args.pid_file)

        # Set up signal handlers
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        # Load unified settings
        # Convert string path to Path if needed
        config_path = None
        if args.config:
            from pathlib import Path
            config_path = Path(args.config) if isinstance(args.config, str) else args.config
        
        unified_settings = load_settings(config_file=config_path)

        # Get data collection config
        dc_config = unified_settings.data_collection
        if dc_config is None:
            dc_config = DataCollectionConfig()

        if not dc_config.enabled:
            console.print("[yellow]Data collection service is disabled in configuration[/yellow]")
            _cleanup_pid_file(args.pid_file)
            return 0

        # Load symbols - always load from database for data collection service
        # (config may have placeholder symbols for validation)
        console.print("[cyan]Loading all active symbols from database...[/cyan]")
        from dgas.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
                symbols = [row[0] for row in cur.fetchall()]
        console.print(f"[green]Loaded {len(symbols)} symbols from database[/green]")

        # Create service and scheduler
        legacy_settings = Settings()
        client = EODHDClient(EODHDConfig.from_settings(legacy_settings))
        service = DataCollectionService(dc_config, client=client)

        scheduler = DataCollectionScheduler(
            config=dc_config,
            symbols=symbols,
            service=service,
        )

        # Start scheduler
        console.print("[green]Data collection service started successfully[/green]")
        console.print(f"PID file: {args.pid_file.absolute()}")
        console.print(f"Symbols: {len(symbols)}")
        console.print(f"Intervals: {dc_config.interval_market_hours} (market), {dc_config.interval_after_hours} (after hours), {dc_config.interval_weekends} (weekends)")

        scheduler.start()

        # Keep running (foreground mode)
        if not args.daemon:
            console.print("\n[cyan]Press Ctrl+C to stop data collection service[/cyan]\n")
            try:
                while scheduler._is_running:
                    time.sleep(1)
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping data collection service...[/yellow]")
                scheduler.stop()
                console.print("[green]Data collection service stopped[/green]")

        return 0

    except Exception as e:
        console.print(f"[red]Error starting data collection service: {e}[/red]")
        logger.exception("Failed to start data collection service")
        _cleanup_pid_file(args.pid_file)
        return 1


def _stop_data_collection(args: Namespace) -> int:
    """Stop the data collection service daemon."""
    console = Console()

    if not _is_running(args.pid_file):
        console.print("[yellow]Data collection service is not running[/yellow]")
        return 0

    try:
        pid = int(args.pid_file.read_text().strip())

        # Try graceful shutdown
        console.print(f"[cyan]Stopping data collection service (PID: {pid})...[/cyan]")
        os.kill(pid, signal.SIGTERM)

        # Wait for shutdown
        for _ in range(10):
            time.sleep(0.5)
            if not _is_running(args.pid_file):
                console.print("[green]Data collection service stopped[/green]")
                _cleanup_pid_file(args.pid_file)
                return 0

        # Force kill if needed
        if args.force:
            console.print("[yellow]Force killing data collection service...[/yellow]")
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
            _cleanup_pid_file(args.pid_file)
            console.print("[green]Data collection service force stopped[/green]")
            return 0

        console.print("[red]Failed to stop data collection service gracefully[/red]")
        return 1

    except Exception as e:
        console.print(f"[red]Error stopping data collection service: {e}[/red]")
        logger.exception("Failed to stop data collection service")
        return 1


def _status_data_collection(args: Namespace) -> int:
    """Check data collection service status."""
    console = Console()

    if not _is_running(args.pid_file):
        console.print("[red]Data collection service is not running[/red]")
        return 1

    try:
        pid = int(args.pid_file.read_text().strip())

        # Load settings to get config
        config_path = getattr(args, 'config', None)
        unified_settings = load_settings(config_file=config_path)
        dc_config = unified_settings.data_collection or DataCollectionConfig()

        # Create temporary scheduler to get status
        legacy_settings = Settings()
        client = EODHDClient(EODHDConfig.from_settings(legacy_settings))
        service = DataCollectionService(dc_config, client=client)

        symbols = unified_settings.scheduler_symbols or []
        if not symbols:
            from dgas.db import get_connection
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
                    symbols = [row[0] for row in cur.fetchall()]

        scheduler = DataCollectionScheduler(
            config=dc_config,
            symbols=symbols,
            service=service,
        )

        status = scheduler.get_status()

        # Display status
        table = Table(title="Data Collection Service Status")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Status", "🟢 Running" if status["running"] else "🔴 Stopped")
        table.add_row("PID", str(pid))
        table.add_row("Enabled", "Yes" if status["enabled"] else "No")
        table.add_row("Symbols", str(status["symbols"]))
        table.add_row("Current Interval", status["current_interval"])
        table.add_row("Market Open", "Yes" if status["market_open"] else "No")
        table.add_row("Last Run", status["last_run_time"] or "Never")

        if status.get("last_result"):
            lr = status["last_result"]
            table.add_row("", "")
            table.add_row("Last Collection Result", "")
            table.add_row("  Symbols Updated", f"{lr['symbols_updated']}/{lr['symbols_requested']}")
            table.add_row("  Bars Stored", str(lr["bars_stored"]))
            table.add_row("  Execution Time", f"{lr['execution_time_ms']}ms")
            table.add_row("  Errors", str(lr["errors"]))

        # Add WebSocket status
        if status.get("websocket"):
            ws = status["websocket"]
            table.add_row("", "")
            table.add_row("WebSocket Status", "")
            table.add_row("  Started", "Yes" if ws.get("started") else "No")
            if ws.get("client_status"):
                cs = ws["client_status"]
                table.add_row("  Connections", f"{cs.get('connected', 0)}/{cs.get('connections', 0)}")
                table.add_row("  Total Symbols", str(cs.get("total_symbols", 0)))
                table.add_row("  Messages Received", str(cs.get("total_messages_received", 0)))
            table.add_row("  Bars Buffered", str(ws.get("bars_buffered", 0)))
            table.add_row("  Bars Stored", str(ws.get("stats", {}).get("bars_stored", 0)))

        console.print(table)
        return 0

    except Exception as e:
        console.print(f"[red]Error checking status: {e}[/red]")
        logger.exception("Failed to check data collection service status")
        return 1


def _run_once_data_collection(args: Namespace) -> int:
    """Trigger immediate data collection cycle."""
    console = Console()

    try:
        # Load unified settings
        # Convert string path to Path if needed
        config_path = None
        if args.config:
            from pathlib import Path
            config_path = Path(args.config) if isinstance(args.config, str) else args.config
        
        unified_settings = load_settings(config_file=config_path)

        # Get data collection config
        dc_config = unified_settings.data_collection
        if dc_config is None:
            dc_config = DataCollectionConfig()

        if not dc_config.enabled:
            console.print("[yellow]Data collection service is disabled in configuration[/yellow]")
            return 1

        # Load symbols - always load from database for data collection
        from dgas.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
                symbols = [row[0] for row in cur.fetchall()]

        console.print(f"[cyan]Running data collection for {len(symbols)} symbols...[/cyan]")

        # Create service and scheduler
        legacy_settings = Settings()
        client = EODHDClient(EODHDConfig.from_settings(legacy_settings))
        service = DataCollectionService(dc_config, client=client)

        scheduler = DataCollectionScheduler(
            config=dc_config,
            symbols=symbols,
            service=service,
        )

        # Run once
        result = scheduler.run_once()

        # Display results
        console.print("[green]Collection complete![/green]")
        console.print(f"Symbols updated: {result.symbols_updated}/{result.symbols_requested}")
        console.print(f"Bars fetched: {result.bars_fetched}")
        console.print(f"Bars stored: {result.bars_stored}")
        console.print(f"Execution time: {result.execution_time_ms}ms")
        if result.errors:
            console.print(f"[yellow]Errors: {len(result.errors)}[/yellow]")
            for error in result.errors[:5]:
                console.print(f"  - {error}")

        return 0

    except Exception as e:
        console.print(f"[red]Error running data collection: {e}[/red]")
        logger.exception("Failed to run data collection")
        return 1


def _stats_data_collection(args: Namespace) -> int:
    """Show data collection statistics."""
    console = Console()

    try:
        # Load unified settings
        # Convert string path to Path if needed
        config_path = None
        if args.config:
            from pathlib import Path
            config_path = Path(args.config) if isinstance(args.config, str) else args.config
        
        unified_settings = load_settings(config_file=config_path)

        # Get data collection config
        dc_config = unified_settings.data_collection
        if dc_config is None:
            dc_config = DataCollectionConfig()

        # Load symbols - always load from database for data collection
        from dgas.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
                symbols = [row[0] for row in cur.fetchall()]

        # Create service
        legacy_settings = Settings()
        client = EODHDClient(EODHDConfig.from_settings(legacy_settings))
        service = DataCollectionService(dc_config, client=client)

        # Get freshness report
        console.print("[cyan]Generating data collection statistics...[/cyan]")
        freshness = service.get_freshness_report(symbols, dc_config.interval_market_hours)

        # Display statistics
        table = Table(title="Data Collection Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Symbols", str(freshness["total_symbols"]))
        table.add_row("Symbols with Data", str(freshness["symbols_with_data"]))
        if freshness["average_age_minutes"] is not None:
            table.add_row("Average Age", f"{freshness['average_age_minutes']:.1f} minutes")
            table.add_row("Min Age", f"{freshness['min_age_minutes']:.1f} minutes")
            table.add_row("Max Age", f"{freshness['max_age_minutes']:.1f} minutes")
        table.add_row("Stale Symbols (>60min)", str(freshness["stale_count"]))

        if freshness["stale_symbols"]:
            table.add_row("", "")
            table.add_row("Stale Symbols (sample)", "")
            for symbol, age in freshness["stale_symbols"][:10]:
                table.add_row(f"  {symbol}", f"{age:.1f} min" if age != float("inf") else "No data")

        console.print(table)
        return 0

    except Exception as e:
        console.print(f"[red]Error getting statistics: {e}[/red]")
        logger.exception("Failed to get data collection statistics")
        return 1


__all__ = ["setup_data_collection_parser"]
