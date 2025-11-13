#!/usr/bin/env python3
"""
Sync database symbols with CSV file.

This script:
1. Deactivates symbols in database that are not in CSV
2. Activates symbols in CSV that are in database but inactive
3. Registers new symbols from CSV that don't exist in database
4. Ensures symbol count matches CSV exactly
"""

import csv
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.data.repository import ensure_market_symbol
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()

CSV_FILE = Path(__file__).parent.parent / "data" / "index_constituents.csv"


def load_csv_symbols() -> dict[str, dict]:
    """Load symbols from CSV file with metadata."""
    symbols = {}
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row["symbol"].strip().upper()
            symbols[symbol] = {
                "name": row.get("name", "").strip(),
                "sector": row.get("sector", "").strip(),
                "industry": row.get("industry", "").strip(),
                "indices": row.get("indices", "").strip().split(",") if row.get("indices") else [],
            }
    return symbols


def sync_symbols():
    """Sync database symbols with CSV."""
    console.print("[bold blue]Syncing database symbols with CSV...[/bold blue]")
    
    if not CSV_FILE.exists():
        console.print(f"[red]Error: CSV file not found: {CSV_FILE}[/red]")
        return 1
    
    csv_symbols = load_csv_symbols()
    console.print(f"[green]Loaded {len(csv_symbols)} symbols from CSV[/green]")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get all symbols from database
            cur.execute("SELECT symbol, is_active FROM market_symbols")
            db_symbols = {row[0]: row[1] for row in cur.fetchall()}
            
            console.print(f"[cyan]Found {len(db_symbols)} symbols in database[/cyan]")
            
            # Step 1: Deactivate symbols not in CSV
            to_deactivate = [s for s, active in db_symbols.items() if active and s not in csv_symbols]
            if to_deactivate:
                console.print(f"\n[yellow]Deactivating {len(to_deactivate)} symbols not in CSV:[/yellow]")
                for symbol in sorted(to_deactivate):
                    console.print(f"  - {symbol}")
                    cur.execute(
                        "UPDATE market_symbols SET is_active = false, updated_at = NOW() WHERE symbol = %s",
                        (symbol,),
                    )
                conn.commit()
                console.print(f"[green]Deactivated {len(to_deactivate)} symbols[/green]")
            else:
                console.print("[green]No symbols to deactivate[/green]")
            
            # Step 2: Register/activate symbols from CSV
            to_register = []
            to_activate = []
            
            for symbol, metadata in csv_symbols.items():
                if symbol not in db_symbols:
                    to_register.append((symbol, metadata))
                elif not db_symbols[symbol]:
                    to_activate.append(symbol)
            
            # Register new symbols
            if to_register:
                console.print(f"\n[cyan]Registering {len(to_register)} new symbols...[/cyan]")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task("Registering...", total=len(to_register))
                    
                    for symbol, metadata in to_register:
                        try:
                            ensure_market_symbol(
                                conn,
                                symbol,
                                "US",
                                company_name=metadata["name"] or None,
                                sector=metadata["sector"] or None,
                                industry=metadata["industry"] or None,
                                is_active=True,
                            )
                            progress.update(task, advance=1)
                        except Exception as e:
                            console.print(f"[yellow]Warning: Failed to register {symbol}: {e}[/yellow]")
                    
                    conn.commit()
                    console.print(f"[green]Registered {len(to_register)} new symbols[/green]")
            else:
                console.print("[green]No new symbols to register[/green]")
            
            # Activate existing inactive symbols
            if to_activate:
                console.print(f"\n[cyan]Activating {len(to_activate)} symbols...[/cyan]")
                for symbol in to_activate:
                    cur.execute(
                        "UPDATE market_symbols SET is_active = true, updated_at = NOW() WHERE symbol = %s",
                        (symbol,),
                    )
                conn.commit()
                console.print(f"[green]Activated {len(to_activate)} symbols[/green]")
            else:
                console.print("[green]No symbols to activate[/green]")
            
            # Step 3: Update metadata for existing symbols
            console.print("\n[cyan]Updating symbol metadata...[/cyan]")
            updated = 0
            for symbol, metadata in csv_symbols.items():
                if symbol in db_symbols:
                    cur.execute(
                        """
                        UPDATE market_symbols
                        SET company_name = COALESCE(NULLIF(%s, ''), company_name),
                            sector = COALESCE(NULLIF(%s, ''), sector),
                            industry = COALESCE(NULLIF(%s, ''), industry),
                            index_membership = %s,
                            updated_at = NOW()
                        WHERE symbol = %s
                        """,
                        (
                            metadata["name"],
                            metadata["sector"],
                            metadata["industry"],
                            metadata["indices"],
                            symbol,
                        ),
                    )
                    if cur.rowcount > 0:
                        updated += 1
            conn.commit()
            console.print(f"[green]Updated metadata for {updated} symbols[/green]")
            
            # Step 4: Verify final state
            console.print("\n[cyan]Verifying sync...[/cyan]")
            cur.execute("SELECT COUNT(*) FROM market_symbols WHERE is_active = true")
            active_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM market_symbols WHERE is_active = false")
            inactive_count = cur.fetchone()[0]
            
            console.print(f"\n[bold green]Sync complete![/bold green]")
            console.print(f"  Active symbols: {active_count}")
            console.print(f"  Inactive symbols: {inactive_count}")
            console.print(f"  CSV symbols: {len(csv_symbols)}")
            
            if active_count == len(csv_symbols):
                console.print("\n[bold green]✓ Symbol count matches CSV![/bold green]")
                return 0
            else:
                console.print(f"\n[yellow]⚠ Symbol count mismatch: {active_count} active vs {len(csv_symbols)} in CSV[/yellow]")
                return 1


if __name__ == "__main__":
    try:
        exit_code = sync_symbols()
        sys.exit(exit_code)
    except Exception as e:
        import traceback
        console.print(f"[bold red]Error: {e}[/bold red]")
        console.print(traceback.format_exc())
        sys.exit(1)
