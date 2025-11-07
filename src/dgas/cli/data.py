"""
Data management command for DGAS CLI.

Provides data ingestion, listing, statistics, and cleanup operations.
"""

from __future__ import annotations

import logging
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List

from rich.console import Console
from rich.table import Table

from dgas.config import load_settings
from dgas.data.ingestion import (
    IngestionSummary,
    backfill_intraday,
    backfill_many,
    incremental_update_intraday,
)
from dgas.db import get_connection
from dgas.monitoring import generate_ingestion_report, render_markdown_report, write_report

logger = logging.getLogger(__name__)


def setup_data_parser(subparsers: Any) -> ArgumentParser:
    """
    Set up the data subcommand parser.

    Args:
        subparsers: The subparsers object from argparse

    Returns:
        The data subparser
    """
    parser = subparsers.add_parser(
        "data",
        help="Manage market data ingestion and storage",
        description="Ingest, list, analyze, and clean market data",
    )

    data_subparsers = parser.add_subparsers(dest="data_command")

    # Ingest command
    ingest_parser = data_subparsers.add_parser(
        "ingest",
        help="Ingest market data for symbols",
    )
    ingest_parser.add_argument(
        "symbols",
        nargs="+",
        help="Symbols to ingest (e.g., AAPL MSFT)",
    )
    ingest_parser.add_argument(
        "--exchange",
        default="US",
        help="Exchange code (default: US)",
    )
    ingest_parser.add_argument(
        "--interval",
        default="30min",
        help="Data interval (default: 30min)",
    )
    ingest_parser.add_argument(
        "--start-date",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    ingest_parser.add_argument(
        "--end-date",
        help="End date (YYYY-MM-DD, default: today)",
    )
    ingest_parser.add_argument(
        "--incremental",
        action="store_true",
        help="Use incremental update instead of backfill",
    )
    ingest_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    ingest_parser.set_defaults(func=_ingest_command)

    # List command
    list_parser = data_subparsers.add_parser(
        "list",
        help="List stored symbols and data ranges",
    )
    list_parser.add_argument(
        "--interval",
        default="30min",
        help="Filter by interval (default: 30min)",
    )
    list_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    list_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    list_parser.set_defaults(func=_list_command)

    # Stats command
    stats_parser = data_subparsers.add_parser(
        "stats",
        help="Show data quality statistics",
    )
    stats_parser.add_argument(
        "--interval",
        default="30min",
        help="Interval to analyze (default: 30min)",
    )
    stats_parser.add_argument(
        "--output",
        type=Path,
        help="Save report to file (Markdown)",
    )
    stats_parser.add_argument(
        "--format",
        choices=["table", "markdown", "json"],
        default="table",
        help="Output format (default: table)",
    )
    stats_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    stats_parser.set_defaults(func=_stats_command)

    # Clean command
    clean_parser = data_subparsers.add_parser(
        "clean",
        help="Clean old or duplicate data",
    )
    clean_parser.add_argument(
        "--symbol",
        help="Clean specific symbol (default: all)",
    )
    clean_parser.add_argument(
        "--interval",
        default="30min",
        help="Interval to clean (default: 30min)",
    )
    clean_parser.add_argument(
        "--older-than",
        type=int,
        help="Delete data older than N days",
    )
    clean_parser.add_argument(
        "--duplicates",
        action="store_true",
        help="Remove duplicate entries",
    )
    clean_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without deleting",
    )
    clean_parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )
    clean_parser.set_defaults(func=_clean_command)

    return parser


def _ingest_command(args: Namespace) -> int:
    """
    Execute the data ingest command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load settings
        settings = load_settings(config_file=args.config)

        # Prepare end date
        end_date = args.end_date or datetime.now().date().isoformat()

        console.print(f"[cyan]Ingesting data for {len(args.symbols)} symbols...[/cyan]")
        console.print(f"Exchange: {args.exchange}")
        console.print(f"Interval: {args.interval}")
        console.print(f"Date range: {args.start_date} to {end_date}")
        console.print(f"Mode: {'Incremental' if args.incremental else 'Backfill'}\n")

        summaries: List[IngestionSummary] = []

        if args.incremental:
            # Incremental update mode
            for symbol in args.symbols:
                try:
                    console.print(f"[cyan]Updating {symbol}...[/cyan]")
                    summary = incremental_update_intraday(
                        symbol,
                        exchange=args.exchange,
                        interval=args.interval,
                        default_start=args.start_date,
                    )
                    summaries.append(summary)
                    console.print(f"[green]✓ {symbol}: {summary.stored} bars stored[/green]")
                except Exception as e:
                    console.print(f"[red]✗ {symbol}: {e}[/red]")
                    logger.exception(f"Failed to update {symbol}")
        else:
            # Backfill mode
            symbol_exchange_pairs = [(sym, args.exchange) for sym in args.symbols]
            summaries = backfill_many(
                symbol_exchange_pairs,
                start_date=args.start_date,
                end_date=end_date,
                interval=args.interval,
            )

            # Display results
            for summary in summaries:
                console.print(
                    f"[green]✓ {summary.symbol}: {summary.stored} bars stored "
                    f"(fetched={summary.fetched}, gaps={summary.quality.gap_count})[/green]"
                )

        # Summary table
        console.print(f"\n[bold]Ingestion Summary:[/bold]")
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Symbol")
        table.add_column("Fetched", justify="right")
        table.add_column("Stored", justify="right")
        table.add_column("Duplicates", justify="right")
        table.add_column("Gaps", justify="right")

        for summary in summaries:
            table.add_row(
                summary.symbol,
                str(summary.fetched),
                str(summary.stored),
                str(summary.quality.duplicate_count),
                str(summary.quality.gap_count),
            )

        console.print(table)

        total_stored = sum(s.stored for s in summaries)
        console.print(f"\n[green]Total bars stored: {total_stored}[/green]")

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Ingest command failed")
        return 1


def _list_command(args: Namespace) -> int:
    """
    Execute the data list command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load settings
        settings = load_settings(config_file=args.config)

        # Query database for symbols
        query = """
            SELECT DISTINCT
                s.symbol,
                s.exchange,
                COUNT(md.data_id) as bar_count,
                MIN(md.timestamp) as first_timestamp,
                MAX(md.timestamp) as last_timestamp
            FROM market_symbols s
            LEFT JOIN market_data md
                ON md.symbol_id = s.symbol_id
                AND md.interval_type = %s
            GROUP BY s.symbol, s.exchange
            ORDER BY s.symbol;
        """

        results = []
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (args.interval,))
                results = cur.fetchall()

        if args.format == "json":
            import json

            output = [
                {
                    "symbol": row[0],
                    "exchange": row[1],
                    "bar_count": row[2],
                    "first_timestamp": row[3].isoformat() if row[3] else None,
                    "last_timestamp": row[4].isoformat() if row[4] else None,
                }
                for row in results
            ]
            console.print(json.dumps(output, indent=2))
        else:
            # Table format
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Symbol")
            table.add_column("Exchange")
            table.add_column("Bars", justify="right")
            table.add_column("First Timestamp")
            table.add_column("Last Timestamp")

            for row in results:
                symbol, exchange, bar_count, first_ts, last_ts = row
                table.add_row(
                    symbol,
                    exchange or "",
                    str(bar_count or 0),
                    first_ts.isoformat() if first_ts else "",
                    last_ts.isoformat() if last_ts else "",
                )

            console.print(table)
            console.print(f"\n[cyan]Total symbols: {len(results)}[/cyan]")

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("List command failed")
        return 1


def _stats_command(args: Namespace) -> int:
    """
    Execute the data stats command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load settings
        settings = load_settings(config_file=args.config)

        console.print(f"[cyan]Analyzing data quality for interval: {args.interval}[/cyan]\n")

        # Generate report
        stats = generate_ingestion_report(interval=args.interval)

        if args.format == "json":
            import json

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
        elif args.format == "markdown":
            markdown = render_markdown_report(stats)
            console.print(markdown)
        else:
            # Table format
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Symbol")
            table.add_column("Exchange")
            table.add_column("Bars", justify="right")
            table.add_column("Missing", justify="right")
            table.add_column("Coverage %", justify="right")
            table.add_column("First Timestamp")
            table.add_column("Last Timestamp")

            total_bars = 0
            total_missing = 0

            for s in stats:
                if s.bar_count > 0:
                    expected = s.bar_count + s.estimated_missing_bars
                    coverage = (s.bar_count / expected * 100) if expected > 0 else 0
                else:
                    coverage = 0

                table.add_row(
                    s.symbol,
                    s.exchange or "",
                    str(s.bar_count),
                    str(s.estimated_missing_bars),
                    f"{coverage:.1f}%",
                    s.first_timestamp.isoformat() if s.first_timestamp else "",
                    s.last_timestamp.isoformat() if s.last_timestamp else "",
                )

                total_bars += s.bar_count
                total_missing += s.estimated_missing_bars

            console.print(table)

            # Summary
            console.print(f"\n[bold]Summary:[/bold]")
            console.print(f"Total symbols: {len(stats)}")
            console.print(f"Total bars: {total_bars:,}")
            console.print(f"Estimated missing: {total_missing:,}")

            if total_bars + total_missing > 0:
                overall_coverage = total_bars / (total_bars + total_missing) * 100
                console.print(f"Overall coverage: {overall_coverage:.1f}%")

        # Save to file if requested
        if args.output:
            markdown = render_markdown_report(stats)
            write_report(stats, args.output)
            console.print(f"\n[green]Report saved to: {args.output}[/green]")

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Stats command failed")
        return 1


def _clean_command(args: Namespace) -> int:
    """
    Execute the data clean command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load settings
        settings = load_settings(config_file=args.config)

        if args.dry_run:
            console.print("[yellow]DRY RUN MODE - No data will be deleted[/yellow]\n")

        deleted_count = 0

        # Clean old data
        if args.older_than:
            cutoff_date = datetime.now() - timedelta(days=args.older_than)
            console.print(
                f"[cyan]Deleting data older than {args.older_than} days "
                f"(before {cutoff_date.date()})[/cyan]"
            )

            query = """
                DELETE FROM market_data
                WHERE interval_type = %s
                  AND timestamp < %s
            """

            params = [args.interval, cutoff_date]

            if args.symbol:
                query += """
                  AND symbol_id = (
                      SELECT symbol_id FROM market_symbols WHERE symbol = %s
                  )
                """
                params.append(args.symbol)

            if not args.dry_run:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(query, params)
                        deleted_count = cur.rowcount
                        conn.commit()
            else:
                # Dry run - count what would be deleted
                count_query = query.replace("DELETE", "SELECT COUNT(*)")
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(count_query, params)
                        deleted_count = cur.fetchone()[0]

            console.print(f"[green]{'Would delete' if args.dry_run else 'Deleted'} {deleted_count} bars[/green]")

        # Clean duplicates
        if args.duplicates:
            console.print("[cyan]Removing duplicate entries...[/cyan]")

            # Find and delete duplicates keeping the latest data_id
            query = """
                DELETE FROM market_data
                WHERE data_id IN (
                    SELECT data_id
                    FROM (
                        SELECT data_id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY symbol_id, interval_type, timestamp
                                   ORDER BY data_id DESC
                               ) as rn
                        FROM market_data
                        WHERE interval_type = %s
                    ) t
                    WHERE rn > 1
                )
            """

            params = [args.interval]

            if not args.dry_run:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(query, params)
                        dup_count = cur.rowcount
                        conn.commit()
            else:
                # Dry run - count duplicates
                count_query = """
                    SELECT COUNT(*)
                    FROM (
                        SELECT data_id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY symbol_id, interval_type, timestamp
                                   ORDER BY data_id DESC
                               ) as rn
                        FROM market_data
                        WHERE interval_type = %s
                    ) t
                    WHERE rn > 1
                """
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(count_query, params)
                        dup_count = cur.fetchone()[0]

            console.print(
                f"[green]{'Would remove' if args.dry_run else 'Removed'} {dup_count} duplicate entries[/green]"
            )

        if not args.older_than and not args.duplicates:
            console.print("[yellow]No cleanup action specified. Use --older-than or --duplicates[/yellow]")
            return 1

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Clean command failed")
        return 1
