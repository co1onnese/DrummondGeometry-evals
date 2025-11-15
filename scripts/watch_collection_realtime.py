#!/usr/bin/env python3
"""
Real-time log watcher for data collection service.
Monitors screen session output and database for 30 minutes.
"""

import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich import box

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection

console = Console()

def get_recent_runs(limit=5):
    """Get recent collection runs from database."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT run_timestamp, status, symbols_requested, symbols_updated,
                           bars_fetched, bars_stored, execution_time_ms
                    FROM data_collection_runs
                    ORDER BY run_timestamp DESC
                    LIMIT %s
                """, (limit,))
                return cur.fetchall()
    except Exception as e:
        return None

def get_screen_output():
    """Get current screen session output."""
    try:
        result = subprocess.run(
            ["screen", "-S", "data-collection", "-X", "hardcopy", "/tmp/dc_watch.txt"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and Path("/tmp/dc_watch.txt").exists():
            with open("/tmp/dc_watch.txt", "rb") as f:
                content = f.read()
            # Decode and get last 30 lines
            try:
                lines = content.decode('utf-8', errors='ignore').split('\n')
                return [l for l in lines[-30:] if l.strip()]
            except:
                return []
    except Exception:
        pass
    return []

def extract_key_events(lines):
    """Extract key events from log lines."""
    events = []
    for line in lines:
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in ['error', 'exception', 'failed', 'timeout', 'timed out']):
            events.append(('error', line))
        elif 'processing symbol' in line_lower:
            events.append(('symbol', line))
        elif 'batch' in line_lower and 'complete' in line_lower:
            events.append(('batch', line))
        elif 'collection cycle' in line_lower and ('complete' in line_lower or 'started' in line_lower):
            events.append(('cycle', line))
        elif 'api' in line_lower or 'eodhd' in line_lower:
            events.append(('api', line))
    return events

def create_status_table(runs, screen_lines, events):
    """Create status display table."""
    table = Table(title="Data Collection Monitor", show_header=True, box=box.ROUNDED)
    table.add_column("Time", style="cyan", width=12)
    table.add_column("Status", style="green", width=10)
    table.add_column("Progress", style="yellow", width=20)
    table.add_column("Details", style="white", width=40)
    
    # Add recent runs
    if runs:
        for run in runs[:3]:
            ts = run[0]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
            age_str = f"{age:.1f}m ago"
            
            status_style = "green" if run[1] == "SUCCESS" else "red" if run[1] == "FAILED" else "yellow"
            progress = f"{run[3]}/{run[2]} symbols"
            details = f"{run[5]} bars, {run[6]/1000:.1f}s"
            
            table.add_row(age_str, f"[{status_style}]{run[1]}[/]", progress, details)
    else:
        table.add_row("N/A", "No data", "N/A", "N/A")
    
    return table

def main():
    console.print(Panel.fit("[bold cyan]Data Collection Log Monitor[/bold cyan]\nMonitoring for 30 minutes...", box=box.DOUBLE))
    
    start_time = time.time()
    duration = 30 * 60  # 30 minutes
    check_interval = 30  # Check every 30 seconds
    
    last_run_count = 0
    hang_detected = False
    
    try:
        while time.time() - start_time < duration:
            elapsed = time.time() - start_time
            elapsed_min = int(elapsed / 60)
            elapsed_sec = int(elapsed % 60)
            
            # Get current state
            runs = get_recent_runs()
            screen_lines = get_screen_output()
            events = extract_key_events(screen_lines)
            
            # Check for new runs
            current_run_count = len(runs) if runs else 0
            if current_run_count > last_run_count:
                console.print(f"[green]✓ New collection run detected! (Run #{current_run_count})[/green]")
                last_run_count = current_run_count
            
            # Check for hangs
            if runs:
                most_recent = runs[0]
                most_recent_ts = most_recent[0]
                if most_recent_ts.tzinfo is None:
                    most_recent_ts = most_recent_ts.replace(tzinfo=timezone.utc)
                age_minutes = (datetime.now(timezone.utc) - most_recent_ts).total_seconds() / 60
                
                # If no new run in 15 minutes and cycle should be running, possible hang
                if age_minutes > 15 and not hang_detected:
                    # Check if cycle is running
                    cycle_running = any('collection cycle' in line.lower() and 'running' in line.lower() 
                                      for line in screen_lines)
                    if cycle_running:
                        console.print(f"[yellow]⚠ Possible hang detected - last run {age_minutes:.1f} minutes ago[/yellow]")
                        hang_detected = True
            
            # Display status
            status_table = create_status_table(runs, screen_lines, events)
            
            # Show recent events
            console.print(f"\n[dim]Elapsed: {elapsed_min}m {elapsed_sec}s | Next check in {check_interval}s[/dim]")
            console.print(status_table)
            
            # Show recent key events
            if events:
                console.print("\n[bold]Recent Key Events:[/bold]")
                for event_type, event_line in events[-5:]:
                    style = "red" if event_type == "error" else "yellow" if event_type == "api" else "cyan"
                    console.print(f"  [{style}]{event_type.upper()}:[/{style}] {event_line[:80]}")
            
            # Show last few log lines
            if screen_lines:
                console.print("\n[bold]Recent Log Output:[/bold]")
                for line in screen_lines[-5:]:
                    if line.strip():
                        console.print(f"  [dim]{line[:100]}[/dim]")
            
            console.print("\n" + "─" * 80)
            
            # Wait for next check
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitoring interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error during monitoring: {e}[/red]", exc_info=True)
    
    # Final summary
    console.print("\n[bold cyan]=== Monitoring Complete ===[/bold cyan]")
    runs = get_recent_runs(limit=10)
    if runs:
        console.print(f"\n[green]Total runs during monitoring: {len(runs)}[/green]")
        console.print("\n[bold]All Runs During Monitoring:[/bold]")
        for run in runs:
            ts = run[0]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
            status_style = "green" if run[1] == "SUCCESS" else "red" if run[1] == "FAILED" else "yellow"
            console.print(
                f"  {ts.strftime('%H:%M:%S')} ({age:.1f}m ago) | "
                f"[{status_style}]{run[1]}[/{status_style}] | "
                f"{run[3]}/{run[2]} symbols | {run[5]} bars | {run[6]/1000:.1f}s"
            )

if __name__ == "__main__":
    main()
