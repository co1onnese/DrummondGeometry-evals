"""
Report generation command for DGAS CLI.

Provides comprehensive reporting for backtests, predictions, and system monitoring.
"""

from __future__ import annotations

import json
import logging
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from dgas.config import load_settings
from dgas.db import get_connection
from dgas.monitoring import generate_ingestion_report, render_markdown_report, write_report
from dgas.settings import Settings

logger = logging.getLogger(__name__)


def setup_report_parser(subparsers: Any) -> ArgumentParser:
    """
    Set up the report subcommand parser.

    Args:
        subparsers: The subparsers object from argparse

    Returns:
        The report subparser
    """
    parser = subparsers.add_parser(
        "report",
        help="Generate comprehensive reports",
        description="Create reports for backtests, predictions, and system monitoring",
    )

    report_subparsers = parser.add_subparsers(dest="report_command")

    # Backtest report command
    backtest_parser = report_subparsers.add_parser(
        "backtest",
        help="Generate backtest performance report",
    )
    backtest_parser.add_argument(
        "--run-id",
        type=int,
        help="Specific backtest run ID (default: latest)",
    )
    backtest_parser.add_argument(
        "--symbol",
        help="Filter by symbol",
    )
    backtest_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent runs to include (default: 10)",
    )
    backtest_parser.add_argument(
        "--output",
        type=Path,
        help="Save report to file (Markdown)",
    )
    backtest_parser.add_argument(
        "--format",
        choices=["table", "markdown", "json"],
        default="table",
        help="Output format (default: table)",
    )
    backtest_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    backtest_parser.set_defaults(func=_backtest_report_command)

    # Prediction report command
    prediction_parser = report_subparsers.add_parser(
        "prediction",
        help="Generate prediction performance report",
    )
    prediction_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)",
    )
    prediction_parser.add_argument(
        "--symbol",
        help="Filter by symbol",
    )
    prediction_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum confidence threshold (default: 0.0)",
    )
    prediction_parser.add_argument(
        "--output",
        type=Path,
        help="Save report to file (Markdown)",
    )
    prediction_parser.add_argument(
        "--format",
        choices=["table", "markdown", "json"],
        default="table",
        help="Output format (default: table)",
    )
    prediction_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    prediction_parser.set_defaults(func=_prediction_report_command)

    # Data quality report command
    quality_parser = report_subparsers.add_parser(
        "data-quality",
        help="Generate data quality and coverage report",
    )
    quality_parser.add_argument(
        "--interval",
        default="30min",
        help="Interval to analyze (default: 30min)",
    )
    quality_parser.add_argument(
        "--output",
        type=Path,
        help="Save report to file (Markdown)",
    )
    quality_parser.add_argument(
        "--format",
        choices=["table", "markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    quality_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    quality_parser.set_defaults(func=_quality_report_command)

    return parser


def _backtest_report_command(args: Namespace) -> int:
    """
    Execute the backtest report command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load settings
        settings = load_settings(config_file=args.config)
        legacy_settings = Settings()

        console.print("[cyan]Generating backtest performance report...[/cyan]\n")

        if args.run_id:
            # Get specific run
            query = """
                SELECT br.backtest_id, br.strategy_name, s.symbol, br.start_date, br.end_date,
                       br.initial_capital, br.final_capital, br.total_return, br.sharpe_ratio,
                       br.max_drawdown, br.win_rate, br.total_trades, br.completed_at
                FROM backtest_results br
                JOIN market_symbols s ON s.symbol_id = br.symbol_id
                WHERE br.backtest_id = %s
            """
            params = [args.run_id]

            runs = []
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    row = cur.fetchone()
                    if row:
                        runs.append({
                            "run_id": row[0],
                            "strategy_name": row[1],
                            "symbol": row[2],
                            "start_date": row[3],
                            "end_date": row[4],
                            "interval": "1d",
                            "initial_capital": row[5],
                            "final_capital": row[6],
                            "total_return": row[7],
                            "sharpe_ratio": row[8],
                            "max_drawdown": row[9],
                            "win_rate": row[10],
                            "total_trades": row[11],
                            "created_at": row[12],
                        })
        else:
            # Get recent runs
            query = """
                SELECT br.backtest_id, br.strategy_name, s.symbol, br.start_date, br.end_date,
                       br.initial_capital, br.final_capital, br.total_return, br.sharpe_ratio,
                       br.max_drawdown, br.win_rate, br.total_trades, br.completed_at
                FROM backtest_results br
                JOIN market_symbols s ON s.symbol_id = br.symbol_id
                ORDER BY br.completed_at DESC
                LIMIT %s
            """
            params = [args.limit]

            if args.symbol:
                query = query.replace("ORDER BY", "WHERE s.symbol = %s ORDER BY")
                params = [args.symbol, args.limit]

            runs = []
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    for row in cur.fetchall():
                        runs.append({
                            "run_id": row[0],
                            "strategy_name": row[1],
                            "symbol": row[2],
                            "start_date": row[3],
                            "end_date": row[4],
                            "interval": "1d",
                            "initial_capital": row[5],
                            "final_capital": row[6],
                            "total_return": row[7],
                            "sharpe_ratio": row[8],
                            "max_drawdown": row[9],
                            "win_rate": row[10],
                            "total_trades": row[11],
                            "created_at": row[12],
                        })

        if not runs:
            console.print("[yellow]No backtest runs found[/yellow]")
            return 0

        # Display results
        if args.format == "json":
            output = [
                {
                    "run_id": r.get("run_id"),
                    "strategy": r.get("strategy_name"),
                    "symbol": r.get("symbol"),
                    "interval": r.get("interval"),
                    "total_return": float(r.get("total_return", 0)),
                    "sharpe_ratio": float(r.get("sharpe_ratio", 0)) if r.get("sharpe_ratio") else None,
                    "max_drawdown": float(r.get("max_drawdown", 0)),
                    "win_rate": float(r.get("win_rate", 0)),
                    "total_trades": r.get("total_trades"),
                    "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
                }
                for r in runs
            ]
            console.print(json.dumps(output, indent=2))
        elif args.format == "markdown":
            # Generate markdown report
            lines = ["# Backtest Performance Report", ""]
            lines.append(f"Generated: {datetime.now().isoformat()}")
            lines.append("")

            for run in runs:
                lines.append(f"## Run {run['run_id']}: {run['symbol']} ({run['strategy_name']})")
                lines.append("")
                lines.append(f"- **Period**: {run['start_date']} to {run['end_date']}")
                lines.append(f"- **Interval**: {run['interval']}")
                lines.append(f"- **Initial Capital**: ${run['initial_capital']:,.2f}")
                lines.append(f"- **Final Capital**: ${run['final_capital']:,.2f}")
                lines.append(f"- **Total Return**: {run['total_return']:.2%}")
                if run['sharpe_ratio']:
                    lines.append(f"- **Sharpe Ratio**: {run['sharpe_ratio']:.2f}")
                lines.append(f"- **Max Drawdown**: {run['max_drawdown']:.2%}")
                lines.append(f"- **Win Rate**: {run['win_rate']:.1%}")
                lines.append(f"- **Total Trades**: {run['total_trades']}")
                lines.append("")

            markdown = "\n".join(lines)
            console.print(markdown)

            if args.output:
                args.output.write_text(markdown)
                console.print(f"\n[green]Report saved to: {args.output}[/green]")
        else:
            # Table format
            table = Table(show_header=True, header_style="bold cyan", title="Backtest Performance")
            table.add_column("Run ID", justify="right")
            table.add_column("Symbol")
            table.add_column("Strategy")
            table.add_column("Return", justify="right")
            table.add_column("Sharpe", justify="right")
            table.add_column("Max DD", justify="right")
            table.add_column("Win Rate", justify="right")
            table.add_column("Trades", justify="right")

            for run in runs:
                table.add_row(
                    str(run["run_id"]),
                    run["symbol"],
                    run["strategy_name"],
                    f"{run['total_return']:.1%}",
                    f"{run['sharpe_ratio']:.2f}" if run['sharpe_ratio'] else "N/A",
                    f"{run['max_drawdown']:.1%}",
                    f"{run['win_rate']:.0%}",
                    str(run["total_trades"]),
                )

            console.print(table)

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Backtest report command failed")
        return 1


def _prediction_report_command(args: Namespace) -> int:
    """
    Execute the prediction report command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load settings
        settings = load_settings(config_file=args.config)
        legacy_settings = Settings()

        console.print(f"[cyan]Generating prediction report for last {args.days} days...[/cyan]\n")

        # Query prediction runs and signals
        since = datetime.now() - timedelta(days=args.days)

        query = """
            SELECT
                pr.run_id,
                pr.run_timestamp,
                pr.symbols_processed,
                pr.signals_generated,
                pr.execution_time_ms,
                COUNT(ps.signal_id) as signal_count
            FROM prediction_runs pr
            LEFT JOIN generated_signals ps ON ps.run_id = pr.run_id
            WHERE pr.run_timestamp >= %s
            GROUP BY pr.run_id, pr.run_timestamp, pr.symbols_processed, pr.signals_generated, pr.execution_time_ms
            ORDER BY pr.run_timestamp DESC
        """

        runs = []
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, [since])
                runs = cur.fetchall()

        # Query signals
        signal_query = """
            SELECT
                s.symbol,
                ps.signal_type,
                ps.confidence,
                ps.entry_price,
                ps.target_price,
                ps.stop_loss,
                ps.signal_timestamp
            FROM generated_signals ps
            JOIN prediction_runs pr ON pr.run_id = ps.run_id
            JOIN market_symbols s ON s.symbol_id = ps.symbol_id
            WHERE pr.run_timestamp >= %s
              AND ps.confidence >= %s
        """
        params = [since, args.min_confidence]

        if args.symbol:
            signal_query += " AND s.symbol = %s"
            params.append(args.symbol)

        signal_query += " ORDER BY ps.signal_timestamp DESC LIMIT 50"

        signals = []
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(signal_query, params)
                signals = cur.fetchall()

        # Display results
        if args.format == "json":
            output = {
                "period_days": args.days,
                "total_runs": len(runs),
                "total_signals": sum(r[5] for r in runs),
                "runs": [
                    {
                        "run_id": r[0],
                        "timestamp": r[1].isoformat(),
                        "symbols_processed": r[2],
                        "signals_generated": r[3],
                        "execution_time_ms": r[4],
                    }
                    for r in runs
                ],
                "recent_signals": [
                    {
                        "symbol": s[0],
                        "type": s[1],
                        "confidence": float(s[2]),
                        "entry_price": float(s[3]),
                        "target_price": float(s[4]),
                        "stop_loss": float(s[5]),
                        "timestamp": s[6].isoformat(),
                    }
                    for s in signals
                ],
            }
            console.print(json.dumps(output, indent=2))
        elif args.format == "markdown":
            lines = ["# Prediction Performance Report", ""]
            lines.append(f"Period: Last {args.days} days")
            lines.append(f"Generated: {datetime.now().isoformat()}")
            lines.append("")
            lines.append("## Summary")
            lines.append(f"- Total prediction runs: {len(runs)}")
            lines.append(f"- Total signals generated: {sum(r[5] for r in runs)}")
            if runs:
                avg_exec = sum(r[4] for r in runs) / len(runs)
                lines.append(f"- Average execution time: {avg_exec:.0f}ms")
            lines.append("")

            if signals:
                lines.append("## Recent Signals")
                lines.append("")
                lines.append("| Symbol | Type | Confidence | Entry | Target | Stop | Timestamp |")
                lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- |")
                for s in signals[:20]:  # Top 20
                    lines.append(
                        f"| {s[0]} | {s[1]} | {float(s[2]):.1%} | ${float(s[3]):.2f} | "
                        f"${float(s[4]):.2f} | ${float(s[5]):.2f} | {s[6].isoformat()} |"
                    )

            markdown = "\n".join(lines)
            console.print(markdown)

            if args.output:
                args.output.write_text(markdown)
                console.print(f"\n[green]Report saved to: {args.output}[/green]")
        else:
            # Table format
            console.print("[bold]Prediction Runs Summary:[/bold]")
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Run ID", justify="right")
            table.add_column("Timestamp")
            table.add_column("Symbols", justify="right")
            table.add_column("Signals", justify="right")
            table.add_column("Exec Time", justify="right")

            for r in runs[:10]:  # Top 10
                table.add_row(
                    str(r[0]),
                    r[1].strftime("%Y-%m-%d %H:%M"),
                    str(r[2]),
                    str(r[3]),
                    f"{r[4]}ms",
                )

            console.print(table)

            if signals:
                console.print("\n[bold]Recent Signals:[/bold]")
                sig_table = Table(show_header=True, header_style="bold cyan")
                sig_table.add_column("Symbol")
                sig_table.add_column("Type")
                sig_table.add_column("Confidence", justify="right")
                sig_table.add_column("Entry", justify="right")
                sig_table.add_column("Target", justify="right")
                sig_table.add_column("Timestamp")

                for s in signals[:15]:  # Top 15
                    sig_table.add_row(
                        s[0],
                        s[1],
                        f"{float(s[2]):.1%}",
                        f"${float(s[3]):.2f}",
                        f"${float(s[4]):.2f}",
                        s[6].strftime("%Y-%m-%d %H:%M"),
                    )

                console.print(sig_table)

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Prediction report command failed")
        return 1


def _quality_report_command(args: Namespace) -> int:
    """
    Execute the data quality report command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load settings
        settings = load_settings(config_file=args.config)

        console.print(f"[cyan]Generating data quality report for interval: {args.interval}[/cyan]\n")

        # Generate report using existing function
        stats = generate_ingestion_report(interval=args.interval)

        if args.format == "json":
            output = [
                {
                    "symbol": s.symbol,
                    "exchange": s.exchange,
                    "interval": s.interval,
                    "bar_count": s.bar_count,
                    "first_timestamp": s.first_timestamp.isoformat() if s.first_timestamp else None,
                    "last_timestamp": s.last_timestamp.isoformat() if s.last_timestamp else None,
                    "estimated_missing_bars": s.estimated_missing_bars,
                }
                for s in stats
            ]
            console.print(json.dumps(output, indent=2))
        else:
            # Markdown format (default for this command)
            markdown = render_markdown_report(stats)
            console.print(markdown)

            if args.output:
                write_report(stats, args.output)
                console.print(f"\n[green]Report saved to: {args.output}[/green]")

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Quality report command failed")
        return 1
