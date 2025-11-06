"""Test script for Discord bot integration."""

from datetime import datetime, timezone
from decimal import Decimal

from dgas.prediction.engine import GeneratedSignal, SignalType
from dgas.calculations.states import TrendDirection
from dgas.prediction.notifications import NotificationConfig, NotificationRouter
from dgas.prediction.notifications.adapters import DiscordAdapter, ConsoleAdapter


def create_sample_signals():
    """Create sample signals for testing."""
    signals = []

    # Signal 1: AAPL LONG with high confidence
    signals.append(
        GeneratedSignal(
            symbol="AAPL",
            signal_timestamp=datetime.now(timezone.utc),
            signal_type=SignalType.LONG,
            entry_price=Decimal("175.50"),
            stop_loss=Decimal("173.00"),
            target_price=Decimal("180.00"),
            confidence=0.85,
            signal_strength=0.90,
            timeframe_alignment=0.88,
            risk_reward_ratio=1.8,
            htf_trend=TrendDirection.UP,
            htf_timeframe="4h",
            trading_tf_state="TREND",
            trading_timeframe="1h",
            confluence_zones_count=3,
            pattern_context={
                "patterns": [
                    {"type": "PLDOT_PUSH", "strength": 0.9},
                    {"type": "C_WAVE", "strength": 0.8},
                ]
            },
        )
    )

    # Signal 2: MSFT SHORT with medium confidence
    signals.append(
        GeneratedSignal(
            symbol="MSFT",
            signal_timestamp=datetime.now(timezone.utc),
            signal_type=SignalType.SHORT,
            entry_price=Decimal("380.00"),
            stop_loss=Decimal("382.50"),
            target_price=Decimal("375.00"),
            confidence=0.68,
            signal_strength=0.72,
            timeframe_alignment=0.70,
            risk_reward_ratio=2.0,
            htf_trend=TrendDirection.DOWN,
            htf_timeframe="4h",
            trading_tf_state="CONGESTION_EXIT",
            trading_timeframe="1h",
            confluence_zones_count=2,
            pattern_context={
                "patterns": [
                    {"type": "EXHAUST", "strength": 0.75},
                ]
            },
        )
    )

    # Signal 3: TSLA LONG with lower confidence
    signals.append(
        GeneratedSignal(
            symbol="TSLA",
            signal_timestamp=datetime.now(timezone.utc),
            signal_type=SignalType.LONG,
            entry_price=Decimal("245.00"),
            stop_loss=Decimal("242.00"),
            target_price=Decimal("251.00"),
            confidence=0.62,
            signal_strength=0.65,
            timeframe_alignment=0.68,
            risk_reward_ratio=2.0,
            htf_trend=TrendDirection.UP,
            htf_timeframe="4h",
            trading_tf_state="TREND",
            trading_timeframe="30min",
            confluence_zones_count=1,
            pattern_context={
                "patterns": [
                    {"type": "PLDOT_REFRESH", "strength": 0.7},
                ]
            },
        )
    )

    return signals


def main():
    """Test Discord bot with sample signals."""
    print("=" * 80)
    print("Discord Bot Test")
    print("=" * 80)

    # Load configuration from environment
    print("\n1. Loading configuration from environment...")
    config = NotificationConfig.from_env()

    if not config.discord_bot_token:
        print("❌ ERROR: DGAS_DISCORD_BOT_TOKEN not found in environment")
        print("   Please add to .env file:")
        print("   DGAS_DISCORD_BOT_TOKEN=your_bot_token_here")
        return 1

    if not config.discord_channel_id:
        print("❌ ERROR: DGAS_DISCORD_CHANNEL_ID not found in environment")
        print("   Please add to .env file:")
        print("   DGAS_DISCORD_CHANNEL_ID=your_channel_id_here")
        return 1

    print(f"✓ Discord bot token: {config.discord_bot_token[:20]}...")
    print(f"✓ Discord channel ID: {config.discord_channel_id}")

    # Create sample signals
    print("\n2. Creating sample signals...")
    signals = create_sample_signals()
    print(f"✓ Created {len(signals)} sample signals")
    for signal in signals:
        print(f"   - {signal.symbol} {signal.signal_type.value} (conf: {signal.confidence:.0%})")

    # Create adapters
    print("\n3. Creating notification adapters...")
    adapters = {}

    # Console adapter (for local feedback)
    adapters["console"] = ConsoleAdapter(
        max_signals=10,
        output_format="summary",
    )
    print("✓ Console adapter created")

    # Discord adapter
    adapters["discord"] = DiscordAdapter(
        bot_token=config.discord_bot_token,
        channel_id=config.discord_channel_id,
        rate_limit_delay=1.0,  # 1 second between messages
    )
    print("✓ Discord adapter created")

    # Create router
    print("\n4. Creating notification router...")
    router = NotificationRouter(config, adapters)
    print("✓ Router created with channels:", config.enabled_channels)

    # Send notifications
    print("\n5. Sending notifications...")
    print("   This will:")
    print("   - Display signals in console (immediate)")
    print("   - Post signals to Discord (may take a few seconds)")
    print()

    run_metadata = {
        "run_id": 1,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols_processed": len(signals),
    }

    results = router.send_notifications(signals, run_metadata)

    # Report results
    print("\n6. Results:")
    for channel, success in results.items():
        status = "✓ SUCCESS" if success else "❌ FAILED"
        print(f"   {channel}: {status}")

    if all(results.values()):
        print("\n✅ All notifications sent successfully!")
        print("\n👀 Check your Discord channel for the posted signals!")
        return 0
    else:
        print("\n⚠️  Some notifications failed. Check logs for details.")
        return 1


if __name__ == "__main__":
    exit(main())
