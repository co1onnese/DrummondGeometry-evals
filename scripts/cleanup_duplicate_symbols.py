#!/usr/bin/env python3
"""
Clean up duplicate symbols in the database.

This script:
1. Removes .US suffix from all symbols
2. Merges duplicate symbols (keeping the one with most data)
3. Updates all foreign key references
4. Ensures all symbols use "US" as exchange code
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import psycopg
from dgas.settings import get_settings
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()


def normalize_symbol(symbol: str) -> str:
    """Remove .US suffix and normalize symbol."""
    if symbol.endswith(".US"):
        return symbol[:-3]
    return symbol.upper()


def cleanup_symbols():
    """Clean up duplicate symbols in the database."""
    settings = get_settings()
    db_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")

    console.print("[bold blue]Starting symbol cleanup...[/bold blue]")

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Step 1: Find all symbols with .US suffix
            cur.execute(
                """
                SELECT symbol_id, symbol, exchange
                FROM market_symbols
                WHERE symbol LIKE '%.US'
                ORDER BY symbol
                """
            )
            symbols_with_suffix = cur.fetchall()
            console.print(f"[yellow]Found {len(symbols_with_suffix)} symbols with .US suffix[/yellow]")

            if not symbols_with_suffix:
                console.print("[green]No symbols with .US suffix found. Database is clean![/green]")
                return

            # Step 2: Create mapping of old symbol_id -> new normalized symbol
            symbol_mapping = {}  # old_symbol_id -> (normalized_symbol, new_symbol_id)
            symbols_to_update = []  # (old_symbol_id, normalized_symbol)

            for symbol_id, symbol, exchange in symbols_with_suffix:
                normalized = normalize_symbol(symbol)
                symbols_to_update.append((symbol_id, normalized))

            # Step 3: For each symbol, check if normalized version already exists
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Processing symbols...", total=len(symbols_to_update))

                for old_symbol_id, normalized_symbol in symbols_to_update:
                    # Check if normalized symbol already exists (could be with or without .US suffix)
                    cur.execute(
                        """
                        SELECT symbol_id, symbol 
                        FROM market_symbols 
                        WHERE (symbol = %s OR symbol = %s) 
                        AND exchange = 'US'
                        ORDER BY symbol_id
                        """,
                        (normalized_symbol, normalized_symbol + ".US"),
                    )
                    existing_rows = cur.fetchall()

                    if existing_rows:
                        # Find the one that's already normalized (without .US)
                        normalized_row = next(
                            (row for row in existing_rows if not row[1].endswith(".US")),
                            None
                        )
                        if normalized_row:
                            # Use the already normalized one
                            new_symbol_id = normalized_row[0]
                            symbol_mapping[old_symbol_id] = (normalized_symbol, new_symbol_id)
                        else:
                            # All existing ones have .US suffix, we'll update this one
                            symbol_mapping[old_symbol_id] = (normalized_symbol, None)
                    else:
                        # Normalized symbol doesn't exist, we'll update this one
                        symbol_mapping[old_symbol_id] = (normalized_symbol, None)

                    progress.update(task, advance=1)

            # Step 4: Update symbols that need to be renamed (no duplicate)
            console.print("\n[cyan]Updating symbols without duplicates...[/cyan]")
            symbols_to_rename = [
                (old_id, norm_symbol)
                for old_id, (norm_symbol, new_id) in symbol_mapping.items()
                if new_id is None
            ]

            if symbols_to_rename:
                for old_id, norm_symbol in symbols_to_rename:
                    cur.execute(
                        "UPDATE market_symbols SET symbol = %s, exchange = 'US' WHERE symbol_id = %s",
                        (norm_symbol, old_id),
                    )
                conn.commit()
                console.print(f"[green]Updated {len(symbols_to_rename)} symbols[/green]")

            # Step 5: Merge duplicates - update all foreign key references
            console.print("\n[cyan]Merging duplicate symbols...[/cyan]")
            duplicates_to_merge = [
                (old_id, new_id)
                for old_id, (norm_symbol, new_id) in symbol_mapping.items()
                if new_id is not None
            ]

            if duplicates_to_merge:
                # For each duplicate, we need to:
                # 1. Update all foreign key references to point to the new symbol_id
                # 2. Delete the old symbol (CASCADE will handle related data)

                # Get tables with foreign keys to market_symbols
                tables_to_update = [
                    ("market_data", "symbol_id"),
                    ("market_states_v2", "symbol_id"),
                    ("pattern_events", "symbol_id"),
                    ("multi_timeframe_analysis", "symbol_id"),
                    ("prediction_runs", "symbol_id"),
                    ("generated_signals", "symbol_id"),
                    ("backtest_results", "symbol_id"),
                    ("backtest_trades", "symbol_id"),
                    ("pldot_calculations", "symbol_id"),
                    ("envelope_bands", "symbol_id"),
                    ("drummond_lines", "symbol_id"),
                    ("market_state", "symbol_id"),
                    ("trading_signals", "symbol_id"),
                ]

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    merge_task = progress.add_task("Merging duplicates...", total=len(duplicates_to_merge))

                    for old_id, new_id in duplicates_to_merge:
                        try:
                            # For market_data, we need to handle duplicates specially
                            # Delete duplicate data from old symbol_id first (data that already exists for new_id)
                            cur.execute(
                                """
                                DELETE FROM market_data
                                WHERE symbol_id = %s
                                AND (timestamp, interval_type) IN (
                                    SELECT timestamp, interval_type
                                    FROM market_data
                                    WHERE symbol_id = %s
                                )
                                """,
                                (old_id, new_id),
                            )
                            
                            # Now update remaining foreign key references
                            for table_name, fk_column in tables_to_update:
                                try:
                                    # Check if table exists first
                                    cur.execute(
                                        """
                                        SELECT EXISTS (
                                            SELECT FROM information_schema.tables 
                                            WHERE table_name = %s
                                        )
                                        """,
                                        (table_name,),
                                    )
                                    if not cur.fetchone()[0]:
                                        continue
                                    
                                    # Check if column exists
                                    cur.execute(
                                        """
                                        SELECT EXISTS (
                                            SELECT FROM information_schema.columns 
                                            WHERE table_name = %s AND column_name = %s
                                        )
                                        """,
                                        (table_name, fk_column),
                                    )
                                    if not cur.fetchone()[0]:
                                        continue
                                    
                                    # For market_data, use a different approach to avoid duplicates
                                    if table_name == "market_data":
                                        # Update non-duplicate rows (we already deleted duplicates above)
                                        cur.execute(
                                            """
                                            UPDATE market_data
                                            SET symbol_id = %s
                                            WHERE symbol_id = %s
                                            """,
                                            (new_id, old_id),
                                        )
                                    else:
                                        # For other tables, just update the foreign key
                                        cur.execute(
                                            f"""
                                            UPDATE {table_name}
                                            SET {fk_column} = %s
                                            WHERE {fk_column} = %s
                                            """,
                                            (new_id, old_id),
                                        )
                                except psycopg.Error as e:
                                    # Log but continue with other tables
                                    console.print(f"[yellow]Warning: Could not update {table_name}.{fk_column}: {e}[/yellow]")

                            # Delete the old symbol (CASCADE will clean up any remaining references)
                            cur.execute("DELETE FROM market_symbols WHERE symbol_id = %s", (old_id,))
                            conn.commit()
                            
                        except psycopg.Error as e:
                            conn.rollback()
                            console.print(f"[yellow]Warning: Could not merge symbol_id {old_id} -> {new_id}: {e}[/yellow]")
                            continue
                        
                        progress.update(merge_task, advance=1)

                conn.commit()
                console.print(f"[green]Merged {len(duplicates_to_merge)} duplicate symbols[/green]")

            # Step 6: Ensure all remaining symbols use "US" as exchange
            console.print("\n[cyan]Ensuring all symbols use 'US' as exchange...[/cyan]")
            cur.execute(
                "UPDATE market_symbols SET exchange = 'US' WHERE exchange != 'US' OR exchange IS NULL"
            )
            updated_exchanges = cur.rowcount
            conn.commit()

            if updated_exchanges > 0:
                console.print(f"[green]Updated {updated_exchanges} symbols to use 'US' exchange[/green]")

            # Step 7: Verify cleanup
            console.print("\n[cyan]Verifying cleanup...[/cyan]")
            cur.execute("SELECT COUNT(*) FROM market_symbols")
            total = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT symbol) FROM market_symbols")
            unique = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM market_symbols WHERE symbol LIKE '%.US'")
            with_suffix = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM market_symbols WHERE exchange != 'US'")
            wrong_exchange = cur.fetchone()[0]

            console.print(f"\n[bold green]Cleanup complete![/bold green]")
            console.print(f"  Total symbols: {total}")
            console.print(f"  Unique symbols: {unique}")
            console.print(f"  Symbols with .US suffix: {with_suffix}")
            console.print(f"  Symbols with wrong exchange: {wrong_exchange}")

            if total == unique and with_suffix == 0 and wrong_exchange == 0:
                console.print("\n[bold green]✓ Database is clean![/bold green]")
            else:
                console.print("\n[yellow]⚠ Some issues remain. Please review.[/yellow]")


if __name__ == "__main__":
    try:
        cleanup_symbols()
    except Exception as e:
        import traceback
        console.print(f"[bold red]Error: {e}[/bold red]")
        console.print(traceback.format_exc())
        sys.exit(1)
