#!/usr/bin/env python3
"""
Test script to verify Discord integration from dashboard notification service.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded .env from {env_path}")
    else:
        print(f"✗ .env file not found at {env_path}")
except ImportError:
    print("⚠ python-dotenv not available, using environment variables")

from dgas.dashboard.services.notification_service import (
    NotificationService,
    NotificationType,
    NotificationPriority,
)

def test_discord_integration():
    """Test Discord integration."""
    print("\n" + "=" * 60)
    print("Testing Dashboard Discord Integration")
    print("=" * 60)
    
    # Check credentials
    bot_token = os.getenv("DGAS_DISCORD_BOT_TOKEN")
    channel_id = os.getenv("DGAS_DISCORD_CHANNEL_ID")
    
    print(f"\n1. Credentials Check:")
    print(f"   Bot Token: {'SET' if bot_token else 'NOT SET'}")
    print(f"   Channel ID: {channel_id or 'NOT SET'}")
    
    if not bot_token or not channel_id:
        print("\n❌ Discord credentials not configured!")
        print("   Set DGAS_DISCORD_BOT_TOKEN and DGAS_DISCORD_CHANNEL_ID in .env")
        return False
    
    # Create service
    print("\n2. Creating NotificationService...")
    service = NotificationService()
    
    # Test system notification
    print("\n3. Testing system notification...")
    try:
        service.create_system_notification(
            "🧪 Dashboard Discord Integration Test\nThis is a test notification from the dashboard notification service.",
            NotificationType.INFO,
            NotificationPriority.LOW,
        )
        print("   ✓ System notification created")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test signal notification
    print("\n4. Testing signal notification...")
    try:
        service.create_signal_notification({
            "symbol": "TEST",
            "signal_type": "BUY",
            "confidence": 0.95,
            "risk_reward_ratio": 2.5,
        })
        print("   ✓ Signal notification created")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    print("✅ Test completed!")
    print("=" * 60)
    print("\nCheck your Discord channel to verify messages were received.")
    print("If no messages appear, check the dashboard logs for errors.")
    
    return True

if __name__ == "__main__":
    test_discord_integration()
