#!/usr/bin/env python3
"""
Comprehensive diagnostic script for data collection service.

Investigates why data collection isn't working by checking:
- Service status (screen sessions, PID files)
- Recent collection runs from database
- Latest data timestamps
- Configuration
- API connectivity
- Logs (if available)
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.config import load_settings
from dgas.db import get_connection
from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings

console = Console()


def check_screen_sessions() -> Dict[str, any]:
    """Check for running screen sessions."""
    result = {
        "sessions": [],
        "data_collection_found": False,
        "scheduler_found": False,
        "dashboard_found": False,
    }
    
    try:
        # List all screen sessions
        output = subprocess.run(
            ["screen", "-ls"],
            capture_output=True,
            text=True,
            check=False,
        )
        
        if output.returncode == 0:
            lines = output.stdout.strip().split("\n")
            for line in lines:
                if "No Sockets found" in line:
                    continue
                if ".dgas" in line or "data" in line.lower() or "scheduler" in line.lower() or "dashboard" in line.lower():
                    result["sessions"].append(line.strip())
                    if "data" in line.lower() or "collection" in line.lower():
                        result["data_collection_found"] = True
                    if "scheduler" in line.lower():
                        result["scheduler_found"] = True
                    if "dashboard" in line.lower():
                        result["dashboard_found"] = True
    except FileNotFoundError:
        result["error"] = "screen command not found"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def check_pid_files() -> Dict[str, any]:
    """Check for PID files."""
    result = {
        "pid_files": [],
        "data_collection_running": False,
    }
    
    pid_file = Path(".dgas_data_collection.pid")
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            # Check if process is running
            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                result["pid_files"].append({
                    "file": str(pid_file),
                    "pid": pid,
                    "running": True,
                })
                result["data_collection_running"] = True
            except OSError:
                result["pid_files"].append({
                    "file": str(pid_file),
                    "pid": pid,
                    "running": False,
                })
        except (ValueError, OSError) as e:
            result["pid_files"].append({
                "file": str(pid_file),
                "error": str(e),
            })
    
    return result


def get_recent_collection_runs(limit: int = 10) -> List[Dict]:
    """Get recent data collection runs from database."""
    runs = []
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        run_id,
                        run_timestamp,
                        interval_type,
                        symbols_requested,
                        symbols_updated,
                        symbols_failed,
                        bars_fetched,
                        bars_stored,
                        execution_time_ms,
                        status,
                        error_count
                    FROM data_collection_runs
                    ORDER BY run_timestamp DESC
                    LIMIT %s
                """, (limit,))
                
                for row in cur.fetchall():
                    runs.append({
                        "run_id": row[0],
                        "run_timestamp": row[1],
                        "interval_type": row[2],
                        "symbols_requested": row[3],
                        "symbols_updated": row[4],
                        "symbols_failed": row[5],
                        "bars_fetched": row[6],
                        "bars_stored": row[7],
                        "execution_time_ms": row[8],
                        "status": row[9],
                        "error_count": row[10],
                    })
    except Exception as e:
        console.print(f"[red]Error querying collection runs: {e}[/red]")
    
    return runs


def get_latest_data_timestamps(limit: int = 10) -> List[Dict]:
    """Get latest data timestamps for symbols."""
    timestamps = []
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        ms.symbol,
                        md.interval_type,
                        MAX(md.timestamp) as latest_timestamp,
                        COUNT(*) as bar_count
                    FROM market_data md
                    JOIN market_symbols ms ON md.symbol_id = ms.symbol_id
                    WHERE ms.is_active = true
                    GROUP BY ms.symbol, md.interval_type
                    ORDER BY latest_timestamp DESC
                    LIMIT %s
                """, (limit,))
                
                for row in cur.fetchall():
                    age_minutes = None
                    if row[2]:
                        ts = row[2]
                        # Ensure timezone-aware
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        age = datetime.now(timezone.utc) - ts
                        age_minutes = age.total_seconds() / 60.0
                    
                    timestamps.append({
                        "symbol": row[0],
                        "interval": row[1],
                        "latest_timestamp": row[2],
                        "age_minutes": age_minutes,
                        "bar_count": row[3],
                    })
    except Exception as e:
        console.print(f"[red]Error querying data timestamps: {e}[/red]")
    
    return timestamps


def get_data_freshness_summary() -> Dict:
    """Get overall data freshness summary."""
    summary = {
        "total_symbols": 0,
        "symbols_with_data": 0,
        "stale_symbols": 0,
        "average_age_minutes": None,
        "oldest_data_minutes": None,
    }
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Get total active symbols
                cur.execute("SELECT COUNT(*) FROM market_symbols WHERE is_active = true")
                summary["total_symbols"] = cur.fetchone()[0]
                
                # Get symbols with data and their latest timestamps
                cur.execute("""
                    SELECT 
                        ms.symbol,
                        MAX(md.timestamp) as latest_timestamp
                    FROM market_symbols ms
                    LEFT JOIN market_data md ON ms.symbol_id = md.symbol_id
                    WHERE ms.is_active = true
                    GROUP BY ms.symbol
                    HAVING MAX(md.timestamp) IS NOT NULL
                """)
                
                now = datetime.now(timezone.utc)
                ages = []
                stale_count = 0
                
                for row in cur.fetchall():
                    if row[1]:
                        ts = row[1]
                        # Ensure timezone-aware
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        age = (now - ts).total_seconds() / 60.0
                        ages.append(age)
                        if age > 60:  # Stale if > 60 minutes
                            stale_count += 1
                
                summary["symbols_with_data"] = len(ages)
                summary["stale_symbols"] = stale_count
                if ages:
                    summary["average_age_minutes"] = sum(ages) / len(ages)
                    summary["oldest_data_minutes"] = max(ages)
    except Exception as e:
        console.print(f"[red]Error getting freshness summary: {e}[/red]")
    
    return summary


def check_configuration() -> Dict:
    """Check data collection configuration."""
    config_info = {}
    
    try:
        unified_settings = load_settings()
        dc_config = unified_settings.data_collection
        
        if dc_config:
            config_info = {
                "enabled": dc_config.enabled,
                "use_websocket": dc_config.use_websocket,
                "interval_market_hours": dc_config.interval_market_hours,
                "interval_after_hours": dc_config.interval_after_hours,
                "interval_weekends": dc_config.interval_weekends,
                "batch_size": dc_config.batch_size,
                "requests_per_minute": dc_config.requests_per_minute,
                "max_retries": dc_config.max_retries,
            }
        else:
            config_info["error"] = "Data collection config not found"
    except Exception as e:
        config_info["error"] = str(e)
    
    return config_info


def test_api_connectivity() -> Dict:
    """Test EODHD API connectivity."""
    result = {
        "connected": False,
        "error": None,
    }
    
    try:
        settings = get_settings()
        if not settings.eodhd_api_token:
            result["error"] = "EODHD API token not configured"
            return result
        
        client = EODHDClient(EODHDConfig.from_settings(settings))
        
        # Try a simple API call (fetch recent data for a known symbol)
        try:
            bars = client.fetch_intraday("AAPL", interval="30m", limit=1)
            result["connected"] = True
            result["test_symbol"] = "AAPL"
            result["bars_received"] = len(bars)
        except Exception as e:
            result["error"] = f"API call failed: {e}"
        
        client.close()
    except Exception as e:
        result["error"] = f"Failed to create client: {e}"
    
    return result


def check_active_symbols() -> Dict:
    """Check active symbols in database."""
    result = {
        "count": 0,
        "sample": [],
    }
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM market_symbols WHERE is_active = true")
                result["count"] = cur.fetchone()[0]
                
                cur.execute("""
                    SELECT symbol 
                    FROM market_symbols 
                    WHERE is_active = true 
                    ORDER BY symbol 
                    LIMIT 10
                """)
                result["sample"] = [row[0] for row in cur.fetchall()]
    except Exception as e:
        result["error"] = str(e)
    
    return result


def main():
    """Run comprehensive diagnostics."""
    console.print(Panel.fit("[bold cyan]Data Collection Service Diagnostics[/bold cyan]", box=box.DOUBLE))
    console.print()
    
    # 1. Check screen sessions
    console.print("[bold]1. Checking Screen Sessions...[/bold]")
    screen_info = check_screen_sessions()
    if screen_info.get("error"):
        console.print(f"[yellow]  ⚠ {screen_info['error']}[/yellow]")
    elif screen_info["sessions"]:
        console.print(f"[green]  ✓ Found {len(screen_info['sessions'])} screen session(s)[/green]")
        for session in screen_info["sessions"]:
            console.print(f"    - {session}")
    else:
        console.print("[yellow]  ⚠ No screen sessions found[/yellow]")
    console.print()
    
    # 2. Check PID files
    console.print("[bold]2. Checking PID Files...[/bold]")
    pid_info = check_pid_files()
    if pid_info["pid_files"]:
        for pid_file in pid_info["pid_files"]:
            if pid_file.get("running"):
                console.print(f"[green]  ✓ PID file found: {pid_file['file']} (PID: {pid_file['pid']}, running)[/green]")
            else:
                console.print(f"[yellow]  ⚠ PID file found: {pid_file['file']} (PID: {pid_file['pid']}, not running)[/yellow]")
    else:
        console.print("[yellow]  ⚠ No PID file found[/yellow]")
    console.print()
    
    # 3. Check recent collection runs
    console.print("[bold]3. Recent Data Collection Runs...[/bold]")
    runs = get_recent_collection_runs(limit=10)
    if runs:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Run ID")
        table.add_column("Timestamp")
        table.add_column("Interval")
        table.add_column("Updated")
        table.add_column("Failed")
        table.add_column("Bars Stored")
        table.add_column("Status")
        
        for run in runs[:10]:
            timestamp_str = run["run_timestamp"].strftime("%Y-%m-%d %H:%M:%S") if run["run_timestamp"] else "N/A"
            table.add_row(
                str(run["run_id"]),
                timestamp_str,
                run["interval_type"],
                f"{run['symbols_updated']}/{run['symbols_requested']}",
                str(run["symbols_failed"]),
                str(run["bars_stored"]),
                run["status"],
            )
        
        console.print(table)
        
        # Check if most recent run is recent
        if runs:
            most_recent = runs[0]
            run_ts = most_recent["run_timestamp"]
            # Ensure timezone-aware
            if run_ts.tzinfo is None:
                run_ts = run_ts.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - run_ts
            age_hours = age.total_seconds() / 3600.0
            if age_hours > 24:
                console.print(f"[red]  ⚠ Most recent run was {age_hours:.1f} hours ago![/red]")
            elif age_hours > 2:
                console.print(f"[yellow]  ⚠ Most recent run was {age_hours:.1f} hours ago[/yellow]")
            else:
                console.print(f"[green]  ✓ Most recent run was {age_hours:.1f} hours ago[/green]")
    else:
        console.print("[red]  ✗ No collection runs found in database![/red]")
    console.print()
    
    # 4. Check data freshness
    console.print("[bold]4. Data Freshness Summary...[/bold]")
    freshness = get_data_freshness_summary()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Metric")
    table.add_column("Value")
    
    table.add_row("Total Active Symbols", str(freshness["total_symbols"]))
    table.add_row("Symbols with Data", str(freshness["symbols_with_data"]))
    if freshness["average_age_minutes"] is not None:
        table.add_row("Average Age", f"{freshness['average_age_minutes']:.1f} minutes")
        table.add_row("Oldest Data", f"{freshness['oldest_data_minutes']:.1f} minutes")
    table.add_row("Stale Symbols (>60min)", str(freshness["stale_symbols"]))
    
    console.print(table)
    console.print()
    
    # 5. Latest data timestamps
    console.print("[bold]5. Latest Data Timestamps (Top 10)...[/bold]")
    timestamps = get_latest_data_timestamps(limit=10)
    if timestamps:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Symbol")
        table.add_column("Interval")
        table.add_column("Latest Timestamp")
        table.add_column("Age (minutes)")
        table.add_column("Bars")
        
        for ts in timestamps:
            timestamp_str = ts["latest_timestamp"].strftime("%Y-%m-%d %H:%M:%S") if ts["latest_timestamp"] else "N/A"
            age_str = f"{ts['age_minutes']:.1f}" if ts["age_minutes"] is not None else "N/A"
            table.add_row(
                ts["symbol"],
                ts["interval"],
                timestamp_str,
                age_str,
                str(ts["bar_count"]),
            )
        
        console.print(table)
    else:
        console.print("[yellow]  ⚠ No data timestamps found[/yellow]")
    console.print()
    
    # 6. Check configuration
    console.print("[bold]6. Configuration Check...[/bold]")
    config = check_configuration()
    if config.get("error"):
        console.print(f"[red]  ✗ {config['error']}[/red]")
    else:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Setting")
        table.add_column("Value")
        
        table.add_row("Enabled", "Yes" if config.get("enabled") else "No")
        table.add_row("Use WebSocket", "Yes" if config.get("use_websocket") else "No")
        table.add_row("Market Hours Interval", config.get("interval_market_hours", "N/A"))
        table.add_row("After Hours Interval", config.get("interval_after_hours", "N/A"))
        table.add_row("Weekend Interval", config.get("interval_weekends", "N/A"))
        table.add_row("Batch Size", str(config.get("batch_size", "N/A")))
        table.add_row("Requests/Min", str(config.get("requests_per_minute", "N/A")))
        table.add_row("Max Retries", str(config.get("max_retries", "N/A")))
        
        console.print(table)
        
        if not config.get("enabled"):
            console.print("[red]  ✗ Data collection is DISABLED in configuration![/red]")
    console.print()
    
    # 7. Test API connectivity
    console.print("[bold]7. API Connectivity Test...[/bold]")
    api_test = test_api_connectivity()
    if api_test["connected"]:
        console.print(f"[green]  ✓ API connection successful[/green]")
        console.print(f"    Test symbol: {api_test.get('test_symbol', 'N/A')}")
        console.print(f"    Bars received: {api_test.get('bars_received', 0)}")
    else:
        console.print(f"[red]  ✗ API connection failed: {api_test.get('error', 'Unknown error')}[/red]")
    console.print()
    
    # 8. Check active symbols
    console.print("[bold]8. Active Symbols Check...[/bold]")
    symbols_info = check_active_symbols()
    if symbols_info.get("error"):
        console.print(f"[red]  ✗ {symbols_info['error']}[/red]")
    else:
        console.print(f"[green]  ✓ {symbols_info['count']} active symbols in database[/green]")
        if symbols_info["sample"]:
            console.print(f"    Sample: {', '.join(symbols_info['sample'][:5])}...")
    console.print()
    
    # Summary and recommendations
    console.print(Panel.fit("[bold cyan]Diagnostic Summary & Recommendations[/bold cyan]", box=box.DOUBLE))
    console.print()
    
    issues = []
    recommendations = []
    
    # Check if service is running
    if not screen_info.get("data_collection_found") and not pid_info.get("data_collection_running"):
        issues.append("Data collection service does not appear to be running")
        recommendations.append("Start the service: python -m dgas data-collection start")
    
    # Check if collection runs exist
    if not runs:
        issues.append("No data collection runs found in database")
        recommendations.append("Service may not have run yet, or database tracking is not working")
    
    # Check data freshness
    if freshness.get("stale_symbols", 0) > 0:
        issues.append(f"{freshness['stale_symbols']} symbols have stale data (>60 minutes old)")
        recommendations.append("Run data collection to update stale symbols")
    
    # Check configuration
    if not config.get("enabled"):
        issues.append("Data collection is disabled in configuration")
        recommendations.append("Enable data collection in config file: data_collection.enabled = true")
    
    # Check API connectivity
    if not api_test["connected"]:
        issues.append("EODHD API connectivity test failed")
        recommendations.append("Check EODHD_API_TOKEN environment variable and API key validity")
    
    if issues:
        console.print("[bold red]Issues Found:[/bold red]")
        for issue in issues:
            console.print(f"  • {issue}")
        console.print()
        
        console.print("[bold yellow]Recommendations:[/bold yellow]")
        for rec in recommendations:
            console.print(f"  • {rec}")
    else:
        console.print("[bold green]✓ No major issues detected![/bold green]")
        console.print("  If data collection still isn't working, check logs for runtime errors.")
    
    console.print()
    console.print("[dim]To manually trigger a collection run:[/dim]")
    console.print("[dim]  python -m dgas data-collection run-once[/dim]")
    console.print()
    console.print("[dim]To check service status:[/dim]")
    console.print("[dim]  python -m dgas data-collection status[/dim]")


if __name__ == "__main__":
    main()
