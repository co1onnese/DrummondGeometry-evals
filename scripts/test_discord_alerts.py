#!/usr/bin/env python3
"""
Test Discord alert functionality and verify scheduler is sending alerts properly.

This script:
1. Checks if Discord is configured
2. Tests Discord connection
3. Verifies signal ordering
4. Checks recent signals and their notification status
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.prediction.notifications import NotificationConfig
from dgas.prediction.notifications.adapters.discord import DiscordAdapter
from dgas.prediction.engine import GeneratedSignal, SignalType
from dgas.calculations.states import TrendDirection
from decimal import Decimal
from rich.console import Console
from rich.table import Table

console = Console()


def check_discord_config():
    """Check if Discord is configured."""
    console.print("\n[bold cyan]1. Discord Configuration Check[/bold cyan]")
    
    import os
    # Load from environment directly
    bot_token = os.getenv("DGAS_DISCORD_BOT_TOKEN")
    channel_id = os.getenv("DGAS_DISCORD_CHANNEL_ID")
    
    if not bot_token:
        console.print("[red]✗[/red] DGAS_DISCORD_BOT_TOKEN not set")
        return False
    else:
        console.print(f"[green]✓[/green] Discord bot token configured (length: {len(bot_token)})")
    
    if not channel_id:
        console.print("[red]✗[/red] DGAS_DISCORD_CHANNEL_ID not set")
        return False
    else:
        console.print(f"[green]✓[/green] Discord channel ID: {channel_id}")
    
    config = NotificationConfig.from_env()
    console.print(f"Min confidence threshold: {config.discord_min_confidence}")
    console.print(f"Enabled channels: {config.enabled_channels}")
    
    return True


def test_discord_connection():
    """Test Discord API connection."""
    console.print("\n[bold cyan]2. Discord Connection Test[/bold cyan]")
    
    config = NotificationConfig.from_env()
    
    if not config.discord_bot_token or not config.discord_channel_id:
        console.print("[yellow]⚠[/yellow] Discord not configured, skipping connection test")
        return False
    
    try:
        adapter = DiscordAdapter(
            bot_token=config.discord_bot_token,
            channel_id=config.discord_channel_id,
        )
        
        # Create a test signal
        test_signal = GeneratedSignal(
            symbol="TEST",
            signal_timestamp=datetime.now(timezone.utc),
            signal_type=SignalType.LONG,
            entry_price=Decimal("100.00"),
            stop_loss=Decimal("95.00"),
            target_price=Decimal("110.00"),
            confidence=0.75,
            signal_strength=0.80,
            timeframe_alignment=0.85,
            risk_reward_ratio=2.0,
            htf_trend=TrendDirection.UP,
            trading_tf_state="TREND",
            confluence_zones_count=2,
            pattern_context={"patterns": [{"type": "PLDOT_PUSH"}]},
            htf_timeframe="30m",
            trading_timeframe="30m",
        )
        
        # Try to send test signal
        console.print("[cyan]Sending test signal to Discord...[/cyan]")
        success = adapter.send([test_signal], {"test": True})
        
        if success:
            console.print("[green]✓[/green] Test signal sent successfully!")
            console.print("[yellow]⚠[/yellow] Check your Discord channel for the test message")
            return True
        else:
            console.print("[red]✗[/red] Failed to send test signal")
            return False
            
    except Exception as e:
        console.print(f"[red]✗[/red] Discord connection test failed: {e}")
        return False


def check_recent_signals():
    """Check recent signals and their notification status."""
    console.print("\n[bold cyan]3. Recent Signals & Notification Status[/bold cyan]")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get recent signals with notification status
            cur.execute("""
                SELECT 
                    gs.signal_timestamp,
                    ms.symbol,
                    gs.signal_type,
                    gs.confidence,
                    gs.signal_strength,
                    gs.notification_sent,
                    gs.notification_channels,
                    gs.notification_timestamp
                FROM generated_signals gs
                JOIN market_symbols ms ON ms.symbol_id = gs.symbol_id
                ORDER BY gs.signal_timestamp DESC
                LIMIT 20
            """)
            rows = cur.fetchall()
            
            if not rows:
                console.print("[yellow]⚠[/yellow] No signals found in database")
                return
            
            table = Table(title="Recent Signals & Notifications")
            table.add_column("Timestamp", style="cyan")
            table.add_column("Symbol", style="yellow")
            table.add_column("Type", style="magenta")
            table.add_column("Confidence", justify="right")
            table.add_column("Strength", justify="right")
            table.add_column("Notified", justify="center")
            table.add_column("Channels", style="green")
            table.add_column("Notify Time", style="dim")
            
            for row in rows:
                ts, symbol, sig_type, conf, strength, notified, channels, notify_ts = row
                notified_str = "[green]✓[/green]" if notified else "[red]✗[/red]"
                channels_str = ", ".join(channels) if channels else "None"
                notify_time_str = notify_ts.strftime("%H:%M:%S") if notify_ts else "N/A"
                
                table.add_row(
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    symbol,
                    sig_type,
                    f"{conf:.2f}",
                    f"{strength:.2f}",
                    notified_str,
                    channels_str,
                    notify_time_str,
                )
            
            console.print(table)
            
            # Statistics
            notified_count = sum(1 for row in rows if row[5])  # notification_sent
            total_count = len(rows)
            console.print(f"\n[cyan]Statistics:[/cyan] {notified_count}/{total_count} signals were notified ({notified_count/total_count*100:.1f}%)")


def check_signal_ordering():
    """Check if signals are being sent in proper order (by timestamp)."""
    console.print("\n[bold cyan]4. Signal Ordering Verification[/bold cyan]")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get signals that were notified, ordered by notification timestamp
            cur.execute("""
                SELECT 
                    gs.signal_timestamp,
                    gs.notification_timestamp,
                    ms.symbol,
                    gs.signal_type,
                    gs.confidence
                FROM generated_signals gs
                JOIN market_symbols ms ON ms.symbol_id = gs.symbol_id
                WHERE gs.notification_sent = true
                  AND gs.notification_timestamp IS NOT NULL
                ORDER BY gs.notification_timestamp DESC
                LIMIT 10
            """)
            rows = cur.fetchall()
            
            if not rows:
                console.print("[yellow]⚠[/yellow] No notified signals found")
                return
            
            # Check if notification order matches signal timestamp order
            signal_timestamps = [row[0] for row in rows]
            notification_timestamps = [row[1] for row in rows]
            
            # Signals should be notified in order of their signal_timestamp
            # (newer signals notified after older ones)
            is_ordered = all(
                signal_timestamps[i] >= signal_timestamps[i+1]
                for i in range(len(signal_timestamps) - 1)
            )
            
            if is_ordered:
                console.print("[green]✓[/green] Signals are being notified in proper order (newest first)")
            else:
                console.print("[yellow]⚠[/yellow] Signal ordering may be incorrect")
            
            table = Table(title="Notification Order")
            table.add_column("Signal Time", style="cyan")
            table.add_column("Notify Time", style="green")
            table.add_column("Symbol", style="yellow")
            table.add_column("Type", style="magenta")
            table.add_column("Confidence", justify="right")
            
            for row in rows:
                sig_ts, notify_ts, symbol, sig_type, conf = row
                table.add_row(
                    sig_ts.strftime("%H:%M:%S"),
                    notify_ts.strftime("%H:%M:%S"),
                    symbol,
                    sig_type,
                    f"{conf:.2f}",
                )
            
            console.print(table)


def check_scheduler_notification_logs():
    """Check scheduler logs for notification activity."""
    console.print("\n[bold cyan]5. Scheduler Notification Activity[/bold cyan]")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get recent prediction runs with notification timing
            cur.execute("""
                SELECT 
                    run_timestamp,
                    symbols_processed,
                    signals_generated,
                    notification_ms,
                    status
                FROM prediction_runs
                WHERE run_timestamp > NOW() - INTERVAL '24 hours'
                ORDER BY run_timestamp DESC
                LIMIT 10
            """)
            rows = cur.fetchall()
            
            if not rows:
                console.print("[yellow]⚠[/yellow] No prediction runs in last 24 hours")
                return
            
            table = Table(title="Recent Prediction Runs (24h)")
            table.add_column("Timestamp", style="cyan")
            table.add_column("Symbols", justify="right")
            table.add_column("Signals", justify="right")
            table.add_column("Notify Time (ms)", justify="right")
            table.add_column("Status", style="green")
            
            for row in rows:
                ts, symbols, signals, notify_ms, status = row
                notify_str = f"{notify_ms}ms" if notify_ms else "N/A"
                table.add_row(
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    str(symbols),
                    str(signals),
                    notify_str,
                    status,
                )
            
            console.print(table)
            
            # Check if notifications are being sent
            runs_with_notifications = sum(1 for row in rows if row[3] and row[3] > 0)
            total_runs = len(rows)
            console.print(f"\n[cyan]Runs with notifications:[/cyan] {runs_with_notifications}/{total_runs}")


def main():
    """Run all checks."""
    console.print("[bold]Discord Alert Verification Report[/bold]")
    console.print("=" * 70)
    
    # Check configuration
    if not check_discord_config():
        console.print("\n[red]Discord is not properly configured. Please set environment variables:[/red]")
        console.print("  - DGAS_DISCORD_BOT_TOKEN")
        console.print("  - DGAS_DISCORD_CHANNEL_ID")
        return
    
    # Test connection (optional - uncomment to test)
    # test_discord_connection()
    
    # Check recent signals
    check_recent_signals()
    
    # Check ordering
    check_signal_ordering()
    
    # Check scheduler activity
    check_scheduler_notification_logs()
    
    console.print("\n[bold]Verification Complete[/bold]")
    console.print("\n[yellow]Note:[/yellow] To test Discord connection, uncomment test_discord_connection() in main()")


if __name__ == "__main__":
    main()
