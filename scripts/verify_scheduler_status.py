#!/usr/bin/env python3
"""
Verify scheduler status and data completeness.

This script checks:
1. If scheduler is running
2. Latest data timestamps in database
3. Scheduler state in database
4. Recent prediction runs
5. Recent signals generated
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.settings import get_settings
from rich.console import Console
from rich.table import Table

console = Console()


def check_scheduler_process():
    """Check if scheduler process is running."""
    console.print("\n[bold cyan]1. Scheduler Process Status[/bold cyan]")
    
    pid_file = Path("/opt/DrummondGeometry-evals/.dgas_scheduler.pid")
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            import os
            try:
                os.kill(pid, 0)  # Check if process exists
                console.print(f"[green]✓[/green] Scheduler is running (PID: {pid})")
                return True
            except OSError:
                console.print(f"[red]✗[/red] PID file exists but process not running (stale PID: {pid})")
                return False
        except Exception as e:
            console.print(f"[red]✗[/red] Error reading PID file: {e}")
            return False
    else:
        console.print("[yellow]⚠[/yellow] Scheduler PID file not found - scheduler may not be running")
        return False


def check_latest_data():
    """Check latest data timestamps in database."""
    console.print("\n[bold cyan]2. Latest Data Timestamps[/bold cyan]")
    
    settings = get_settings()
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get latest timestamp for 30m data
            cur.execute("""
                SELECT MAX(md.timestamp) as latest_ts, COUNT(DISTINCT s.symbol) as symbol_count
                FROM market_data md
                JOIN market_symbols s ON s.symbol_id = md.symbol_id
                WHERE md.interval_type = '30m'
            """)
            row = cur.fetchone()
            if row and row[0]:
                latest_ts = row[0]
                symbol_count = row[1]
                console.print(f"[green]✓[/green] Latest 30m data: {latest_ts} UTC")
                console.print(f"   Symbols with data: {symbol_count}")
                
                # Check if we have data through Nov 7, 2025 4:00 PM ET (21:00 UTC)
                target_ts = datetime(2025, 11, 7, 21, 0, tzinfo=timezone.utc)
                if latest_ts >= target_ts:
                    console.print(f"[green]✓[/green] Data is backfilled through Nov 7, 2025 4:00 PM ET")
                else:
                    console.print(f"[yellow]⚠[/yellow] Data is NOT backfilled through Nov 7, 2025 4:00 PM ET")
                    console.print(f"   Latest: {latest_ts}, Target: {target_ts}")
            else:
                console.print("[red]✗[/red] No 30m data found in database")


def check_scheduler_state():
    """Check scheduler state in database."""
    console.print("\n[bold cyan]3. Scheduler State (Database)[/bold cyan]")
    
    settings = get_settings()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT status, last_run_timestamp, next_scheduled_run, error_message, updated_at
                FROM scheduler_state
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                status, last_run, next_run, error, updated = row
                console.print(f"Status: [{'green' if status == 'RUNNING' else 'yellow' if status == 'STOPPED' else 'red'}]{status}[/]")
                if last_run:
                    console.print(f"Last run: {last_run}")
                if next_run:
                    console.print(f"Next scheduled: {next_run}")
                if error:
                    console.print(f"[red]Error:[/red] {error}")
                console.print(f"Last updated: {updated}")
            else:
                console.print("[yellow]⚠[/yellow] No scheduler state found in database")


def check_recent_runs():
    """Check recent prediction runs."""
    console.print("\n[bold cyan]4. Recent Prediction Runs[/bold cyan]")
    
    settings = get_settings()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    run_timestamp,
                    symbols_processed,
                    signals_generated,
                    execution_time_ms,
                    status,
                    errors
                FROM prediction_runs
                ORDER BY run_timestamp DESC
                LIMIT 10
            """)
            rows = cur.fetchall()
            if rows:
                table = Table(title="Recent Prediction Runs")
                table.add_column("Timestamp", style="cyan")
                table.add_column("Symbols", justify="right")
                table.add_column("Signals", justify="right")
                table.add_column("Time (ms)", justify="right")
                table.add_column("Status", style="green")
                
                for row in rows:
                    ts, symbols, signals, time_ms, status, errors = row
                    status_style = "green" if status == "SUCCESS" else "red"
                    table.add_row(
                        str(ts),
                        str(symbols),
                        str(signals),
                        str(time_ms),
                        f"[{status_style}]{status}[/]"
                    )
                console.print(table)
            else:
                console.print("[yellow]⚠[/yellow] No prediction runs found in database")


def check_recent_signals():
    """Check recent signals generated."""
    console.print("\n[bold cyan]5. Recent Signals Generated[/bold cyan]")
    
    settings = get_settings()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    gs.signal_timestamp,
                    ms.symbol,
                    gs.signal_type,
                    gs.confidence,
                    gs.signal_strength,
                    gs.notification_sent
                FROM generated_signals gs
                JOIN market_symbols ms ON ms.symbol_id = gs.symbol_id
                ORDER BY gs.signal_timestamp DESC
                LIMIT 10
            """)
            rows = cur.fetchall()
            if rows:
                table = Table(title="Recent Signals")
                table.add_column("Timestamp", style="cyan")
                table.add_column("Symbol", style="yellow")
                table.add_column("Type", style="magenta")
                table.add_column("Confidence", justify="right")
                table.add_column("Strength", justify="right")
                table.add_column("Notified", justify="center")
                
                for row in rows:
                    ts, symbol, sig_type, conf, strength, notified = row
                    notified_str = "[green]✓[/green]" if notified else "[red]✗[/red]"
                    table.add_row(
                        str(ts),
                        symbol,
                        sig_type,
                        f"{conf:.2f}",
                        f"{strength:.2f}",
                        notified_str
                    )
                console.print(table)
            else:
                console.print("[yellow]⚠[/yellow] No signals found in database")


def check_symbols_in_database():
    """Check symbols registered in database."""
    console.print("\n[bold cyan]6. Symbols in Database[/bold cyan]")
    
    settings = get_settings()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as total, COUNT(CASE WHEN is_active THEN 1 END) as active
                FROM market_symbols
            """)
            row = cur.fetchone()
            if row:
                total, active = row
                console.print(f"Total symbols: {total}")
                console.print(f"Active symbols: {active}")
                
                # Check symbols from full_symbols.txt
                symbols_file = Path("/opt/DrummondGeometry-evals/data/full_symbols.txt")
                if symbols_file.exists():
                    with open(symbols_file) as f:
                        # File has symbols space-separated on one line
                        content = f.read().strip()
                        file_symbols = set(s.strip().replace('.US', '') for s in content.split() if s.strip())
                    
                    cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true")
                    db_symbols = set(row[0] for row in cur.fetchall())
                    
                    missing = file_symbols - db_symbols
                    if missing:
                        console.print(f"[yellow]⚠[/yellow] {len(missing)} symbols from file not in database")
                        console.print(f"   First 10 missing: {', '.join(list(missing)[:10])}")
                    else:
                        console.print(f"[green]✓[/green] All {len(file_symbols)} symbols from file are in database")


def main():
    """Run all checks."""
    console.print("[bold]DGAS Scheduler Verification Report[/bold]")
    console.print("=" * 70)
    
    check_scheduler_process()
    check_latest_data()
    check_scheduler_state()
    check_recent_runs()
    check_recent_signals()
    check_symbols_in_database()
    
    console.print("\n[bold]Verification Complete[/bold]")


if __name__ == "__main__":
    main()
