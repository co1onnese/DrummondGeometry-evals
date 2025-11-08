"""Market hours filtering utilities leveraging ExchangeCalendar.

Filters market data to regular trading hours using the existing
exchange calendar system with database-backed holiday and hours tracking.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Sequence
from zoneinfo import ZoneInfo

from ..data.models import IntervalData
from ..data.exchange_calendar import ExchangeCalendar


def filter_to_regular_hours(
    bars: Sequence[IntervalData],
    exchange_code: str = "US",
    calendar: ExchangeCalendar | None = None,
) -> list[IntervalData]:
    """Filter bars to regular market hours only.

    Uses ExchangeCalendar to respect:
    - Regular trading hours (typically 9:30 AM - 4:00 PM EST)
    - Holidays (market closed)
    - Half-day early close times
    - Weekends

    Args:
        bars: Sequence of OHLCV bars
        exchange_code: Exchange identifier (default: "US")
        calendar: Optional ExchangeCalendar instance (creates new if None)

    Returns:
        List of bars during regular trading hours

    Example:
        >>> bars = load_market_data("AAPL", "30m")
        >>> regular_hours = filter_to_regular_hours(bars)
    """
    if not bars:
        return []

    if calendar is None:
        calendar = ExchangeCalendar()

    filtered_bars = []

    # US market hours: 9:30 AM - 4:00 PM Eastern Time
    # Bar timestamps are stored in Europe/Berlin (Europe/Prague) timezone
    # We need to convert to US/Eastern timezone to check trading hours

    us_tz = ZoneInfo("America/New_York")
    
    # Determine source timezone - bars are stored in Europe/Berlin/Prague
    # If bar has timezone info, use it; otherwise assume Europe/Berlin
    source_tz = None
    if bars and bars[0].timestamp.tzinfo:
        source_tz = bars[0].timestamp.tzinfo
    else:
        source_tz = ZoneInfo("Europe/Berlin")

    for bar in bars:
        # Convert bar timestamp to US/Eastern timezone first
        if bar.timestamp.tzinfo is None:
            # If naive, assume it's in source timezone
            bar_with_tz = bar.timestamp.replace(tzinfo=source_tz)
        else:
            bar_with_tz = bar.timestamp
        
        # Convert to US/Eastern timezone
        us_time = bar_with_tz.astimezone(us_tz)
        
        # Use US date for checking trading days (important for timezone boundaries)
        us_date = us_time.date()
        us_time_of_day = us_time.time()

        # Check if trading day (using US date)
        if not calendar.is_trading_day(exchange_code, us_date):
            continue

        # Get trading hours for this specific US date
        hours = calendar.get_trading_hours(exchange_code, us_date)
        if hours is None:
            continue

        market_open, market_close = hours

        # Check if bar is within US trading hours
        if market_open <= us_time_of_day < market_close:
            filtered_bars.append(bar)

    return filtered_bars


def is_during_regular_hours(
    timestamp: datetime,
    exchange_code: str = "US",
    calendar: ExchangeCalendar | None = None,
) -> bool:
    """Check if a timestamp is during regular market hours.

    Args:
        timestamp: UTC timestamp to check
        exchange_code: Exchange identifier (default: "US")
        calendar: Optional ExchangeCalendar instance

    Returns:
        True if timestamp is during regular trading hours
    """
    if calendar is None:
        calendar = ExchangeCalendar()

    check_date = timestamp.date()

    # Check if trading day
    if not calendar.is_trading_day(exchange_code, check_date):
        return False

    # Get trading hours
    hours = calendar.get_trading_hours(exchange_code, check_date)
    if hours is None:
        return False

    market_open, market_close = hours

    # Convert to exchange timezone
    exchange_tz = ZoneInfo("America/New_York")
    local_time = timestamp.astimezone(exchange_tz)
    time_of_day = local_time.time()

    return market_open <= time_of_day < market_close


def get_regular_hours_stats(
    bars: Sequence[IntervalData],
    exchange_code: str = "US",
    calendar: ExchangeCalendar | None = None,
) -> dict[str, int]:
    """Get statistics about regular vs non-regular hours bars.

    Args:
        bars: Sequence of OHLCV bars
        exchange_code: Exchange identifier
        calendar: Optional ExchangeCalendar instance

    Returns:
        Dictionary with counts:
            - total: Total bars
            - regular_hours: Bars during regular hours
            - pre_market: Bars before market open
            - after_hours: Bars after market close
            - non_trading_days: Bars on holidays/weekends
    """
    if not bars:
        return {
            "total": 0,
            "regular_hours": 0,
            "pre_market": 0,
            "after_hours": 0,
            "non_trading_days": 0,
        }

    if calendar is None:
        calendar = ExchangeCalendar()

    exchange_tz = ZoneInfo("America/New_York")

    total = len(bars)
    regular_hours = 0
    pre_market = 0
    after_hours = 0
    non_trading_days = 0

    for bar in bars:
        bar_date = bar.timestamp.date()

        # Check if trading day
        if not calendar.is_trading_day(exchange_code, bar_date):
            non_trading_days += 1
            continue

        # Get trading hours
        hours = calendar.get_trading_hours(exchange_code, bar_date)
        if hours is None:
            non_trading_days += 1
            continue

        market_open, market_close = hours
        local_time = bar.timestamp.astimezone(exchange_tz)
        bar_time = local_time.time()

        if market_open <= bar_time < market_close:
            regular_hours += 1
        elif bar_time < market_open:
            pre_market += 1
        else:
            after_hours += 1

    return {
        "total": total,
        "regular_hours": regular_hours,
        "pre_market": pre_market,
        "after_hours": after_hours,
        "non_trading_days": non_trading_days,
    }


__all__ = [
    "filter_to_regular_hours",
    "is_during_regular_hours",
    "get_regular_hours_stats",
]
