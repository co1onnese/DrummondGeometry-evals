"""
Prediction command for DGAS CLI.

Provides manual signal generation with flexible output formats.
"""

from __future__ import annotations

import json
import logging
from argparse import ArgumentParser, Namespace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table

from dgas.config import load_settings
from dgas.prediction import PredictionEngine, PredictionPersistence
from dgas.prediction.notifications import NotificationRouter
from dgas.settings import Settings

logger = logging.getLogger(__name__)


def setup_predict_parser(subparsers: Any) -> ArgumentParser:
    """
    Set up the predict subcommand parser.

    Args:
        subparsers: The subparsers object from argparse

    Returns:
        The predict subparser
    """
    parser = subparsers.add_parser(
        "predict",
        help="Generate trading signals for specified symbols",
        description="Run the prediction engine to generate trading signals",
    )

    parser.add_argument(
        "symbols",
        nargs="*",
        help="Symbols to analyze (e.g., AAPL MSFT). If not provided, uses watchlist from config",
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["summary", "detailed", "json"],
        default="summary",
        help="Output format (default: summary)",
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Save signals to database",
    )

    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send notifications for generated signals",
    )

    parser.add_argument(
        "--watchlist",
        help="Path to file containing symbols (one per line)",
    )

    parser.add_argument(
        "--min-confidence",
        type=float,
        help="Minimum confidence threshold (default: from config or 0.6)",
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: auto-detect)",
    )

    parser.set_defaults(func=run_predict_command)

    return parser


def run_predict_command(args: Namespace) -> int:
    """
    Execute the predict command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load unified settings (config file + environment + overrides)
        config_overrides = {}
        if args.min_confidence is not None:
            config_overrides["min_confidence"] = args.min_confidence

        config_file = getattr(args, 'config', None)
        settings = load_settings(config_file=config_file, **config_overrides)

        # Show config source
        if settings.has_config_file:
            console.print(f"[dim]Using configuration file[/dim]")

        # Determine symbols to analyze
        symbols = _get_symbols(args, settings, console)
        if not symbols:
            console.print("[red]Error: No symbols specified[/red]")
            console.print("Provide symbols as arguments, use --watchlist, or configure default watchlist")
            return 1

        # Initialize components (legacy Settings for now)
        legacy_settings = Settings()
        persistence = PredictionPersistence(legacy_settings)
        engine = PredictionEngine(legacy_settings)

        # Run prediction
        console.print(f"[cyan]Running prediction for {len(symbols)} symbols...[/cyan]")
        result = engine.run(symbols)

        # Get min confidence from unified settings
        min_confidence = settings.prediction_min_confidence

        # Filter signals by confidence
        filtered_signals = [
            s for s in result.signals
            if s.confidence >= min_confidence
        ]

        # Save to database if requested
        run_id: Optional[int] = None
        if args.save:
            run_id = persistence.save_prediction_run(
                timestamp=datetime.now(),
                symbols=symbols,
                signals_generated=len(filtered_signals),
                execution_time_ms=result.execution_time_ms,
                data_fetch_ms=result.data_fetch_ms,
                indicator_calc_ms=result.indicator_calc_ms,
                signal_generation_ms=result.signal_generation_ms,
                errors=result.errors,
            )

            for signal in filtered_signals:
                persistence.save_signal(signal, run_id)

            console.print(f"[green]Saved to database (run_id={run_id})[/green]")

        # Send notifications if requested
        if args.notify and filtered_signals:
            router = NotificationRouter(settings)
            notification_errors = router.send_signals(filtered_signals)

            if notification_errors:
                console.print(f"[yellow]Warning: {len(notification_errors)} notification errors[/yellow]")
                for error in notification_errors:
                    logger.warning(f"Notification error: {error}")
            else:
                console.print(f"[green]Sent {len(filtered_signals)} notifications[/green]")

        # Display results
        _display_results(
            console=console,
            result=result,
            signals=filtered_signals,
            format_type=args.format,
            min_confidence=min_confidence,
        )

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Prediction command failed")
        return 1


def _get_symbols(args: Namespace, settings: Any, console: Console) -> List[str]:
    """
    Determine which symbols to analyze.

    Priority:
    1. Command line symbols (if provided)
    2. Watchlist file (if --watchlist provided)
    3. Default watchlist from settings

    Args:
        args: Parsed command line arguments
        settings: Application settings
        console: Rich console for output

    Returns:
        List of symbols to analyze
    """
    # Command line symbols
    if args.symbols:
        return [s.upper() for s in args.symbols]

    # Watchlist file
    if args.watchlist:
        try:
            with open(args.watchlist, "r") as f:
                symbols = [line.strip().upper() for line in f if line.strip()]
            console.print(f"[cyan]Loaded {len(symbols)} symbols from {args.watchlist}[/cyan]")
            return symbols
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load watchlist: {e}[/yellow]")

    # Default watchlist from settings
    if hasattr(settings, "scheduler_symbols") and settings.scheduler_symbols:
        return settings.scheduler_symbols
    elif hasattr(settings, "default_watchlist") and settings.default_watchlist:
        return settings.default_watchlist

    return []


def _display_results(
    console: Console,
    result: Any,
    signals: List[Any],
    format_type: str,
    min_confidence: float,
) -> None:
    """
    Display prediction results in the requested format.

    Args:
        console: Rich console for output
        result: PredictionRunResult from engine
        signals: Filtered list of signals to display
        format_type: Output format (summary, detailed, json)
        min_confidence: Minimum confidence threshold used
    """
    if format_type == "json":
        _display_json(console, result, signals)
    elif format_type == "detailed":
        _display_detailed(console, result, signals, min_confidence)
    else:  # summary
        _display_summary(console, result, signals, min_confidence)


def _display_summary(
    console: Console,
    result: Any,
    signals: List[Any],
    min_confidence: float,
) -> None:
    """Display results in summary format."""
    console.print("\n[bold]Prediction Summary[/bold]")
    console.print(f"Symbols processed: {result.symbols_processed}")
    console.print(f"Signals generated: {len(signals)} (confidence >= {min_confidence})")
    console.print(f"Execution time: {result.execution_time_ms}ms")

    if result.errors:
        console.print(f"[yellow]Errors: {len(result.errors)}[/yellow]")

    if signals:
        console.print("\n[bold]Generated Signals:[/bold]")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Symbol")
        table.add_column("Type")
        table.add_column("Confidence")
        table.add_column("Entry")
        table.add_column("Target")
        table.add_column("Stop")

        for signal in signals:
            table.add_row(
                signal.symbol,
                signal.signal_type.value,
                f"{signal.confidence:.2%}",
                f"${signal.entry_price:.2f}",
                f"${signal.target_price:.2f}",
                f"${signal.stop_loss:.2f}",
            )

        console.print(table)
    else:
        console.print("\n[yellow]No signals generated above confidence threshold[/yellow]")


def _display_detailed(
    console: Console,
    result: Any,
    signals: List[Any],
    min_confidence: float,
) -> None:
    """Display results in detailed format."""
    # Show summary first
    _display_summary(console, result, signals, min_confidence)

    # Add detailed timing breakdown
    console.print("\n[bold]Timing Breakdown:[/bold]")
    console.print(f"Data fetch: {result.data_fetch_ms}ms")
    console.print(f"Indicator calculation: {result.indicator_calc_ms}ms")
    console.print(f"Signal generation: {result.signal_generation_ms}ms")

    # Show detailed signal information
    if signals:
        console.print("\n[bold]Detailed Signal Information:[/bold]")

        for i, signal in enumerate(signals, 1):
            console.print(f"\n[cyan]Signal {i}: {signal.symbol}[/cyan]")
            console.print(f"  Type: {signal.signal_type.value}")
            console.print(f"  Confidence: {signal.confidence:.2%}")
            console.print(f"  Entry: ${signal.entry_price:.2f}")
            console.print(f"  Target: ${signal.target_price:.2f} ({_calc_pct(float(signal.entry_price), float(signal.target_price)):+.2%})")
            console.print(f"  Stop: ${signal.stop_loss:.2f} ({_calc_pct(float(signal.entry_price), float(signal.stop_loss)):+.2%})")
            console.print(f"  HTF: {signal.htf_timeframe} ({signal.htf_trend.value})")
            console.print(f"  Trading TF: {signal.trading_timeframe}")
            console.print(f"  Generated: {signal.signal_timestamp}")
            console.print(f"  Risk/Reward: {signal.risk_reward_ratio:.2f}")

            if signal.pattern_context:
                console.print(f"  Context: {signal.pattern_context}")

    # Show errors if any
    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in result.errors:
            console.print(f"  - {error}")


def _display_json(console: Console, result: Any, signals: List[Any]) -> None:
    """Display results in JSON format."""
    output = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "symbols_processed": result.symbols_processed,
            "signals_generated": len(signals),
            "execution_time_ms": result.execution_time_ms,
            "data_fetch_ms": result.data_fetch_ms,
            "indicator_calc_ms": result.indicator_calc_ms,
            "signal_generation_ms": result.signal_generation_ms,
            "errors": result.errors,
        },
        "signals": [
            {
                "symbol": s.symbol,
                "type": s.signal_type.value,
                "confidence": float(s.confidence),
                "entry_price": float(s.entry_price),
                "target_price": float(s.target_price),
                "stop_loss": float(s.stop_loss),
                "htf_timeframe": s.htf_timeframe,
                "trading_timeframe": s.trading_timeframe,
                "timestamp": s.signal_timestamp.isoformat(),
                "htf_trend": s.htf_trend.value,
                "risk_reward_ratio": s.risk_reward_ratio,
                "signal_strength": s.signal_strength,
                "timeframe_alignment": s.timeframe_alignment,
                "pattern_context": s.pattern_context,
            }
            for s in signals
        ],
    }

    console.print(json.dumps(output, indent=2))


def _calc_pct(entry: float, target: float) -> float:
    """Calculate percentage change from entry to target."""
    return (target - entry) / entry
