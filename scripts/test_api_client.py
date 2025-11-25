#!/usr/bin/env python3
"""
Test EODHD API client to verify credentials and connectivity.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dgas.data.client import EODHDClient, EODHDConfig

def test_api_client():
    """Test the EODHD API client with a simple request."""
    
    print("=" * 60)
    print("TESTING EODHD API CLIENT")
    print("=" * 60)
    
    try:
        # Load configuration from settings (which reads from .env)
        print("\n1. Loading configuration from .env...")
        config = EODHDConfig.from_settings()
        print(f"   ✓ API Token loaded: {config.api_token[:10]}...")
        print(f"   ✓ Base URL: {config.base_url}")
        
        # Create client
        print("\n2. Creating API client...")
        client = EODHDClient(config)
        print("   ✓ Client created successfully")
        
        # Test with a simple request for AAPL
        print("\n3. Testing API with AAPL 5m data request...")
        symbol = "AAPL"
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=5)  # Last 5 days
        
        print(f"   Requesting: {symbol} from {start_date} to {end_date}")
        
        # Test historical intraday endpoint
        bars = client.fetch_intraday(
            symbol=symbol,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            interval="5m",
            exchange="US"
        )
        
        if bars:
            print(f"   ✓ Success! Received {len(bars)} bars")
            print(f"   First bar: {bars[0].timestamp} - O:{bars[0].open} H:{bars[0].high} L:{bars[0].low} C:{bars[0].close}")
            print(f"   Last bar:  {bars[-1].timestamp} - O:{bars[-1].open} H:{bars[-1].high} L:{bars[-1].low} C:{bars[-1].close}")
        else:
            print("   ⚠ No data returned (market might be closed)")
        
        # Test live endpoint
        print("\n4. Testing live/realtime endpoint...")
        try:
            live_bars = client.fetch_live_ohlcv(symbol, interval="5m", exchange="US")
            if live_bars:
                print(f"   ✓ Live endpoint works! Received {len(live_bars)} bars")
            else:
                print("   ⚠ No live data (market might be closed)")
        except Exception as e:
            print(f"   ⚠ Live endpoint error: {e}")
        
        # Check API usage
        print("\n5. API Usage Information:")
        print(f"   Total requests made: {client.request_count}")
        
        print("\n✅ API CLIENT TEST SUCCESSFUL!")
        print("The EODHD API client is working correctly with your credentials.")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"\n❌ API CLIENT TEST FAILED!")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_api_client()
    sys.exit(0 if success else 1)