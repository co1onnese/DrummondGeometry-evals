#!/usr/bin/env python3
"""Sync exchange calendar for historical period."""

from dgas.data.exchange_calendar import ExchangeCalendar
from datetime import date

# Sync US exchange calendar for historical data period
calendar = ExchangeCalendar()
print("Syncing US exchange calendar for historical period (2024-01-01 to 2025-12-31)...")

try:
    result = calendar.sync_exchange_calendar(
        exchange_code="US",
        from_date=date(2024, 1, 1),
        to_date=date(2025, 12, 31),
    )

    holidays_synced, trading_days_synced = result
    print(f"✓ Sync complete!")
    print(f"  Holidays synced: {holidays_synced}")
    print(f"  Trading days synced: {trading_days_synced}")

except Exception as e:
    print(f"✗ Sync failed: {e}")
    import traceback
    traceback.print_exc()
