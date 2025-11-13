#!/usr/bin/env python3
"""Test script for EODHD WebSocket client.

Tests WebSocket connection with a small number of symbols to verify
connectivity and message parsing.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.websocket_client import EODHDWebSocketClient
from dgas.settings import get_settings
from rich.console import Console
from rich.table import Table

console = Console()


async def test_websocket():
    """Test WebSocket client with a few symbols."""
    settings = get_settings()

    if not settings.eodhd_api_token:
        console.print("[bold red]Error: EODHD_API_TOKEN not configured[/bold red]")
        return 1

    # Test with a few symbols
    test_symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]
    console.print(f"[bold blue]Testing WebSocket with {len(test_symbols)} symbols[/bold blue]")
    console.print(f"Symbols: {', '.join(test_symbols)}")

    bars_received = {}
    ticks_received = {}
    errors = []

    def on_bar(symbol: str, bar):
        """Callback when bar is complete."""
        if symbol not in bars_received:
            bars_received[symbol] = []
        bars_received[symbol].append(bar)
        console.print(f"[green]✓[/green] Bar received for {symbol}: {bar.timestamp} @ ${bar.close}")

    def on_tick(symbol: str, tick):
        """Callback for raw ticks."""
        if symbol not in ticks_received:
            ticks_received[symbol] = 0
        ticks_received[symbol] += 1

    def on_error(symbol: str, error: Exception):
        """Callback for errors."""
        error_msg = f"{symbol}: {error}"
        errors.append(error_msg)
        console.print(f"[red]✗[/red] Error: {error_msg}")

    # Create client
    client = EODHDWebSocketClient(
        api_token=settings.eodhd_api_token,
        on_bar_complete=on_bar,
        on_tick=on_tick,
        on_error=on_error,
        interval="30m",
    )

    try:
        console.print("[cyan]Connecting to EODHD WebSocket...[/cyan]")
        await client.connect(test_symbols)

        # Wait for data (run for 2 minutes)
        console.print("[cyan]Waiting for data (2 minutes)...[/cyan]")
        console.print("[yellow]Note: Bars will only be completed when 30m interval finishes[/yellow]")

        start_time = time.time()
        while time.time() - start_time < 120:  # 2 minutes
            await asyncio.sleep(5)

            # Print status
            status = client.get_status()
            console.print(f"\n[dim]Status: {status['connected']}/{status['connections']} connections, "
                         f"{status['total_messages_received']} messages, "
                         f"{status['aggregation']['ticks_processed']} ticks processed[/dim]")

            # Print tick counts
            if ticks_received:
                tick_summary = ", ".join(f"{s}: {c}" for s, c in sorted(ticks_received.items()))
                console.print(f"[dim]Ticks: {tick_summary}[/dim]")

        # Flush any pending bars
        console.print("\n[cyan]Flushing pending bars...[/cyan]")
        completed_bars = client.flush_pending_bars()
        for bar in completed_bars:
            if bar.symbol not in bars_received:
                bars_received[bar.symbol] = []
            bars_received[bar.symbol].append(bar)

        # Print summary
        console.print("\n[bold green]Test Summary:[/bold green]")
        table = Table(title="WebSocket Test Results")
        table.add_column("Symbol", style="cyan")
        table.add_column("Ticks", justify="right")
        table.add_column("Bars", justify="right")

        for symbol in test_symbols:
            ticks = ticks_received.get(symbol, 0)
            bars = len(bars_received.get(symbol, []))
            table.add_row(symbol, str(ticks), str(bars))

        console.print(table)

        if errors:
            console.print(f"\n[bold red]Errors ({len(errors)}):[/bold red]")
            for error in errors[:10]:
                console.print(f"  • {error}")

        status = client.get_status()
        console.print(f"\n[bold]Final Status:[/bold]")
        console.print(f"  Connections: {status['connected']}/{status['connections']}")
        console.print(f"  Messages: {status['total_messages_received']}")
        console.print(f"  Ticks processed: {status['aggregation']['ticks_processed']}")
        console.print(f"  Bars completed: {status['aggregation']['bars_completed']}")
        console.print(f"  Pending bars: {status['aggregation']['pending_bars']}")

        if status['aggregation']['ticks_processed'] > 0:
            console.print("\n[bold green]✓ WebSocket is receiving data![/bold green]")
            console.print("[yellow]Note: Verify message format matches EODHD API documentation[/yellow]")
            return 0
        else:
            console.print("\n[bold yellow]⚠ No ticks received - check connection and message format[/bold yellow]")
            return 1

    except Exception as e:
        console.print(f"[bold red]Test failed: {e}[/bold red]", exc_info=True)
        return 1
    finally:
        console.print("\n[cyan]Disconnecting...[/cyan]")
        await client.disconnect()


if __name__ == "__main__":
    exit_code = asyncio.run(test_websocket())
    sys.exit(exit_code)
