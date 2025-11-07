"""
Status command for DGAS CLI.

Provides system health dashboard and operational status.
"""

from __future__ import annotations

import logging
import sys
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from pathlib import Path
from subprocess import run
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dgas.config import load_settings
from dgas.db import get_connection
from dgas.settings import Settings

logger = logging.getLogger(__name__)


def setup_status_parser(subparsers: Any) -> ArgumentParser:
    """
    Set up the status subcommand parser.

    Args:
        subparsers: The subparsers object from argparse

    Returns:
        The status subparser
    """
    parser = subparsers.add_parser(
        "status",
        help="Show system health and operational status",
        description="Display comprehensive system status dashboard",
    )

    parser.add_argument(
        "--format",
        choices=["dashboard", "json", "compact"],
        default="dashboard",
        help="Output format (default: dashboard)",
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )

    parser.set_defaults(func=_status_command)

    return parser


def _status_command(args: Namespace) -> int:
    """
    Execute the status command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load settings
        settings = load_settings(config_file=args.config)

        console.print("[cyan]Fetching system status...[/cyan]\n")

        # Gather status information
        status_info = _gather_status_info(settings)

        # Display based on format
        if args.format == "json":
            import json
            console.print(json.dumps(status_info, indent=2, default=str))
        elif args.format == "compact":
            _display_compact(console, status_info)
        else:  # dashboard
            _display_dashboard(console, status_info)

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Status command failed")
        return 1


def _gather_status_info(settings: Any) -> Dict[str, Any]:
    """
    Gather comprehensive status information.

    Args:
        settings: UnifiedSettings instance

    Returns:
        Dictionary containing all status information
    """
    info: Dict[str, Any] = {
        "timestamp": datetime.now(),
        "system": {},
        "database": {},
        "data": {},
        "predictions": {},
        "backtests": {},
        "scheduler": {},
        "config": {},
    }

    # System information
    info["system"] = {
        "python_version": sys.version,
        "platform": sys.platform,
        "uptime": _get_uptime(),
    }

    # Database status
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Total symbols
                cur.execute("SELECT COUNT(*) FROM market_symbols")
                info["database"]["total_symbols"] = cur.fetchone()[0]

                # Total data bars
                cur.execute("SELECT COUNT(*) FROM market_data")
                info["database"]["total_data_bars"] = cur.fetchone()[0]

                # Database size
                cur.execute(
                    """
                    SELECT pg_size_pretty(pg_database_size(current_database()))
                    """
                )
                info["database"]["size"] = cur.fetchone()[0]

                # Connection test
                info["database"]["status"] = "connected"
                info["database"]["connection_count"] = "N/A (requires pg_stat_activity)"
    except Exception as e:
        info["database"]["status"] = f"error: {e}"

    # Data coverage status
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Recent data
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT s.symbol)
                    FROM market_symbols s
                    JOIN market_data md ON md.symbol_id = s.symbol_id
                    WHERE md.timestamp > NOW() - INTERVAL '24 hours'
                    """
                )
                info["data"]["symbols_with_recent_data"] = cur.fetchone()[0] or 0

                # Oldest data
                cur.execute(
                    """
                    SELECT MIN(timestamp) FROM market_data
                    """
                )
                oldest = cur.fetchone()[0]
                info["data"]["oldest_data"] = oldest.isoformat() if oldest else "None"

                # Newest data
                cur.execute(
                    """
                    SELECT MAX(timestamp) FROM market_data
                    """
                )
                newest = cur.fetchone()[0]
                info["data"]["newest_data"] = newest.isoformat() if newest else "None"
    except Exception as e:
        info["data"]["error"] = str(e)

    # Prediction status
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Recent prediction runs
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM prediction_runs
                    WHERE timestamp > NOW() - INTERVAL '24 hours'
                    """
                )
                info["predictions"]["runs_last_24h"] = cur.fetchone()[0] or 0

                # Recent signals
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM prediction_signals ps
                    JOIN prediction_runs pr ON pr.run_id = ps.run_id
                    WHERE pr.timestamp > NOW() - INTERVAL '24 hours'
                    """
                )
                info["predictions"]["signals_last_24h"] = cur.fetchone()[0] or 0

                # Latest run
                cur.execute(
                    """
                    SELECT timestamp, symbols_processed, signals_generated
                    FROM prediction_runs
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if row:
                    info["predictions"]["latest_run"] = {
                        "timestamp": row[0].isoformat(),
                        "symbols": row[1],
                        "signals": row[2],
                    }
    except Exception as e:
        info["predictions"]["error"] = str(e)

    # Backtest status
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Total backtests
                cur.execute("SELECT COUNT(*) FROM backtest_results")
                info["backtests"]["total"] = cur.fetchone()[0] or 0

                # Recent backtests
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM backtest_results
                    WHERE completed_at > NOW() - INTERVAL '7 days'
                    """
                )
                info["backtests"]["last_7_days"] = cur.fetchone()[0] or 0

                # Best performer
                cur.execute(
                    """
                    SELECT br.strategy_name, s.symbol, br.total_return
                    FROM backtest_results br
                    JOIN market_symbols s ON s.symbol_id = br.symbol_id
                    ORDER BY br.total_return DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if row:
                    info["backtests"]["best_performer"] = {
                        "strategy": row[0],
                        "symbol": row[1],
                        "return": f"{float(row[2]):.2%}",
                    }
    except Exception as e:
        info["backtests"]["error"] = str(e)

    # Scheduler status
    info["scheduler"] = {
        "status": _check_scheduler_status(),
        "config": {
            "symbols": settings.scheduler_symbols,
            "cron": settings.scheduler_cron,
            "timezone": settings.scheduler_timezone,
        },
    }

    # Configuration
    info["config"] = {
        "source": "config file" if settings.has_config_file else "environment",
        "database_url": settings.database_url[:50] + "..." if len(settings.database_url) > 50 else settings.database_url,
        "symbols_configured": len(settings.scheduler_symbols),
    }

    return info


def _check_scheduler_status() -> Dict[str, Any]:
    """
    Check if scheduler daemon is running.

    Returns:
        Dictionary with status information
    """
    pid_file = Path(".dgas_scheduler.pid")

    if not pid_file.exists():
        return {"status": "not running", "pid_file": str(pid_file)}

    try:
        pid = int(pid_file.read_text().strip())
        # Check if process is running
        try:
            run(["kill", "-0", str(pid)], check=True, capture_output=True)
            return {"status": "running", "pid": pid, "pid_file": str(pid_file)}
        except Exception:
            return {"status": "stopped (stale pid file)", "pid": pid, "pid_file": str(pid_file)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _get_uptime() -> str:
    """
    Get system uptime.

    Returns:
        Uptime string
    """
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])

        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)

        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    except Exception:
        return "Unknown"


def _display_dashboard(console: Console, info: Dict[str, Any]) -> None:
    """
    Display status in dashboard format.

    Args:
        console: Rich console instance
        info: Status information dictionary
    """
    console.print(f"[bold]DGAS System Status Dashboard[/bold]", justify="center")
    console.print(f"Last updated: {info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}\n")

    # System panel
    sys_info = info["system"]
    console.print(
        Panel(
            f"Python: {sys_info['python_version'].split()[0]}\n"
            f"Platform: {sys_info['platform']}\n"
            f"Uptime: {sys_info['uptime']}",
            title="[bold]System[/bold]",
            border_style="cyan",
        )
    )

    # Database panel
    db_info = info["database"]
    console.print(
        Panel(
            f"Status: {db_info.get('status', 'unknown')}\n"
            f"Symbols: {db_info.get('total_symbols', 0):,}\n"
            f"Data bars: {db_info.get('total_data_bars', 0):,}\n"
            f"Size: {db_info.get('size', 'unknown')}",
            title="[bold]Database[/bold]",
            border_style="green" if "connected" in db_info.get("status", "") else "red",
        )
    )

    # Data panel
    data_info = info["data"]
    console.print(
        Panel(
            f"Symbols (24h): {data_info.get('symbols_with_recent_data', 0)}\n"
            f"Oldest: {data_info.get('oldest_data', 'None')}\n"
            f"Newest: {data_info.get('newest_data', 'None')}",
            title="[bold]Data Coverage[/bold]",
            border_style="blue",
        )
    )

    # Predictions panel
    pred_info = info["predictions"]
    latest = pred_info.get("latest_run")
    console.print(
        Panel(
            f"Runs (24h): {pred_info.get('runs_last_24h', 0)}\n"
            f"Signals (24h): {pred_info.get('signals_last_24h', 0)}\n"
            f"Latest: {latest['timestamp'] if latest else 'Never'}",
            title="[bold]Predictions[/bold]",
            border_style="magenta",
        )
    )

    # Backtests panel
    bt_info = info["backtests"]
    best = bt_info.get("best_performer")
    console.print(
        Panel(
            f"Total: {bt_info.get('total', 0)}\n"
            f"Last 7 days: {bt_info.get('last_7_days', 0)}\n"
            f"Best: {best['symbol']} ({best['return']})" if best else "No results",
            title="[bold]Backtests[/bold]",
            border_style="yellow",
        )
    )

    # Scheduler panel
    sched_info = info["scheduler"]
    status = sched_info.get("status", {})
    console.print(
        Panel(
            f"Status: {status.get('status', 'unknown')}\n"
            f"PID: {status.get('pid', 'N/A')}\n"
            f"Symbols: {len(sched_info['config']['symbols'])}\n"
            f"Schedule: {sched_info['config']['cron']}",
            title="[bold]Scheduler[/bold]",
            border_style="green" if status.get("status") == "running" else "yellow",
        )
    )

    # Configuration panel
    config_info = info["config"]
    console.print(
        Panel(
            f"Source: {config_info['source']}\n"
            f"DB URL: {config_info['database_url']}\n"
            f"Symbols: {config_info['symbols_configured']}",
            title="[bold]Configuration[/bold]",
            border_style="dim",
        )
    )

    # Summary table
    console.print("\n[bold]Summary:[/bold]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Component")
    table.add_column("Status")
    table.add_column("Details")

    # Add rows
    db_status = "✓" if "connected" in info["database"].get("status", "") else "✗"
    table.add_row("Database", db_status, f"{info['database'].get('total_symbols', 0)} symbols")

    pred_status = "✓" if info["predictions"].get("runs_last_24h", 0) > 0 else "○"
    table.add_row("Predictions", pred_status, f"{info['predictions'].get('signals_last_24h', 0)} signals (24h)")

    sched_status = "✓" if info["scheduler"]["status"].get("status") == "running" else "○"
    table.add_row("Scheduler", sched_status, f"{len(info['scheduler']['config']['symbols'])} symbols")

    config_status = "✓" if info["config"]["source"] == "config file" else "○"
    table.add_row("Configuration", config_status, info["config"]["source"])

    console.print(table)


def _display_compact(console: Console, info: Dict[str, Any]) -> None:
    """
    Display status in compact format.

    Args:
        console: Rich console instance
        info: Status information dictionary
    """
    console.print(f"DGAS Status - {info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")

    db = info["database"]
    console.print(f"DB: {db.get('status', '?')} | {db.get('total_symbols', 0)} symbols | {db.get('total_data_bars', 0):,} bars")

    pred = info["predictions"]
    console.print(f"Pred: {pred.get('runs_last_24h', 0)} runs, {pred.get('signals_last_24h', 0)} signals (24h)")

    sched_status = info["scheduler"]["status"].get("status", "?")
    console.print(f"Sched: {sched_status} | {len(info['scheduler']['config']['symbols'])} symbols")

    console.print(f"Config: {info['config']['source']} | {info['system']['uptime']} uptime")
