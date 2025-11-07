"""
Scheduler command for DGAS CLI.

Provides daemon lifecycle management for the prediction scheduler.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from argparse import ArgumentParser, Namespace
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from dgas.config import load_settings
from dgas.prediction import (
    MarketHoursManager,
    PredictionEngine,
    PredictionPersistence,
    PredictionScheduler,
    SchedulerConfig,
    TradingSession,
)
from dgas.prediction.monitoring import PerformanceTracker
from dgas.prediction.notifications import NotificationRouter
from dgas.settings import Settings

logger = logging.getLogger(__name__)


def setup_scheduler_parser(subparsers) -> ArgumentParser:
    """
    Set up the scheduler subcommand parser.

    Args:
        subparsers: The subparsers object from argparse

    Returns:
        The scheduler subparser
    """
    parser = subparsers.add_parser(
        "scheduler",
        help="Manage the prediction scheduler daemon",
        description="Start, stop, and monitor the prediction scheduler",
    )

    scheduler_subparsers = parser.add_subparsers(dest="scheduler_command")

    # Start command
    start_parser = scheduler_subparsers.add_parser(
        "start",
        help="Start the scheduler daemon",
    )
    start_parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as background daemon (default: foreground)",
    )
    start_parser.add_argument(
        "--pid-file",
        type=Path,
        default=Path(".dgas_scheduler.pid"),
        help="Path to PID file (default: .dgas_scheduler.pid)",
    )
    start_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    start_parser.set_defaults(func=_start_scheduler)

    # Stop command
    stop_parser = scheduler_subparsers.add_parser(
        "stop",
        help="Stop the scheduler daemon",
    )
    stop_parser.add_argument(
        "--pid-file",
        type=Path,
        default=Path(".dgas_scheduler.pid"),
        help="Path to PID file (default: .dgas_scheduler.pid)",
    )
    stop_parser.add_argument(
        "--force",
        action="store_true",
        help="Force kill if graceful shutdown fails",
    )
    stop_parser.set_defaults(func=_stop_scheduler)

    # Status command
    status_parser = scheduler_subparsers.add_parser(
        "status",
        help="Check scheduler daemon status",
    )
    status_parser.add_argument(
        "--pid-file",
        type=Path,
        default=Path(".dgas_scheduler.pid"),
        help="Path to PID file (default: .dgas_scheduler.pid)",
    )
    status_parser.set_defaults(func=_status_scheduler)

    # Restart command
    restart_parser = scheduler_subparsers.add_parser(
        "restart",
        help="Restart the scheduler daemon",
    )
    restart_parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as background daemon (default: foreground)",
    )
    restart_parser.add_argument(
        "--pid-file",
        type=Path,
        default=Path(".dgas_scheduler.pid"),
        help="Path to PID file (default: .dgas_scheduler.pid)",
    )
    restart_parser.set_defaults(func=_restart_scheduler)

    return parser


def _start_scheduler(args: Namespace) -> int:
    """
    Start the scheduler daemon.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    # Check if already running
    if _is_running(args.pid_file):
        console.print("[yellow]Scheduler is already running[/yellow]")
        return 1

    try:
        if args.daemon:
            # Fork to background
            console.print("[cyan]Starting scheduler as daemon...[/cyan]")
            _daemonize(args.pid_file)

        # Write PID file
        _write_pid_file(args.pid_file)

        # Set up signal handlers
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        # Load unified settings
        unified_settings = load_settings(config_file=args.config)

        # Initialize components (using legacy Settings for now)
        legacy_settings = Settings()
        persistence = PredictionPersistence(legacy_settings)
        engine = PredictionEngine(legacy_settings)
        performance_tracker = PerformanceTracker(persistence)

        # Create scheduler config from unified settings
        config = SchedulerConfig(
            prediction_symbols=unified_settings.scheduler_symbols or ["AAPL", "MSFT", "GOOGL"],
            cron_expression=unified_settings.scheduler_cron,
            timezone=unified_settings.scheduler_timezone,
            market_hours_only=unified_settings.scheduler_market_hours_only,
            trading_sessions=[
                TradingSession(
                    name="US_REGULAR",
                    start_time="09:30",
                    end_time="16:00",
                    days=[0, 1, 2, 3, 4],  # Mon-Fri
                )
            ],
        )

        # Create scheduler
        scheduler = PredictionScheduler(
            config=config,
            engine=engine,
            persistence=persistence,
            settings=settings,
            performance_tracker=performance_tracker,
        )

        # Start scheduler
        console.print("[green]Scheduler started successfully[/green]")
        console.print(f"PID file: {args.pid_file.absolute()}")

        scheduler.start()

        # Keep running (foreground mode)
        if not args.daemon:
            console.print("\n[cyan]Press Ctrl+C to stop scheduler[/cyan]\n")
            try:
                while scheduler.is_running():
                    time.sleep(1)
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping scheduler...[/yellow]")
                scheduler.stop()
                console.print("[green]Scheduler stopped[/green]")

        return 0

    except Exception as e:
        console.print(f"[red]Error starting scheduler: {e}[/red]")
        logger.exception("Failed to start scheduler")
        _cleanup_pid_file(args.pid_file)
        return 1


def _stop_scheduler(args: Namespace) -> int:
    """
    Stop the scheduler daemon.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    # Check if running
    pid = _read_pid_file(args.pid_file)
    if pid is None:
        console.print("[yellow]Scheduler is not running[/yellow]")
        return 1

    # Check if process exists
    if not _process_exists(pid):
        console.print("[yellow]Scheduler process not found (stale PID file)[/yellow]")
        _cleanup_pid_file(args.pid_file)
        return 1

    try:
        # Try graceful shutdown first
        console.print(f"[cyan]Stopping scheduler (PID {pid})...[/cyan]")
        os.kill(pid, signal.SIGTERM)

        # Wait for graceful shutdown (max 10 seconds)
        for _ in range(10):
            if not _process_exists(pid):
                console.print("[green]Scheduler stopped successfully[/green]")
                _cleanup_pid_file(args.pid_file)
                return 0
            time.sleep(1)

        # Force kill if requested
        if args.force:
            console.print("[yellow]Graceful shutdown failed, forcing kill...[/yellow]")
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)

            if not _process_exists(pid):
                console.print("[green]Scheduler killed successfully[/green]")
                _cleanup_pid_file(args.pid_file)
                return 0

        console.print("[red]Failed to stop scheduler (use --force to kill)[/red]")
        return 1

    except ProcessLookupError:
        console.print("[yellow]Scheduler process not found[/yellow]")
        _cleanup_pid_file(args.pid_file)
        return 0
    except PermissionError:
        console.print("[red]Permission denied (cannot stop scheduler)[/red]")
        return 1
    except Exception as e:
        console.print(f"[red]Error stopping scheduler: {e}[/red]")
        logger.exception("Failed to stop scheduler")
        return 1


def _status_scheduler(args: Namespace) -> int:
    """
    Check scheduler daemon status.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 if running, 1 if not running)
    """
    console = Console()

    pid = _read_pid_file(args.pid_file)

    if pid is None:
        console.print("[yellow]Status:[/yellow] [red]Not running[/red]")
        console.print(f"PID file: {args.pid_file.absolute()} (not found)")
        return 1

    if not _process_exists(pid):
        console.print("[yellow]Status:[/yellow] [red]Not running[/red] (stale PID file)")
        console.print(f"PID file: {args.pid_file.absolute()}")
        console.print(f"PID: {pid} (process not found)")
        return 1

    # Get process info
    try:
        import psutil
        process = psutil.Process(pid)
        uptime = datetime.now() - datetime.fromtimestamp(process.create_time())

        console.print("[yellow]Status:[/yellow] [green]Running[/green]")
        console.print(f"PID: {pid}")
        console.print(f"Uptime: {_format_uptime(uptime.total_seconds())}")
        console.print(f"CPU: {process.cpu_percent()}%")
        console.print(f"Memory: {process.memory_info().rss / 1024 / 1024:.1f} MB")
        console.print(f"PID file: {args.pid_file.absolute()}")

    except ImportError:
        # psutil not available, just show basic info
        console.print("[yellow]Status:[/yellow] [green]Running[/green]")
        console.print(f"PID: {pid}")
        console.print(f"PID file: {args.pid_file.absolute()}")

    except Exception as e:
        console.print(f"[yellow]Warning: Could not get process details: {e}[/yellow]")
        console.print("[yellow]Status:[/yellow] [green]Running[/green]")
        console.print(f"PID: {pid}")

    return 0


def _restart_scheduler(args: Namespace) -> int:
    """
    Restart the scheduler daemon.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    # Stop if running
    if _is_running(args.pid_file):
        console.print("[cyan]Stopping scheduler...[/cyan]")
        stop_args = Namespace(pid_file=args.pid_file, force=True)
        result = _stop_scheduler(stop_args)
        if result != 0:
            console.print("[red]Failed to stop scheduler[/red]")
            return result

        # Wait for shutdown
        time.sleep(2)

    # Start
    console.print("[cyan]Starting scheduler...[/cyan]")
    return _start_scheduler(args)


# Helper functions

def _is_running(pid_file: Path) -> bool:
    """Check if scheduler is running."""
    pid = _read_pid_file(pid_file)
    return pid is not None and _process_exists(pid)


def _read_pid_file(pid_file: Path) -> Optional[int]:
    """Read PID from file."""
    if not pid_file.exists():
        return None

    try:
        with open(pid_file, "r") as f:
            return int(f.read().strip())
    except (ValueError, IOError):
        return None


def _write_pid_file(pid_file: Path) -> None:
    """Write current PID to file."""
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))


def _cleanup_pid_file(pid_file: Path) -> None:
    """Remove PID file."""
    if pid_file.exists():
        try:
            pid_file.unlink()
        except Exception:
            pass


def _process_exists(pid: int) -> bool:
    """Check if process with given PID exists."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _daemonize(pid_file: Path) -> None:
    """
    Fork process to background daemon.

    This is a simplified daemonization - for production use,
    consider using a proper daemon library like python-daemon.
    """
    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent process exits
            sys.exit(0)
    except OSError as e:
        raise RuntimeError(f"Fork #1 failed: {e}")

    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Second parent exits
            sys.exit(0)
    except OSError as e:
        raise RuntimeError(f"Fork #2 failed: {e}")

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    with open("/dev/null", "r") as f:
        os.dup2(f.fileno(), sys.stdin.fileno())

    with open("/dev/null", "a+") as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    # The scheduler's shutdown will be handled by the main loop
    sys.exit(0)


def _format_uptime(seconds: float) -> str:
    """Format uptime seconds into human-readable string."""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)
