"""Entry point for running the Drummond Geometry toolkit."""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from . import get_version
from .cli import run_analyze_command, run_backtest_command
from .monitoring import generate_ingestion_report, render_markdown_report, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dgas",
        description="Drummond Geometry Analysis System",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Display version information and exit.",
    )

    subparsers = parser.add_subparsers(dest="command")

    # Analyze command
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Perform Drummond Geometry analysis on market data",
    )
    analyze_parser.add_argument(
        "symbols",
        nargs="+",
        help="One or more symbols to analyze (e.g., AAPL MSFT)",
    )
    analyze_parser.add_argument(
        "--htf",
        "--higher-timeframe",
        dest="htf_interval",
        default="4h",
        help="Higher timeframe interval for trend direction (default: 4h)",
    )
    analyze_parser.add_argument(
        "--trading",
        "--trading-timeframe",
        dest="trading_interval",
        default="1h",
        help="Trading timeframe interval for entry signals (default: 1h)",
    )
    analyze_parser.add_argument(
        "--lookback",
        type=int,
        default=200,
        help="Number of bars to load for analysis (default: 200)",
    )
    analyze_parser.add_argument(
        "--save",
        action="store_true",
        help="Save analysis results to database",
    )
    analyze_parser.add_argument(
        "--format",
        choices=["summary", "detailed", "json"],
        default="summary",
        help="Output format (default: summary)",
    )

    # Backtest command
    backtest_parser = subparsers.add_parser(
        "backtest",
        help="Run historical backtests and optional reports",
    )
    backtest_parser.add_argument(
        "symbols",
        nargs="+",
        help="Symbols to backtest",
    )
    backtest_parser.add_argument(
        "--interval",
        default="1h",
        help="Interval to backtest (default: 1h)",
    )
    backtest_parser.add_argument(
        "--strategy",
        default="multi_timeframe",
        help="Strategy name registered with the backtesting engine",
    )
    backtest_parser.add_argument(
        "--strategy-param",
        action="append",
        dest="strategy_params",
        default=[],
        help="Strategy parameter override in key=value form (may be repeated)",
    )
    backtest_parser.add_argument("--start", help="Start date (YYYY-MM-DD) or ISO timestamp", default=None)
    backtest_parser.add_argument("--end", help="End date (YYYY-MM-DD) or ISO timestamp", default=None)
    backtest_parser.add_argument(
        "--initial-capital",
        type=Decimal,
        default=Decimal("100000"),
        help="Initial account capital",
    )
    backtest_parser.add_argument(
        "--commission-rate",
        type=Decimal,
        default=Decimal("0.0"),
        help="Commission rate applied per trade (decimal fraction)",
    )
    backtest_parser.add_argument(
        "--slippage-bps",
        type=Decimal,
        default=Decimal("0.0"),
        help="Slippage in basis points applied to entries/exits",
    )
    backtest_parser.add_argument(
        "--risk-free-rate",
        type=Decimal,
        default=Decimal("0.0"),
        help="Annual risk-free rate used for Sharpe/Sortino",
    )
    backtest_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not persist backtest results to the database",
    )
    backtest_parser.add_argument(
        "--output-format",
        choices=["summary", "detailed", "json"],
        default="summary",
        help="Console output format",
    )
    backtest_parser.add_argument(
        "--report",
        type=Path,
        help="Optional Markdown report output (file or directory)",
    )
    backtest_parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional JSON report output (file or directory)",
    )
    backtest_parser.add_argument(
        "--limit-bars",
        type=int,
        default=None,
        help="Limit number of most recent bars (for debugging)",
    )

    # Data report command
    report_parser = subparsers.add_parser(
        "data-report",
        help="Generate a data ingestion completeness report",
    )
    report_parser.add_argument(
        "--interval",
        default="30min",
        help="Interval type to analyse (default: 30min)",
    )
    report_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the report as Markdown",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"Drummond Geometry Analysis System {get_version()}")
        return 0

    if args.command == "analyze":
        return run_analyze_command(
            symbols=args.symbols,
            htf_interval=args.htf_interval,
            trading_interval=args.trading_interval,
            lookback_bars=args.lookback,
            save_to_db=args.save,
            output_format=args.format,
        )

    if args.command == "backtest":
        strategy_params = _parse_key_value_pairs(args.strategy_params)
        return run_backtest_command(
            symbols=args.symbols,
            interval=args.interval,
            strategy=args.strategy,
            strategy_params=strategy_params,
            start=args.start,
            end=args.end,
            initial_capital=args.initial_capital,
            commission_rate=args.commission_rate,
            slippage_bps=args.slippage_bps,
            risk_free_rate=args.risk_free_rate,
            persist=not args.no_save,
            output_format=args.output_format,
            report_path=args.report,
            json_path=args.json_output,
            limit_bars=args.limit_bars,
        )

    if args.command == "data-report":
        stats = generate_ingestion_report(interval=args.interval)
        report = render_markdown_report(stats)
        print(report)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_report(stats, args.output)
            print(f"\nReport written to {args.output}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _parse_key_value_pairs(items: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Strategy parameter must be key=value, got: {item}")
        key, value = item.split("=", 1)
        params[key] = value
    return params
