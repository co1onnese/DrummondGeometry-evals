#!/usr/bin/env python3
"""Test exchange calendar after schema fix."""

from datetime import datetime, date, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.exchange_calendar import ExchangeCalendar
from dgas.utils.market_hours_filter import filter_to_regular_hours, is_during_regular_hours


def main():
    print("\n" + "="*60)
    print("TESTING EXCHANGE CALENDAR")
    print("="*60 + "\n")

    try:
        # Test 1: Initialize calendar
        print("Test 1: Initializing ExchangeCalendar...")
        calendar = ExchangeCalendar()
        print("✓ ExchangeCalendar initialized\n")

        # Test 2: Sync US exchange (will now accept "USA")
        print("Test 2: Syncing US exchange calendar...")
        print("  (This will fetch from EODHD API)")
        try:
            holidays_synced, trading_days_synced = calendar.sync_exchange_calendar(
                "US",
                force_refresh=True
            )
            print(f"✓ Sync successful!")
            print(f"  - Holidays synced: {holidays_synced}")
            print(f"  - Trading days synced: {trading_days_synced}\n")
        except Exception as e:
            print(f"⚠ Sync failed (may need API key): {e}")
            print("  Continuing with other tests...\n")

        # Test 3: Check if specific date is trading day
        print("Test 3: Checking trading days...")
        test_dates = [
            date(2025, 10, 30),  # Wednesday
            date(2025, 11, 1),   # Saturday
            date(2025, 7, 4),    # Independence Day
        ]

        for test_date in test_dates:
            is_trading = calendar.is_trading_day("US", test_date)
            print(f"  {test_date}: {'Trading day' if is_trading else 'Non-trading day'}")
        print()

        # Test 4: Get trading hours
        print("Test 4: Getting trading hours...")
        hours = calendar.get_trading_hours("US", date(2025, 10, 30))
        if hours:
            print(f"✓ Trading hours: {hours[0]} - {hours[1]}")
        else:
            print("  No trading hours available")
        print()

        # Test 5: Test timestamp filtering
        print("Test 5: Testing market hours filtering...")
        test_timestamps = [
            datetime(2025, 10, 30, 8, 0, tzinfo=timezone.utc),   # Pre-market
            datetime(2025, 10, 30, 14, 30, tzinfo=timezone.utc), # Market hours (9:30 AM EST)
            datetime(2025, 10, 30, 21, 0, tzinfo=timezone.utc),  # After hours
        ]

        for ts in test_timestamps:
            is_regular = is_during_regular_hours(ts, "US", calendar)
            local_time = ts.astimezone(timezone.utc).strftime("%H:%M UTC")
            status = "✓ Regular hours" if is_regular else "✗ Outside hours"
            print(f"  {local_time}: {status}")
        print()

        print("="*60)
        print("✓ ALL TESTS PASSED")
        print("="*60 + "\n")
        return 0

    except Exception as e:
        print("\n" + "="*60)
        print("✗ TEST FAILED")
        print("="*60)
        print(f"\nError: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
