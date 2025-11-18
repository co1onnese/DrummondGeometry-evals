#!/usr/bin/env python3
"""Verify production setup before deployment."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.config import load_config
from rich.console import Console
from rich.table import Table

console = Console()


def check_database():
    """Check database connectivity and symbol count."""
    console.print("\n[cyan]Checking database...[/cyan]")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM market_symbols WHERE is_active = true")
                symbol_count = cur.fetchone()[0]
                console.print(f"[green]✓ Database connected[/green]")
                console.print(f"[green]✓ Active symbols: {symbol_count}[/green]")
                return True, symbol_count
    except Exception as e:
        console.print(f"[red]✗ Database error: {e}[/red]")
        return False, 0


def check_config():
    """Check production configuration."""
    console.print("\n[cyan]Checking configuration...[/cyan]")
    try:
        config_path = Path(__file__).parent.parent / "config" / "production.yaml"
        config = load_config(config_path)
        
        checks = []
        
        # Data collection
        if config.data_collection.enabled:
            console.print("[green]✓ Data collection enabled[/green]")
            checks.append(True)
        else:
            console.print("[red]✗ Data collection disabled[/red]")
            checks.append(False)
        
        # Discord notifications
        if config.notifications.discord and config.notifications.discord.enabled:
            console.print("[green]✓ Discord notifications enabled[/green]")
            checks.append(True)
        else:
            console.print("[yellow]⚠ Discord notifications disabled[/yellow]")
            checks.append(False)
        
        # Scheduler
        if config.scheduler.cron_expression:
            console.print(f"[green]✓ Scheduler cron: {config.scheduler.cron_expression}[/green]")
            checks.append(True)
        else:
            console.print("[red]✗ Scheduler cron not configured[/red]")
            checks.append(False)
        
        # Prediction thresholds
        console.print(f"[green]✓ Min confidence: {config.prediction.min_confidence}[/green]")
        console.print(f"[green]✓ Min signal strength: {config.prediction.min_signal_strength}[/green]")
        
        return all(checks)
    except Exception as e:
        console.print(f"[red]✗ Configuration error: {e}[/red]")
        return False


def check_environment():
    """Check required environment variables."""
    import os
    from dgas.settings import get_settings
    
    console.print("\n[cyan]Checking environment variables...[/cyan]")
    
    # Check via Settings class (loads from .env)
    try:
        settings = get_settings()
        checks = []
        
        if settings.eodhd_api_token:
            console.print("[green]✓ EODHD_API_TOKEN: SET[/green]")
            checks.append(True)
        else:
            console.print("[red]✗ EODHD_API_TOKEN: NOT SET[/red]")
            checks.append(False)
        
        if settings.database_url:
            console.print("[green]✓ DGAS_DATABASE_URL: SET[/green]")
            checks.append(True)
        else:
            console.print("[red]✗ DGAS_DATABASE_URL: NOT SET[/red]")
            checks.append(False)
        
        # Check Discord variables directly (not in Settings class)
        discord_token = os.getenv("DGAS_DISCORD_BOT_TOKEN")
        discord_channel = os.getenv("DGAS_DISCORD_CHANNEL_ID")
        
        if discord_token:
            console.print("[green]✓ DGAS_DISCORD_BOT_TOKEN: SET[/green]")
            checks.append(True)
        else:
            console.print("[red]✗ DGAS_DISCORD_BOT_TOKEN: NOT SET[/red]")
            checks.append(False)
        
        if discord_channel:
            console.print("[green]✓ DGAS_DISCORD_CHANNEL_ID: SET[/green]")
            checks.append(True)
        else:
            console.print("[red]✗ DGAS_DISCORD_CHANNEL_ID: NOT SET[/red]")
            checks.append(False)
        
        return all(checks)
    except Exception as e:
        console.print(f"[red]✗ Error loading settings: {e}[/red]")
        return False


def main():
    """Run all verification checks."""
    console.print("\n[bold cyan]DGAS Production Setup Verification[/bold cyan]")
    console.print("=" * 60)
    
    results = []
    
    # Check database
    db_ok, symbol_count = check_database()
    results.append(("Database", db_ok))
    
    # Check configuration
    config_ok = check_config()
    results.append(("Configuration", config_ok))
    
    # Check environment
    env_ok = check_environment()
    results.append(("Environment", env_ok))
    
    # Summary
    console.print("\n[bold]Summary:[/bold]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="green")
    
    all_ok = True
    for name, status in results:
        status_text = "✓ PASS" if status else "✗ FAIL"
        status_style = "green" if status else "red"
        table.add_row(name, f"[{status_style}]{status_text}[/{status_style}]")
        if not status:
            all_ok = False
    
    console.print(table)
    
    if all_ok:
        console.print("\n[bold green]✓ All checks passed! Ready for production deployment.[/bold green]")
        return 0
    else:
        console.print("\n[bold red]✗ Some checks failed. Please fix issues before deployment.[/bold red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
