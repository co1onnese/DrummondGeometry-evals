#!/usr/bin/env python3
"""
Clean up invalid symbols from the database.
Removes or deactivates symbols that don't exist in EODHD API.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def find_invalid_symbols():
    """Find symbols that are likely invalid (evaluation, test, etc.)."""
    invalid_patterns = ['EVAL', 'TEST', '_NOV', '_DEC', '_JAN', '_FEB', '_MAR', '_APR', '_MAY', '_JUN']
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Find symbols matching invalid patterns
            pattern_conditions = " OR ".join([f"symbol LIKE '%{p}%'" for p in invalid_patterns])
            cur.execute(f"""
                SELECT symbol_id, symbol, is_active
                FROM market_symbols
                WHERE {pattern_conditions}
                ORDER BY symbol
            """)
            return cur.fetchall()


def verify_symbol_exists(symbol: str, client: EODHDClient) -> bool:
    """Verify if a symbol exists in EODHD API."""
    try:
        # Try to fetch a small amount of data to verify symbol exists
        data = client.fetch_intraday(symbol, interval="1d", limit=1)
        return len(data) > 0
    except Exception as e:
        error_msg = str(e).lower()
        if "404" in error_msg or "not found" in error_msg or "ticker not found" in error_msg:
            return False
        # For other errors, assume symbol might exist but API has issues
        # Log but don't fail
        console.print(f"[yellow]Warning: Could not verify {symbol}: {e}[/yellow]")
        return True  # Give benefit of doubt


def deactivate_symbols(symbol_ids: list[int], reason: str = "Invalid symbol"):
    """Deactivate symbols in the database."""
    if not symbol_ids:
        return 0
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            placeholders = ','.join(['%s'] * len(symbol_ids))
            cur.execute(f"""
                UPDATE market_symbols
                SET is_active = false
                WHERE symbol_id IN ({placeholders})
            """, symbol_ids)
            conn.commit()
            return cur.rowcount


def delete_symbols(symbol_ids: list[int]):
    """Delete symbols and their data from the database."""
    if not symbol_ids:
        return 0
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            placeholders = ','.join(['%s'] * len(symbol_ids))
            # Delete market data first (foreign key constraint)
            cur.execute(f"""
                DELETE FROM market_data
                WHERE symbol_id IN ({placeholders})
            """, symbol_ids)
            data_deleted = cur.rowcount
            
            # Delete symbols
            cur.execute(f"""
                DELETE FROM market_symbols
                WHERE symbol_id IN ({placeholders})
            """, symbol_ids)
            symbols_deleted = cur.rowcount
            conn.commit()
            return symbols_deleted, data_deleted


def main():
    """Main cleanup function."""
    console.print("\n[bold cyan]DGAS Invalid Symbol Cleanup[/bold cyan]")
    console.print("=" * 60)
    
    # Find invalid symbols by pattern
    console.print("\n[cyan]Step 1: Finding symbols with invalid patterns...[/cyan]")
    invalid_by_pattern = find_invalid_symbols()
    
    if not invalid_by_pattern:
        console.print("[green]✓ No symbols found matching invalid patterns[/green]")
        return 0
    
    console.print(f"[yellow]Found {len(invalid_by_pattern)} symbols matching invalid patterns[/yellow]")
    
    # Show what we found
    table = Table(title="Invalid Symbols by Pattern")
    table.add_column("Symbol ID", style="cyan")
    table.add_column("Symbol", style="magenta")
    table.add_column("Active", style="yellow")
    
    for symbol_id, symbol, is_active in invalid_by_pattern[:20]:
        table.add_row(str(symbol_id), symbol, str(is_active))
    
    if len(invalid_by_pattern) > 20:
        table.add_row("...", f"... and {len(invalid_by_pattern) - 20} more", "...")
    
    console.print(table)
    
    # Ask what to do
    console.print("\n[cyan]Step 2: Choose action for invalid symbols[/cyan]")
    console.print("1. Deactivate (mark as inactive) - Recommended")
    console.print("2. Delete (remove from database completely)")
    console.print("3. Verify with EODHD API first, then deactivate invalid ones")
    console.print("4. Cancel")
    
    choice = console.input("\n[bold]Choice (1-4): [/bold]").strip()
    
    if choice == "4":
        console.print("[yellow]Cancelled[/yellow]")
        return 0
    
    symbol_ids = [sid for sid, _, _ in invalid_by_pattern]
    symbols = [sym for _, sym, _ in invalid_by_pattern]
    
    if choice == "3":
        # Verify with API
        console.print("\n[cyan]Verifying symbols with EODHD API...[/cyan]")
        settings = get_settings()
        client = EODHDClient(EODHDConfig.from_settings(settings))
        
        verified_invalid = []
        verified_valid = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Verifying symbols...", total=len(symbols))
            
            for symbol_id, symbol in zip(symbol_ids, symbols):
                progress.update(task, description=f"Checking {symbol}...")
                if not verify_symbol_exists(symbol, client):
                    verified_invalid.append(symbol_id)
                else:
                    verified_valid.append(symbol_id)
                progress.advance(task)
        
        client.close()
        
        console.print(f"\n[green]✓ Verified: {len(verified_valid)} valid, {len(verified_invalid)} invalid[/green]")
        
        if verified_invalid:
            console.print(f"\n[cyan]Deactivating {len(verified_invalid)} invalid symbols...[/cyan]")
            count = deactivate_symbols(verified_invalid, "Verified as non-existent in EODHD API")
            console.print(f"[green]✓ Deactivated {count} symbols[/green]")
        
        if verified_valid:
            console.print(f"\n[yellow]Note: {len(verified_valid)} symbols matched pattern but exist in API (keeping active)[/yellow]")
    
    elif choice == "1":
        # Deactivate
        console.print(f"\n[cyan]Deactivating {len(symbol_ids)} symbols...[/cyan]")
        count = deactivate_symbols(symbol_ids, "Invalid pattern match")
        console.print(f"[green]✓ Deactivated {count} symbols[/green]")
    
    elif choice == "2":
        # Delete
        confirm = console.input(f"\n[bold red]WARNING: This will DELETE {len(symbol_ids)} symbols and all their data. Type 'DELETE' to confirm: [/bold red]")
        if confirm == "DELETE":
            console.print(f"\n[cyan]Deleting {len(symbol_ids)} symbols...[/cyan]")
            symbols_deleted, data_deleted = delete_symbols(symbol_ids)
            console.print(f"[green]✓ Deleted {symbols_deleted} symbols and {data_deleted} data records[/green]")
        else:
            console.print("[yellow]Cancelled[/yellow]")
            return 0
    
    # Show final status
    console.print("\n[cyan]Final status:[/cyan]")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM market_symbols WHERE is_active = true")
            active_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM market_symbols WHERE is_active = false")
            inactive_count = cur.fetchone()[0]
    
    console.print(f"[green]Active symbols: {active_count}[/green]")
    console.print(f"[yellow]Inactive symbols: {inactive_count}[/yellow]")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
