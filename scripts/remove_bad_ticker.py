#!/usr/bin/env python3
"""Remove a bad ticker from the database and all related data.

This script safely removes a ticker symbol and all data associated with it,
including:
- Market data (OHLCV bars)
- Market states
- Pattern events
- Multi-timeframe analysis
- Generated signals
- Backtest results (sets symbol_id to NULL)
- And all other related data via CASCADE DELETE
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from rich.console import Console
from rich.table import Table

console = Console()


def check_ticker_data(conn, symbol: str) -> dict:
    """Check what data exists for the given symbol."""
    # Get symbol_id first
    with conn.cursor() as cur:
        cur.execute("SELECT symbol_id FROM market_symbols WHERE symbol = %s", (symbol,))
        row = cur.fetchone()
        if not row:
            return None
        symbol_id = row[0]
    
    # Count data in each table (rollback after errors to continue)
    counts = {}
    
    # Tables with CASCADE DELETE (will auto-delete)
    tables = [
        ("market_data", "symbol_id"),
        ("market_states_v2", "symbol_id"),
        ("market_state", "symbol_id"),
        ("pattern_events", "symbol_id"),
        ("multi_timeframe_analysis", "symbol_id"),
        ("confluence_zones", "symbol_id"),
        ("generated_signals", "symbol_id"),
        ("trading_signals", "symbol_id"),
        ("backtest_trades", "symbol_id"),
        ("pldot_calculations", "symbol_id"),
    ]
    
    for table, col in tables:
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = %s", (symbol_id,))
                counts[table] = cur.fetchone()[0]
        except Exception as e:
            # Rollback to continue with next query
            conn.rollback()
            # Table might not exist or other error
            counts[table] = f"Error: {str(e)[:50]}"
    
    # Tables with SET NULL (will set to NULL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM backtest_results 
                WHERE symbol_id = %s OR benchmark_symbol_id = %s
                """,
                (symbol_id, symbol_id)
            )
            counts["backtest_results"] = cur.fetchone()[0]
    except Exception as e:
        conn.rollback()
        counts["backtest_results"] = f"Error: {str(e)[:50]}"
    
    return {
        "symbol_id": symbol_id,
        "counts": counts,
    }


def remove_ticker(conn, symbol: str, dry_run: bool = False) -> bool:
    """Remove the ticker and all related data."""
    with conn.cursor() as cur:
        # Get symbol_id first
        cur.execute("SELECT symbol_id FROM market_symbols WHERE symbol = %s", (symbol,))
        row = cur.fetchone()
        if not row:
            console.print(f"[red]Symbol '{symbol}' not found in database[/red]")
            return False
        
        symbol_id = row[0]
        
        if dry_run:
            console.print(f"[yellow]DRY RUN: Would delete symbol '{symbol}' (symbol_id={symbol_id})[/yellow]")
            return True
        
        # Delete the symbol (CASCADE will handle related data)
        cur.execute("DELETE FROM market_symbols WHERE symbol_id = %s", (symbol_id,))
        
        # Check if anything was deleted
        if cur.rowcount == 0:
            console.print(f"[red]Failed to delete symbol '{symbol}'[/red]")
            return False
        
        console.print(f"[green]Successfully deleted symbol '{symbol}' (symbol_id={symbol_id})[/green]")
        return True


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Remove a bad ticker from the database")
    parser.add_argument("symbol", help="Symbol to remove (e.g., 30DAY_BT)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    
    args = parser.parse_args()
    
    symbol = args.symbol.upper()
    
    console.print(f"\n[bold]Removing ticker: {symbol}[/bold]\n")
    
    try:
        with get_connection() as conn:
            # Check what data exists
            data_info = check_ticker_data(conn, symbol)
            
            if data_info is None:
                console.print(f"[red]Symbol '{symbol}' not found in database[/red]")
                return 1
            
            # Display summary
            table = Table(title=f"Data Summary for {symbol} (symbol_id={data_info['symbol_id']})")
            table.add_column("Table", style="cyan")
            table.add_column("Count", style="magenta")
            
            total_rows = 0
            for table_name, count in data_info["counts"].items():
                if isinstance(count, int):
                    table.add_row(table_name, str(count))
                    total_rows += count
                else:
                    table.add_row(table_name, str(count))
            
            table.add_row("", "", style="bold")
            table.add_row("Total rows to be deleted", str(total_rows), style="bold yellow")
            
            console.print(table)
            console.print()
            
            if args.dry_run:
                console.print("[yellow]DRY RUN: No changes made[/yellow]")
                return 0
            
            # Confirm deletion
            if not args.force:
                console.print(f"[bold red]WARNING: This will permanently delete all data for '{symbol}'[/bold red]")
                response = input("Are you sure you want to continue? (yes/no): ")
                if response.lower() not in ["yes", "y"]:
                    console.print("[yellow]Deletion cancelled[/yellow]")
                    return 0
            
            # Remove the ticker
            success = remove_ticker(conn, symbol, dry_run=False)
            
            if success:
                console.print(f"\n[green]✓ Successfully removed '{symbol}' and all related data[/green]")
                return 0
            else:
                console.print(f"\n[red]✗ Failed to remove '{symbol}'[/red]")
                return 1
                
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
