#!/usr/bin/env python3
"""Sync exchange calendar for historical period."""

from dgas.data.exchange_calendar import ExchangeCalendar

# Sync US exchange calendar
# Note: sync_exchange_calendar syncs 6 months back and 6 months forward from today
calendar = ExchangeCalendar()
print("Syncing US exchange calendar (6 months back and 6 months forward from today)...")

try:
    result = calendar.sync_exchange_calendar(
        exchange_code="US",
        force_refresh=True,  # Force refresh to ensure we get latest data
    )

    holidays_synced, trading_days_synced = result
    print(f"✓ Sync complete!")
    print(f"  Holidays synced: {holidays_synced}")
    print(f"  Trading days synced: {trading_days_synced}")

except Exception as e:
    print(f"✗ Sync failed: {e}")
    import traceback
    traceback.print_exc()
