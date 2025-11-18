#!/usr/bin/env python3
"""
Fix data collection issues:
1. Deactivate invalid symbols (EVAL, TEST, etc.)
2. Check for other issues
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from rich.console import Console

console = Console()


def deactivate_invalid_symbols():
    """Deactivate symbols with invalid patterns."""
    console.print("\n[cyan]Deactivating invalid symbols...[/cyan]")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Deactivate invalid symbols
            cur.execute("""
                UPDATE market_symbols
                SET is_active = false
                WHERE (symbol LIKE '%EVAL%' 
                    OR symbol LIKE '%TEST%' 
                    OR symbol LIKE '%_NOV%'
                    OR symbol LIKE '%_DEC%')
                    AND is_active = true
            """)
            count = cur.rowcount
            conn.commit()
            
            if count > 0:
                console.print(f"[green]✓ Deactivated {count} invalid symbols[/green]")
                
                # Show what was deactivated
                cur.execute("""
                    SELECT symbol FROM market_symbols
                    WHERE symbol LIKE '%EVAL%' 
                        OR symbol LIKE '%TEST%' 
                        OR symbol LIKE '%_NOV%'
                        OR symbol LIKE '%_DEC%'
                    ORDER BY symbol
                """)
                for (symbol,) in cur.fetchall():
                    console.print(f"  - {symbol}")
            else:
                console.print("[yellow]No invalid symbols found[/yellow]")


def show_status():
    """Show current symbol status."""
    console.print("\n[cyan]Current Status:[/cyan]")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM market_symbols WHERE is_active = true")
            active = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM market_symbols WHERE is_active = false")
            inactive = cur.fetchone()[0]
            
            console.print(f"[green]Active symbols: {active}[/green]")
            console.print(f"[yellow]Inactive symbols: {inactive}[/yellow]")


def main():
    """Main function."""
    console.print("\n[bold cyan]DGAS Data Collection Fix[/bold cyan]")
    console.print("=" * 60)
    
    deactivate_invalid_symbols()
    show_status()
    
    console.print("\n[green]✓ Cleanup complete![/green]")
    console.print("\n[yellow]Note:[/yellow] Data collection may show 'failures' on weekends")
    console.print("when there's no new market data. This is expected behavior.")
    console.print("\nRestart data collection service:")
    console.print("  screen -r dgas_data_collection")
    console.print("  # Or restart: ./scripts/start_all_services.sh")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
