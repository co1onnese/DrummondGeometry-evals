#!/usr/bin/env python3
"""Verify that data collection is making API calls."""
import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from rich.console import Console
from rich.table import Table
from dgas.db import get_connection
from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings
console = Console()
def main():
    console.print("[bold cyan]Verifying API Calls[/bold cyan]\n")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT run_timestamp, status, symbols_requested, symbols_updated, bars_fetched, bars_stored FROM data_collection_runs ORDER BY run_timestamp DESC LIMIT 5")
            runs = cur.fetchall()
            if runs:
                table = Table(show_header=True)
                table.add_column("Time")
                table.add_column("Status")
                table.add_column("Requested")
                table.add_column("Updated")
                table.add_column("Bars Fetched")
                table.add_column("Bars Stored")
                for run in runs:
                    ts = run[0]
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
                    table.add_row(f"{age:.1f} min ago", run[1], str(run[2]), str(run[3]), str(run[4]), str(run[5]))
                console.print(table)
                if runs[0][4] > 0:
                    console.print(f"\n[green]✓ API calls confirmed: {runs[0][4]} bars fetched in most recent run[/green]")
                else:
                    console.print("\n[red]✗ No bars fetched - API calls not working![/red]")
            else:
                console.print("[yellow]No collection runs found[/yellow]")
    try:
        settings = get_settings()
        client = EODHDClient(EODHDConfig.from_settings(settings))
        bars = client.fetch_intraday("AAPL", interval="30m", limit=3)
        client.close()
        if bars:
            console.print(f"\n[green]✓ Direct API test successful: {len(bars)} bars received[/green]")
        else:
            console.print("\n[yellow]⚠ Direct API test returned no data[/yellow]")
    except Exception as e:
        console.print(f"\n[red]✗ Direct API test failed: {e}[/red]")
    return 0
if __name__ == "__main__":
    sys.exit(main())
