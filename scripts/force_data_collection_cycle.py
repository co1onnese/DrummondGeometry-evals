#!/usr/bin/env python3
"""
Force a data collection cycle to run and see what happens.
This helps diagnose stuck cycles.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console
from dgas.config import load_settings
from dgas.data.collection_scheduler import DataCollectionScheduler
from dgas.data.collection_service import DataCollectionService
from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings
from dgas.db import get_connection

console = Console()

def main():
    console.print("[bold cyan]Forcing a data collection cycle...[/bold cyan]")
    console.print()
    
    # Load config
    unified_settings = load_settings()
    dc_config = unified_settings.data_collection
    
    if not dc_config or not dc_config.enabled:
        console.print("[red]Data collection is disabled![/red]")
        return 1
    
    # Load symbols
    console.print("[cyan]Loading symbols from database...[/cyan]")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            symbols = [row[0] for row in cur.fetchall()]
    
    console.print(f"[green]Loaded {len(symbols)} symbols[/green]")
    console.print()
    
    # Create service and scheduler
    console.print("[cyan]Creating service and scheduler...[/cyan]")
    legacy_settings = get_settings()
    client = EODHDClient(EODHDConfig.from_settings(legacy_settings))
    service = DataCollectionService(dc_config, client=client)
    
    scheduler = DataCollectionScheduler(
        config=dc_config,
        symbols=symbols,
        service=service,
    )
    
    # Try to run once
    console.print("[cyan]Executing collection cycle...[/cyan]")
    console.print("[yellow]This may take several minutes...[/yellow]")
    console.print()
    
    try:
        result = scheduler.run_once()
        
        console.print("[bold green]Collection cycle completed![/bold green]")
        console.print()
        console.print(f"Symbols requested: {result.symbols_requested}")
        console.print(f"Symbols updated: {result.symbols_updated}")
        console.print(f"Symbols failed: {result.symbols_failed}")
        console.print(f"Bars fetched: {result.bars_fetched}")
        console.print(f"Bars stored: {result.bars_stored}")
        console.print(f"Execution time: {result.execution_time_ms}ms ({result.execution_time_ms/1000:.1f}s)")
        console.print(f"Errors: {len(result.errors)}")
        
        if result.errors:
            console.print()
            console.print("[yellow]Errors encountered:[/yellow]")
            for error in result.errors[:10]:
                console.print(f"  - {error}")
            if len(result.errors) > 10:
                console.print(f"  ... and {len(result.errors) - 10} more errors")
        
        return 0
        
    except RuntimeError as e:
        if "already executing" in str(e):
            console.print("[red]Collection cycle is already running![/red]")
            console.print("[yellow]This suggests a stuck cycle. You may need to restart the service.[/yellow]")
        else:
            console.print(f"[red]Runtime error: {e}[/red]")
        return 1
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())
        return 1
    finally:
        service.close()

if __name__ == "__main__":
    sys.exit(main())
