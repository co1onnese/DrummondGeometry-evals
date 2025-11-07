"""Drummond Geometry analysis CLI command."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..calculations import (
    MultiTimeframeCoordinator,
    TimeframeData,
    TimeframeType,
    build_timeframe_data,
)
from ..data.models import IntervalData
from ..db import get_connection

console = Console()


def load_market_data(
    symbol: str,
    interval: str,
    lookback_bars: int = 200,
) -> list[IntervalData]:
    """Load market data from database."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get symbol_id
        cursor.execute(
            "SELECT symbol_id FROM market_symbols WHERE symbol = %s",
            (symbol,)
        )
        result = cursor.fetchone()
        if result is None:
            raise ValueError(f"Symbol {symbol} not found in database")
        symbol_id = result[0]

        # Get recent market data
        cursor.execute(
            """
            SELECT
                timestamp, open_price, high_price, low_price,
                close_price, volume
            FROM market_data
            WHERE symbol_id = %s AND interval_type = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            (symbol_id, interval, lookback_bars)
        )

        rows = cursor.fetchall()
        if not rows:
            raise ValueError(f"No market data found for {symbol} on {interval} interval")

        # Convert to IntervalData (reverse to chronological order)
        intervals = []
        for row in reversed(rows):
            timestamp, open_p, high_p, low_p, close_p, volume = row
            intervals.append(
                IntervalData(
                    symbol=symbol,
                    exchange=None,  # Will be added by fetch_market_data if needed
                    timestamp=timestamp,
                    interval=interval,
                    open=Decimal(str(open_p)),
                    high=Decimal(str(high_p)),
                    low=Decimal(str(low_p)),
                    close=Decimal(str(close_p)),
                    volume=int(volume),
                    adjusted_close=Decimal(str(close_p)),
                )
            )

        return intervals


def calculate_indicators(intervals: list[IntervalData]) -> TimeframeData:
    """Calculate all Drummond indicators for a single timeframe."""
    return build_timeframe_data(intervals, timeframe="", classification=TimeframeType.TRADING)


def display_single_timeframe_analysis(
    symbol: str,
    interval: str,
    tf_data: TimeframeData,
) -> None:
    """Display single timeframe analysis results."""
    console.print()
    console.print(Panel(
        f"[bold cyan]{symbol}[/bold cyan] - [cyan]{interval}[/cyan] Timeframe Analysis",
        border_style="cyan"
    ))

    # Current state
    if tf_data.state_series:
        current_state = tf_data.state_series[-1]

        # State info
        state_table = Table(show_header=False, box=None, padding=(0, 2))
        state_table.add_column("Field", style="bold")
        state_table.add_column("Value")

        # Color code based on state
        state_color = "green" if current_state.state.value == "TREND" else "yellow"
        direction_color = "green" if current_state.trend_direction.value == "UP" else "red" if current_state.trend_direction.value == "DOWN" else "yellow"

        state_table.add_row("Market State:", f"[{state_color}]{current_state.state.value}[/{state_color}]")
        state_table.add_row("Trend Direction:", f"[{direction_color}]{current_state.trend_direction.value}[/{direction_color}]")
        state_table.add_row("Bars in State:", str(current_state.bars_in_state))
        state_table.add_row("Confidence:", f"{float(current_state.confidence):.2%}")
        state_table.add_row("PLdot Slope:", current_state.pldot_slope_trend)

        console.print(state_table)

    # Current PLdot
    if tf_data.pldot_series:
        current_pldot = tf_data.pldot_series[-1]
        console.print()
        pldot_table = Table(show_header=False, box=None, padding=(0, 2))
        pldot_table.add_column("Field", style="bold")
        pldot_table.add_column("Value")

        pldot_table.add_row("PLdot Value:", f"${float(current_pldot.value):,.2f}")
        pldot_table.add_row("PLdot Slope:", f"{float(current_pldot.slope):,.4f}")
        pldot_table.add_row("Projected Value:", f"${float(current_pldot.projected_value):,.2f}")

        console.print(pldot_table)

    # Current envelope
    if tf_data.envelope_series:
        current_env = tf_data.envelope_series[-1]
        console.print()
        env_table = Table(show_header=False, box=None, padding=(0, 2))
        env_table.add_column("Field", style="bold")
        env_table.add_column("Value")

        env_table.add_row("Upper Band:", f"${float(current_env.upper):,.2f}")
        env_table.add_row("Center (PLdot):", f"${float(current_env.center):,.2f}")
        env_table.add_row("Lower Band:", f"${float(current_env.lower):,.2f}")
        env_table.add_row("Band Width:", f"${float(current_env.width):,.2f}")
        env_table.add_row("Position:", f"{float(current_env.position):.2%}")

        console.print(env_table)

    # Recent patterns
    if tf_data.pattern_events:
        console.print()
        console.print("[bold]Recent Patterns (Last 5):[/bold]")

        recent_patterns = sorted(tf_data.pattern_events, key=lambda p: p.end_timestamp, reverse=True)[:5]

        for pattern in recent_patterns:
            direction_symbol = "🔼" if pattern.direction == 1 else "🔽" if pattern.direction == -1 else "⏸️"
            direction_color = "green" if pattern.direction == 1 else "red" if pattern.direction == -1 else "yellow"

            console.print(
                f"  {direction_symbol} [{direction_color}]{pattern.pattern_type.value}[/{direction_color}] "
                f"(strength: {pattern.strength}) - "
                f"{pattern.start_timestamp.strftime('%Y-%m-%d %H:%M')} to "
                f"{pattern.end_timestamp.strftime('%Y-%m-%d %H:%M')}"
            )


def display_multi_timeframe_analysis(
    symbol: str,
    analysis,
) -> None:
    """Display multi-timeframe analysis results."""
    console.print()
    console.print(Panel(
        f"[bold magenta]Multi-Timeframe Analysis: {symbol}[/bold magenta]",
        border_style="magenta"
    ))

    # HTF vs Trading TF comparison
    htf_table = Table(title="Timeframe Comparison", box=None, show_header=True)
    htf_table.add_column("Timeframe", style="bold")
    htf_table.add_column("Trend")
    htf_table.add_column("Strength")

    htf_color = "green" if analysis.htf_trend.value == "UP" else "red" if analysis.htf_trend.value == "DOWN" else "yellow"
    trading_color = "green" if analysis.trading_tf_trend.value == "UP" else "red" if analysis.trading_tf_trend.value == "DOWN" else "yellow"

    htf_table.add_row(
        f"HTF ({analysis.htf_timeframe})",
        f"[{htf_color}]{analysis.htf_trend.value}[/{htf_color}]",
        f"{float(analysis.htf_trend_strength):.2%}"
    )
    htf_table.add_row(
        f"Trading ({analysis.trading_timeframe})",
        f"[{trading_color}]{analysis.trading_tf_trend.value}[/{trading_color}]",
        "N/A"
    )

    console.print(htf_table)

    # Alignment analysis
    console.print()
    alignment_table = Table(show_header=False, box=None, padding=(0, 2))
    alignment_table.add_column("Field", style="bold")
    alignment_table.add_column("Value")

    alignment_color = "green" if analysis.alignment.alignment_type == "perfect" else "blue" if analysis.alignment.alignment_type == "partial" else "yellow" if analysis.alignment.alignment_type == "divergent" else "red"

    alignment_table.add_row("Alignment Type:", f"[{alignment_color}]{analysis.alignment.alignment_type.upper()}[/{alignment_color}]")
    alignment_table.add_row("Alignment Score:", f"{float(analysis.alignment.alignment_score):.2%}")
    alignment_table.add_row("Trade Permitted:", "✅ YES" if analysis.alignment.trade_permitted else "❌ NO")

    console.print(alignment_table)

    # PLdot overlay
    console.print()
    overlay_table = Table(show_header=False, box=None, padding=(0, 2))
    overlay_table.add_column("Field", style="bold")
    overlay_table.add_column("Value")

    overlay_table.add_row("HTF PLdot:", f"${float(analysis.pldot_overlay.htf_pldot_value):,.2f}")
    overlay_table.add_row("Trading PLdot:", f"${float(analysis.pldot_overlay.ltf_pldot_value):,.2f}")
    overlay_table.add_row("Distance:", f"{float(analysis.pldot_overlay.distance_percent):.2f}%")
    overlay_table.add_row("Position:", analysis.pldot_overlay.position.replace("_", " ").upper())

    console.print(overlay_table)

    # Signal analysis
    console.print()
    signal_color = "green" if analysis.risk_level == "low" else "yellow" if analysis.risk_level == "medium" else "red"
    action_color = "green" if analysis.recommended_action in ["long", "short"] else "yellow"

    signal_table = Table(show_header=False, box=None, padding=(0, 2))
    signal_table.add_column("Field", style="bold")
    signal_table.add_column("Value")

    signal_table.add_row("Signal Strength:", f"{float(analysis.signal_strength):.2%}")
    signal_table.add_row("Risk Level:", f"[{signal_color}]{analysis.risk_level.upper()}[/{signal_color}]")
    signal_table.add_row("Recommended Action:", f"[{action_color}]{analysis.recommended_action.upper()}[/{action_color}]")
    signal_table.add_row("Pattern Confluence:", "✅ YES" if analysis.pattern_confluence else "❌ NO")

    console.print(signal_table)

    # Confluence zones
    if analysis.confluence_zones:
        console.print()
        console.print(f"[bold]Confluence Zones ({len(analysis.confluence_zones)}):[/bold]")

        zones_table = Table(show_header=True)
        zones_table.add_column("Type", style="bold")
        zones_table.add_column("Level", justify="right")
        zones_table.add_column("Range", justify="right")
        zones_table.add_column("Strength")
        zones_table.add_column("Timeframes")

        for zone in analysis.confluence_zones[:5]:  # Show top 5
            zone_color = "green" if zone.zone_type == "support" else "red" if zone.zone_type == "resistance" else "blue"

            zones_table.add_row(
                f"[{zone_color}]{zone.zone_type.upper()}[/{zone_color}]",
                f"${float(zone.level):,.2f}",
                f"${float(zone.lower_bound):,.2f} - ${float(zone.upper_bound):,.2f}",
                f"{zone.strength} TFs",
                ", ".join(zone.timeframes)
            )

        console.print(zones_table)

    # Trading recommendation summary
    console.print()
    if analysis.alignment.trade_permitted and analysis.signal_strength >= 0.6:
        if analysis.recommended_action == "long":
            console.print(Panel(
                f"[bold green]LONG SIGNAL[/bold green]\n"
                f"Signal Strength: {float(analysis.signal_strength):.1%}\n"
                f"Risk Level: {analysis.risk_level.upper()}\n"
                f"HTF Trend: {analysis.htf_trend.value}",
                border_style="green",
                title="🚀 Trading Signal"
            ))
        elif analysis.recommended_action == "short":
            console.print(Panel(
                f"[bold red]SHORT SIGNAL[/bold red]\n"
                f"Signal Strength: {float(analysis.signal_strength):.1%}\n"
                f"Risk Level: {analysis.risk_level.upper()}\n"
                f"HTF Trend: {analysis.htf_trend.value}",
                border_style="red",
                title="📉 Trading Signal"
            ))
        else:
            console.print(Panel(
                f"[bold yellow]{analysis.recommended_action.upper()}[/bold yellow]\n"
                f"Alignment: {analysis.alignment.alignment_type}\n"
                f"Signal Strength: {float(analysis.signal_strength):.1%}",
                border_style="yellow",
                title="⏸️ No Clear Signal"
            ))
    else:
        reason = []
        if not analysis.alignment.trade_permitted:
            reason.append("HTF trend does not permit this direction")
        if analysis.signal_strength < 0.6:
            reason.append(f"Signal strength too low ({float(analysis.signal_strength):.1%})")

        console.print(Panel(
            f"[bold yellow]WAIT[/bold yellow]\n" + "\n".join(f"• {r}" for r in reason),
            border_style="yellow",
            title="⏸️ No Trade Signal"
        ))


def run_analyze_command(
    symbols: list[str],
    htf_interval: str,
    trading_interval: str,
    lookback_bars: int,
    save_to_db: bool,
    output_format: str,
) -> int:
    """
    Run Drummond Geometry analysis on specified symbols.

    Args:
        symbols: List of symbols to analyze
        htf_interval: Higher timeframe interval (e.g., '4h', '1d')
        trading_interval: Trading timeframe interval (e.g., '1h', '30min')
        lookback_bars: Number of bars to load for analysis
        save_to_db: Whether to save results to database
        output_format: Output format ('table', 'json', 'summary')

    Returns:
        Exit code (0 for success)
    """
    try:
        console.print(f"[bold]Drummond Geometry Analysis[/bold]")
        console.print(f"HTF: {htf_interval} | Trading: {trading_interval} | Symbols: {', '.join(symbols)}\n")

        for symbol in symbols:
            try:
                # Load market data for both timeframes
                console.print(f"[dim]Loading data for {symbol}...[/dim]")

                htf_intervals = load_market_data(symbol, htf_interval, lookback_bars)
                trading_intervals = load_market_data(symbol, trading_interval, lookback_bars)

                # Calculate indicators for both timeframes
                console.print(f"[dim]Calculating indicators...[/dim]")

                htf_base = calculate_indicators(htf_intervals)
                htf_data = TimeframeData(
                    timeframe=htf_interval,
                    classification=TimeframeType.HIGHER,
                    pldot_series=htf_base.pldot_series,
                    envelope_series=htf_base.envelope_series,
                    state_series=htf_base.state_series,
                    pattern_events=htf_base.pattern_events,
                    drummond_zones=htf_base.drummond_zones,
                )

                trading_base = calculate_indicators(trading_intervals)
                trading_data = TimeframeData(
                    timeframe=trading_interval,
                    classification=TimeframeType.TRADING,
                    pldot_series=trading_base.pldot_series,
                    envelope_series=trading_base.envelope_series,
                    state_series=trading_base.state_series,
                    pattern_events=trading_base.pattern_events,
                    drummond_zones=trading_base.drummond_zones,
                )

                # Display single timeframe analysis if in detailed mode
                if output_format == "detailed":
                    display_single_timeframe_analysis(symbol, htf_interval, htf_data)
                    display_single_timeframe_analysis(symbol, trading_interval, trading_data)

                # Perform multi-timeframe coordination
                console.print(f"[dim]Performing multi-timeframe coordination...[/dim]")

                coordinator = MultiTimeframeCoordinator(
                    htf_timeframe=htf_interval,
                    trading_timeframe=trading_interval,
                )

                analysis = coordinator.analyze(htf_data, trading_data)

                # Display multi-timeframe analysis
                display_multi_timeframe_analysis(symbol, analysis)

                # Save to database if requested
                if save_to_db:
                    try:
                        from ..db.persistence import DrummondPersistence

                        console.print(f"\n[dim]Saving results to database...[/dim]")

                        with DrummondPersistence() as db:
                            # Save states
                            db.save_market_states(symbol, htf_interval, htf_data.state_series)
                            db.save_market_states(symbol, trading_interval, trading_data.state_series)

                            # Save patterns
                            db.save_pattern_events(symbol, htf_interval, htf_data.pattern_events)
                            db.save_pattern_events(symbol, trading_interval, trading_data.pattern_events)

                            # Save multi-timeframe analysis
                            analysis_id = db.save_multi_timeframe_analysis(symbol, analysis)

                            console.print(f"[green]✓ Results saved (Analysis ID: {analysis_id})[/green]")
                    except ImportError:
                        console.print("[yellow]⚠ Database persistence not available (psycopg2 not installed)[/yellow]")
                    except Exception as e:
                        console.print(f"[red]✗ Failed to save to database: {e}[/red]")

                console.print("\n" + "─" * console.width + "\n")

            except ValueError as e:
                console.print(f"[red]Error analyzing {symbol}: {e}[/red]\n")
                continue
            except Exception as e:
                console.print(f"[red]Unexpected error analyzing {symbol}: {e}[/red]\n")
                if "--debug" in sys.argv:
                    raise
                continue

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Analysis interrupted by user[/yellow]")
        return 1
    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")
        if "--debug" in sys.argv:
            raise
        return 1


__all__ = ["run_analyze_command"]
