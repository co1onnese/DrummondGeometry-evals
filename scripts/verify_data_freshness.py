#!/usr/bin/env python3
"""
Verify that scheduler is collecting current, near-real-time data throughout the day.

This script checks:
1. Latest data timestamps in database vs current time
2. Data freshness across all symbols
3. Whether scheduler is updating data
4. API data availability vs database data
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.data.repository import get_latest_timestamp, get_symbol_id
from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def get_data_freshness_report(interval: str = "30m", sample_symbols: int = 20) -> dict:
    """
    Generate data freshness report.
    
    Args:
        interval: Data interval to check
        sample_symbols: Number of symbols to sample for detailed analysis
    
    Returns:
        Dictionary with freshness metrics
    """
    now = datetime.now(timezone.utc)
    
    with get_connection() as conn:
        # Get all symbols
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            all_symbols = [row[0] for row in cur.fetchall()]
        
        # Get latest timestamps for all symbols
        symbol_freshness = []
        for symbol in all_symbols:
            symbol_id = get_symbol_id(conn, symbol)
            if symbol_id:
                latest_ts = get_latest_timestamp(conn, symbol_id, interval)
                if latest_ts:
                    age_minutes = (now - latest_ts).total_seconds() / 60
                    symbol_freshness.append({
                        'symbol': symbol,
                        'latest_timestamp': latest_ts,
                        'age_minutes': age_minutes,
                        'age_hours': age_minutes / 60,
                    })
        
        # Calculate statistics
        if symbol_freshness:
            ages = [s['age_minutes'] for s in symbol_freshness]
            avg_age = sum(ages) / len(ages)
            min_age = min(ages)
            max_age = max(ages)
            
            # Count by freshness buckets
            fresh_count = sum(1 for a in ages if a <= 60)  # < 1 hour
            recent_count = sum(1 for a in ages if 60 < a <= 240)  # 1-4 hours
            stale_count = sum(1 for a in ages if 240 < a <= 1440)  # 4-24 hours
            very_stale_count = sum(1 for a in ages if a > 1440)  # > 24 hours
            
            # Get sample of symbols for detailed view
            sorted_symbols = sorted(symbol_freshness, key=lambda x: x['age_minutes'])
            sample = sorted_symbols[:sample_symbols]
            
            return {
                'total_symbols': len(all_symbols),
                'symbols_with_data': len(symbol_freshness),
                'now': now,
                'statistics': {
                    'avg_age_minutes': avg_age,
                    'min_age_minutes': min_age,
                    'max_age_minutes': max_age,
                    'fresh_count': fresh_count,
                    'recent_count': recent_count,
                    'stale_count': stale_count,
                    'very_stale_count': very_stale_count,
                },
                'sample': sample,
                'all_data': symbol_freshness,
            }
        else:
            return {
                'total_symbols': len(all_symbols),
                'symbols_with_data': 0,
                'now': now,
                'statistics': None,
                'sample': [],
                'all_data': [],
            }


def check_api_latest_data(interval: str = "30m", test_symbols: list[str] = None) -> dict:
    """
    Check what's the latest data available from API.
    
    Args:
        interval: Interval to check
        test_symbols: Symbols to test (default: ['AAPL', 'MSFT', 'GOOGL'])
    
    Returns:
        Dictionary with API data availability
    """
    if test_symbols is None:
        test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']
    
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    client = EODHDClient(config)
    
    api_results = []
    now = datetime.now(timezone.utc)
    
    for symbol in test_symbols:
        try:
            # Fetch latest data without date range (gets most recent)
            bars = client.fetch_intraday(symbol, interval=interval, limit=10)
            if bars:
                latest = max(bar.timestamp for bar in bars)
                age_minutes = (now - latest).total_seconds() / 60
                api_results.append({
                    'symbol': symbol,
                    'latest_available': latest,
                    'age_minutes': age_minutes,
                    'bar_count': len(bars),
                })
            else:
                api_results.append({
                    'symbol': symbol,
                    'latest_available': None,
                    'age_minutes': None,
                    'bar_count': 0,
                })
        except Exception as e:
            api_results.append({
                'symbol': symbol,
                'latest_available': None,
                'age_minutes': None,
                'error': str(e)[:100],
            })
    
    client.close()
    
    return {
        'test_symbols': test_symbols,
        'results': api_results,
        'checked_at': now,
    }


def display_freshness_report(freshness_report: dict, api_check: dict, interval: str):
    """Display the data freshness report."""
    
    console.print(Panel.fit(
        f"[bold cyan]Data Freshness Report - {interval} Interval[/bold cyan]",
        border_style="cyan"
    ))
    console.print()
    
    # Summary statistics
    stats = freshness_report['statistics']
    if stats:
        console.print("[bold]Database Data Freshness:[/bold]")
        console.print(f"  Total Symbols: {freshness_report['total_symbols']}")
        console.print(f"  Symbols with Data: {freshness_report['symbols_with_data']}")
        console.print()
        console.print(f"  Average Age: {stats['avg_age_minutes']:.1f} minutes ({stats['avg_age_minutes']/60:.1f} hours)")
        console.print(f"  Minimum Age: {stats['min_age_minutes']:.1f} minutes")
        console.print(f"  Maximum Age: {stats['max_age_minutes']:.1f} minutes ({stats['max_age_minutes']/60:.1f} hours)")
        console.print()
        console.print("[bold]Freshness Distribution:[/bold]")
        console.print(f"  Fresh (< 1 hour): {stats['fresh_count']} symbols")
        console.print(f"  Recent (1-4 hours): {stats['recent_count']} symbols")
        console.print(f"  Stale (4-24 hours): {stats['stale_count']} symbols")
        console.print(f"  Very Stale (> 24 hours): {stats['very_stale_count']} symbols")
    else:
        console.print("[yellow]No data found in database[/yellow]")
    
    console.print()
    
    # API availability
    console.print("[bold]API Data Availability (Sample):[/bold]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Symbol")
    table.add_column("Latest Available")
    table.add_column("Age (minutes)")
    table.add_column("Status")
    
    for result in api_check['results']:
        if result.get('error'):
            table.add_row(result['symbol'], "Error", "-", f"[red]{result['error']}[/red]")
        elif result['latest_available']:
            age = result['age_minutes']
            if age <= 60:
                status = "[green]Fresh[/green]"
            elif age <= 240:
                status = "[yellow]Recent[/yellow]"
            else:
                status = "[red]Stale[/red]"
            table.add_row(
                result['symbol'],
                result['latest_available'].strftime("%Y-%m-%d %H:%M UTC"),
                f"{age:.1f}",
                status
            )
        else:
            table.add_row(result['symbol'], "No data", "-", "[red]No data[/red]")
    
    console.print(table)
    console.print()
    
    # Sample of database data
    if freshness_report['sample']:
        console.print("[bold]Database Data Sample (20 freshest symbols):[/bold]")
        sample_table = Table(show_header=True, header_style="bold magenta")
        sample_table.add_column("Symbol")
        sample_table.add_column("Latest Timestamp")
        sample_table.add_column("Age (minutes)")
        sample_table.add_column("Age (hours)")
        sample_table.add_column("Status")
        
        for item in freshness_report['sample']:
            age = item['age_minutes']
            if age <= 60:
                status = "[green]Fresh[/green]"
            elif age <= 240:
                status = "[yellow]Recent[/yellow]"
            else:
                status = "[red]Stale[/red]"
            
            sample_table.add_row(
                item['symbol'],
                item['latest_timestamp'].strftime("%Y-%m-%d %H:%M UTC"),
                f"{age:.1f}",
                f"{item['age_hours']:.2f}",
                status
            )
        
        console.print(sample_table)
        console.print()
    
    # Recommendations
    console.print("[bold]Recommendations:[/bold]")
    if stats:
        if stats['avg_age_minutes'] > 60:
            console.print(f"  [yellow]⚠ Average data age is {stats['avg_age_minutes']:.1f} minutes[/yellow]")
            console.print("  [yellow]  Consider:[/yellow]")
            console.print("    - Verify scheduler is running")
            console.print("    - Check if scheduler is actually fetching new data")
            console.print("    - Consider using shorter interval (1m, 5m) for more real-time updates")
        
        if stats['fresh_count'] < freshness_report['symbols_with_data'] * 0.8:
            console.print(f"  [yellow]⚠ Only {stats['fresh_count']}/{freshness_report['symbols_with_data']} symbols have fresh data (< 1 hour)[/yellow]")
            console.print("  [yellow]  Scheduler may not be updating all symbols regularly[/yellow]")
        
        if stats['max_age_minutes'] > 1440:
            console.print(f"  [red]⚠ Some symbols have data older than 24 hours (max: {stats['max_age_minutes']/60:.1f} hours)[/red]")
            console.print("  [red]  These symbols need immediate data refresh[/red]")
        
        if stats['avg_age_minutes'] <= 60 and stats['fresh_count'] >= freshness_report['symbols_with_data'] * 0.9:
            console.print("  [green]✓ Data is fresh - scheduler appears to be working correctly[/green]")


def main():
    """Main verification function."""
    interval = "30m"  # Current production interval
    
    console.print("\n[bold cyan]DGAS Data Freshness Verification[/bold cyan]\n")
    console.print(f"Checking {interval} interval data...\n")
    
    # Get freshness report
    freshness_report = get_data_freshness_report(interval=interval)
    
    # Check API availability
    api_check = check_api_latest_data(interval=interval)
    
    # Display report
    display_freshness_report(freshness_report, api_check, interval)
    
    # Return status
    if freshness_report['statistics']:
        avg_age = freshness_report['statistics']['avg_age_minutes']
        if avg_age <= 60:
            console.print("\n[green]✓ Data freshness: GOOD[/green]")
            return 0
        elif avg_age <= 240:
            console.print("\n[yellow]⚠ Data freshness: NEEDS ATTENTION[/yellow]")
            return 1
        else:
            console.print("\n[red]✗ Data freshness: POOR[/red]")
            return 2
    else:
        console.print("\n[red]✗ No data found[/red]")
        return 2


if __name__ == "__main__":
    sys.exit(main())
