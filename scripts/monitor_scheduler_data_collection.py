#!/usr/bin/env python3
"""
Monitor scheduler data collection to verify it's collecting real-time data.

This script:
1. Checks if scheduler is running
2. Monitors scheduler logs for data update activity
3. Tracks data freshness over time
4. Verifies data updates are happening
5. Alerts if data collection is failing
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.data.repository import get_latest_timestamp, get_symbol_id
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout

console = Console()


def check_scheduler_running() -> dict:
    """Check if scheduler process is running."""
    import subprocess
    
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        scheduler_running = "dgas scheduler" in result.stdout or "PredictionScheduler" in result.stdout
        pid_file_exists = Path("/opt/DrummondGeometry-evals/.dgas_scheduler.pid").exists()
        
        if pid_file_exists:
            try:
                pid = int(Path("/opt/DrummondGeometry-evals/.dgas_scheduler.pid").read_text().strip())
                process_exists = subprocess.run(
                    ["kill", "-0", str(pid)],
                    capture_output=True,
                    timeout=2
                ).returncode == 0
            except:
                process_exists = False
        else:
            process_exists = False
        
        return {
            'running': scheduler_running or process_exists,
            'pid_file_exists': pid_file_exists,
            'process_exists': process_exists,
        }
    except Exception as e:
        return {
            'running': False,
            'error': str(e),
        }


def check_recent_scheduler_activity() -> dict:
    """Check scheduler logs for recent activity."""
    log_file = Path("/var/log/dgas/scheduler.log")
    
    if not log_file.exists():
        return {
            'log_exists': False,
            'recent_activity': False,
        }
    
    try:
        # Read last 100 lines
        with open(log_file, 'r') as f:
            lines = f.readlines()
            last_lines = lines[-100:] if len(lines) > 100 else lines
        
        # Look for key indicators
        now = datetime.now(timezone.utc)
        recent_activity = False
        last_cycle_time = None
        data_updates = []
        errors = []
        
        for line in last_lines:
            line_lower = line.lower()
            
            # Check for recent execution
            if "executing prediction cycle" in line_lower:
                # Try to extract timestamp
                try:
                    # Look for timestamp in log line
                    if "INFO" in line:
                        recent_activity = True
                except:
                    pass
            
            # Check for data updates
            if "incremental_update" in line_lower or "stored=" in line_lower:
                data_updates.append(line.strip()[:100])
            
            # Check for errors
            if "error" in line_lower or "failed" in line_lower:
                errors.append(line.strip()[:100])
        
        return {
            'log_exists': True,
            'recent_activity': recent_activity,
            'data_updates_count': len(data_updates),
            'recent_data_updates': data_updates[-5:] if data_updates else [],
            'errors_count': len(errors),
            'recent_errors': errors[-5:] if errors else [],
            'log_lines_checked': len(last_lines),
        }
    except Exception as e:
        return {
            'log_exists': True,
            'error': str(e),
        }


def check_data_update_tracking(sample_symbols: list[str] = None) -> dict:
    """
    Track when data was last updated by checking timestamps.
    
    Args:
        sample_symbols: Symbols to check (default: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA'])
    """
    if sample_symbols is None:
        sample_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'NFLX']
    
    now = datetime.now(timezone.utc)
    results = []
    
    with get_connection() as conn:
        for symbol in sample_symbols:
            symbol_id = get_symbol_id(conn, symbol)
            if symbol_id:
                latest_ts = get_latest_timestamp(conn, symbol_id, "30m")
                if latest_ts:
                    age_minutes = (now - latest_ts).total_seconds() / 60
                    results.append({
                        'symbol': symbol,
                        'latest_timestamp': latest_ts,
                        'age_minutes': age_minutes,
                        'fresh': age_minutes <= 60,
                    })
                else:
                    results.append({
                        'symbol': symbol,
                        'latest_timestamp': None,
                        'age_minutes': None,
                        'fresh': False,
                    })
    
    return {
        'checked_at': now,
        'results': results,
        'fresh_count': sum(1 for r in results if r.get('fresh')),
        'total_checked': len(results),
    }


def check_prediction_runs_recent() -> dict:
    """Check if prediction runs have been happening recently."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get recent prediction runs
            cur.execute("""
                SELECT 
                    run_id,
                    run_timestamp,
                    symbols_processed,
                    signals_generated,
                    status,
                    interval_type
                FROM prediction_runs
                ORDER BY run_timestamp DESC
                LIMIT 10
            """)
            
            runs = []
            for row in cur.fetchall():
                runs.append({
                    'run_id': row[0],
                    'timestamp': row[1],
                    'symbols_processed': row[2],
                    'signals_generated': row[3],
                    'status': row[4],
                    'interval': row[5],
                })
            
            if runs:
                latest_run = runs[0]
                now = datetime.now(timezone.utc)
                age_minutes = (now - latest_run['timestamp']).total_seconds() / 60
                
                return {
                    'has_runs': True,
                    'total_runs': len(runs),
                    'latest_run': latest_run,
                    'age_minutes': age_minutes,
                    'recent': age_minutes <= 30,  # Within last 30 minutes
                    'all_runs': runs,
                }
            else:
                return {
                    'has_runs': False,
                    'total_runs': 0,
                }


def display_monitoring_dashboard(scheduler_status: dict, log_activity: dict, 
                                 data_tracking: dict, prediction_runs: dict):
    """Display comprehensive monitoring dashboard."""
    
    # Create layout
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )
    
    # Header
    layout["header"].update(Panel.fit(
        "[bold cyan]Scheduler Data Collection Monitor[/bold cyan]",
        border_style="cyan"
    ))
    
    # Left panel - Scheduler Status
    scheduler_table = Table(title="Scheduler Status", show_header=True)
    scheduler_table.add_column("Metric")
    scheduler_table.add_column("Value")
    
    if scheduler_status.get('running'):
        scheduler_table.add_row("Status", "[green]Running[/green]")
    else:
        scheduler_table.add_row("Status", "[red]Not Running[/red]")
    
    scheduler_table.add_row("PID File", "✓ Exists" if scheduler_status.get('pid_file_exists') else "✗ Missing")
    scheduler_table.add_row("Process", "✓ Active" if scheduler_status.get('process_exists') else "✗ Not Found")
    
    # Right panel - Recent Activity
    activity_table = Table(title="Recent Activity", show_header=True)
    activity_table.add_column("Metric")
    activity_table.add_column("Value")
    
    if log_activity.get('log_exists'):
        activity_table.add_row("Log File", "[green]Exists[/green]")
        activity_table.add_row("Recent Activity", "✓ Yes" if log_activity.get('recent_activity') else "✗ No")
        activity_table.add_row("Data Updates", str(log_activity.get('data_updates_count', 0)))
        activity_table.add_row("Errors", str(log_activity.get('errors_count', 0)))
    else:
        activity_table.add_row("Log File", "[red]Missing[/red]")
    
    # Prediction runs
    if prediction_runs.get('has_runs'):
        latest = prediction_runs['latest_run']
        age = prediction_runs['age_minutes']
        if age <= 30:
            status = f"[green]{age:.1f} min ago[/green]"
        elif age <= 60:
            status = f"[yellow]{age:.1f} min ago[/yellow]"
        else:
            status = f"[red]{age:.1f} min ago[/red]"
        
        activity_table.add_row("Latest Run", status)
        activity_table.add_row("Symbols Processed", str(latest['symbols_processed']))
        activity_table.add_row("Signals Generated", str(latest['signals_generated']))
    else:
        activity_table.add_row("Latest Run", "[red]No runs found[/red]")
    
    # Data freshness
    data_table = Table(title="Data Freshness (Sample)", show_header=True)
    data_table.add_column("Symbol")
    data_table.add_column("Latest Data")
    data_table.add_column("Age")
    data_table.add_column("Status")
    
    for result in data_tracking['results']:
        if result['latest_timestamp']:
            age = result['age_minutes']
            if age <= 60:
                status = "[green]Fresh[/green]"
            elif age <= 240:
                status = "[yellow]Recent[/yellow]"
            else:
                status = "[red]Stale[/red]"
            
            data_table.add_row(
                result['symbol'],
                result['latest_timestamp'].strftime("%H:%M UTC"),
                f"{age:.0f} min",
                status
            )
        else:
            data_table.add_row(result['symbol'], "No data", "-", "[red]Missing[/red]")
    
    layout["left"].update(scheduler_table)
    layout["right"].update(activity_table)
    
    # Footer with recommendations
    recommendations = []
    
    if not scheduler_status.get('running'):
        recommendations.append("[red]⚠ Scheduler is not running - start it immediately[/red]")
    
    if prediction_runs.get('has_runs'):
        if prediction_runs['age_minutes'] > 30:
            recommendations.append(f"[yellow]⚠ Last prediction run was {prediction_runs['age_minutes']:.1f} minutes ago[/yellow]")
    
    if data_tracking['fresh_count'] < data_tracking['total_checked'] * 0.5:
        recommendations.append("[yellow]⚠ Most symbols have stale data - scheduler may not be updating[/yellow]")
    
    if not recommendations:
        recommendations.append("[green]✓ System appears to be operating normally[/green]")
    
    layout["footer"].update(Panel("\n".join(recommendations), title="Recommendations", border_style="yellow"))
    
    console.print(layout)
    console.print()
    console.print(data_table)


def main():
    """Main monitoring function."""
    console.print("\n[bold cyan]DGAS Scheduler Data Collection Monitor[/bold cyan]\n")
    
    # Check all components
    scheduler_status = check_scheduler_running()
    log_activity = check_recent_scheduler_activity()
    data_tracking = check_data_update_tracking()
    prediction_runs = check_prediction_runs_recent()
    
    # Display dashboard
    display_monitoring_dashboard(scheduler_status, log_activity, data_tracking, prediction_runs)
    
    # Return status code
    if not scheduler_status.get('running'):
        return 2
    elif prediction_runs.get('has_runs') and prediction_runs['age_minutes'] > 60:
        return 1
    elif data_tracking['fresh_count'] < data_tracking['total_checked'] * 0.5:
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
