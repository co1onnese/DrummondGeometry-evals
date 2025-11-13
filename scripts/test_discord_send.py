#!/usr/bin/env python3
"""
Test sending a real Discord alert to verify the system works.

This script creates a test signal and sends it to Discord to verify:
1. Discord connection works
2. Message formatting is correct
3. Alerts are received in Discord channel
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.prediction.notifications import NotificationConfig
from dgas.prediction.notifications.adapters.discord import DiscordAdapter
from dgas.prediction.engine import GeneratedSignal, SignalType
from dgas.calculations.states import TrendDirection
from rich.console import Console

console = Console()


def test_discord_alert():
    """Send a test alert to Discord."""
    console.print("[bold cyan]Testing Discord Alert System[/bold cyan]")
    console.print("=" * 70)
    
    # Load configuration
    config = NotificationConfig.from_env()
    
    if not config.discord_bot_token or not config.discord_channel_id:
        console.print("[red]✗[/red] Discord not configured")
        console.print("Please set DGAS_DISCORD_BOT_TOKEN and DGAS_DISCORD_CHANNEL_ID")
        return False
    
    console.print(f"[green]✓[/green] Discord configured")
    console.print(f"  Channel ID: {config.discord_channel_id}")
    console.print(f"  Min confidence: {config.discord_min_confidence}")
    console.print(f"  Enabled channels: {config.enabled_channels}")
    console.print()
    
    # Create test signal
    now = datetime.now(timezone.utc)
    test_signal = GeneratedSignal(
        symbol="TEST",
        signal_timestamp=now,
        signal_type=SignalType.LONG,
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("95.00"),
        target_price=Decimal("110.00"),
        confidence=0.75,  # Above threshold
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
    
    # Create adapter
    try:
        adapter = DiscordAdapter(
            bot_token=config.discord_bot_token,
            channel_id=config.discord_channel_id,
        )
        console.print("[green]✓[/green] Discord adapter created")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to create adapter: {e}")
        return False
    
    # Send test signal
    console.print()
    console.print("[cyan]Sending test signal to Discord...[/cyan]")
    console.print("[yellow]Check your Discord channel for the message![/yellow]")
    console.print()
    
    try:
        success = adapter.send([test_signal], {"test": True, "run_id": 0})
        
        if success:
            console.print("[green]✓[/green] Test signal sent successfully!")
            console.print()
            console.print("[bold]Next Steps:[/bold]")
            console.print("1. Check your Discord channel (ID: {})".format(config.discord_channel_id))
            console.print("2. Verify the message appears with correct formatting")
            console.print("3. Start the scheduler to begin receiving real alerts")
            return True
        else:
            console.print("[red]✗[/red] Failed to send test signal")
            return False
            
    except Exception as e:
        console.print(f"[red]✗[/red] Error sending to Discord: {e}")
        console.print()
        console.print("[yellow]Troubleshooting:[/yellow]")
        console.print("1. Verify bot token is valid")
        console.print("2. Verify bot has permission to send messages in the channel")
        console.print("3. Check Discord API status")
        return False


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--send":
        # Actually send the test
        test_discord_alert()
    else:
        console.print("[yellow]This script will send a test message to Discord.[/yellow]")
        console.print("[yellow]Run with --send flag to actually send:[/yellow]")
        console.print("  python scripts/test_discord_send.py --send")
