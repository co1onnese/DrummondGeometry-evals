"""
Exchange calendar management with EODHD API integration.

This module handles fetching and caching exchange trading hours, holidays,
and market schedules to enable market-hours-aware scheduling.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg
from psycopg.rows import dict_row

from ..settings import Settings, get_settings


class ExchangeCalendarError(Exception):
    """Base exception for exchange calendar operations."""
    pass


class ExchangeCalendar:
    """
    Manage exchange trading calendar with EODHD API integration.

    Handles:
    - Fetching exchange details from EODHD API
    - Parsing trading hours and holidays
    - Caching data in database to minimize API calls
    - Querying trading day information
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize exchange calendar manager.

        Args:
            settings: Settings instance (uses get_settings() if None)
        """
        if settings is None:
            settings = get_settings()
        self.settings = settings

        # In-memory cache for trading calendar data
        # Key: (exchange_code, date), Value: (is_trading_day, trading_hours or None)
        self._calendar_cache: dict[tuple[str, date], tuple[bool, Optional[tuple[time, time]]]] = {}

    def fetch_exchange_details(
        self,
        exchange_code: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Fetch exchange details from EODHD API.

        Args:
            exchange_code: Exchange identifier (e.g., "US")
            from_date: Start date for calendar range (default: 6 months ago)
            to_date: End date for calendar range (default: 6 months ahead)

        Returns:
            Exchange details dictionary from EODHD API

        Raises:
            ExchangeCalendarError: If API request fails
        """
        from .client import EODHDClient, EODHDConfig
        from .errors import EODHDError

        # Default date range: 6 months back and forward
        if from_date is None:
            from_date = date.today() - timedelta(days=180)
        if to_date is None:
            to_date = date.today() + timedelta(days=180)

        try:
            config = EODHDConfig.from_settings(self.settings)
            client = EODHDClient(config)

            # Build API URL
            url = f"{config.base_url}/exchange-details/{exchange_code}"
            params = {
                "api_token": config.api_token,
                "fmt": "json",
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
            }

            # Make request
            response = client._session.get(url, params=params, timeout=config.timeout)
            response.raise_for_status()

            data = response.json()
            client.close()

            return data

        except EODHDError as e:
            raise ExchangeCalendarError(f"Failed to fetch exchange details: {e}") from e
        except Exception as e:
            raise ExchangeCalendarError(f"Unexpected error fetching exchange details: {e}") from e

    def sync_exchange_calendar(
        self,
        exchange_code: str,
        force_refresh: bool = False,
    ) -> Tuple[int, int]:
        """
        Sync exchange calendar data from EODHD API to database.

        Args:
            exchange_code: Exchange identifier (e.g., "US")
            force_refresh: If True, refresh even if recently synced

        Returns:
            Tuple of (holidays_synced, trading_days_synced)

        Raises:
            ExchangeCalendarError: If sync fails
        """
        from ..db import get_connection

        # Check if we need to sync
        if not force_refresh and self._is_recently_synced(exchange_code):
            return (0, 0)

        # Fetch data from EODHD
        from_date = date.today() - timedelta(days=180)
        to_date = date.today() + timedelta(days=180)
        exchange_data = self.fetch_exchange_details(exchange_code, from_date, to_date)

        # Parse and store
        with get_connection() as conn:
            # Update exchange metadata
            self._upsert_exchange_metadata(conn, exchange_code, exchange_data)

            # Sync holidays
            holidays_synced = self._sync_holidays(conn, exchange_code, exchange_data)

            # Generate trading days cache
            trading_days_synced = self._generate_trading_days(
                conn,
                exchange_code,
                from_date,
                to_date,
            )

            # Update sync timestamp
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE exchanges
                    SET last_synced_at = NOW(),
                        sync_range_start = %s,
                        sync_range_end = %s,
                        updated_at = NOW()
                    WHERE exchange_code = %s
                    """,
                    (from_date, to_date, exchange_code)
                )

            conn.commit()

        return (holidays_synced, trading_days_synced)

    def is_trading_day(
        self,
        exchange_code: str,
        check_date: date,
    ) -> bool:
        """
        Check if a given date is a trading day.

        Args:
            exchange_code: Exchange identifier
            check_date: Date to check

        Returns:
            True if market is open on this date

        Raises:
            ExchangeCalendarError: If exchange not found or data not synced
        """
        # Check in-memory cache first
        cache_key = (exchange_code, check_date)
        if cache_key in self._calendar_cache:
            is_trading, _ = self._calendar_cache[cache_key]
            return is_trading

        from ..db import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT is_trading_day
                    FROM trading_days
                    WHERE exchange_code = %s AND trading_date = %s
                    """,
                    (exchange_code, check_date)
                )
                result = cur.fetchone()

                if result is None:
                    # Not in cache, check if we need to sync
                    if not self._is_date_in_sync_range(exchange_code, check_date):
                        # Trigger sync
                        self.sync_exchange_calendar(exchange_code)
                        # Retry query
                        cur.execute(
                            """
                            SELECT is_trading_day
                            FROM trading_days
                            WHERE exchange_code = %s AND trading_date = %s
                            """,
                            (exchange_code, check_date)
                        )
                        result = cur.fetchone()

                if result is None:
                    # Still not found, assume non-trading day
                    is_trading = False
                else:
                    is_trading = result[0]

                # Cache the result (no trading hours available for this call)
                self._calendar_cache[cache_key] = (is_trading, None)
                return is_trading

    def get_trading_hours(
        self,
        exchange_code: str,
        check_date: date,
    ) -> Optional[Tuple[time, time]]:
        """
        Get market open and close times for a specific date.

        Args:
            exchange_code: Exchange identifier
            check_date: Date to check

        Returns:
            Tuple of (market_open, market_close) in local exchange time,
            or None if market is closed

        Raises:
            ExchangeCalendarError: If exchange not found
        """
        # Check in-memory cache first
        cache_key = (exchange_code, check_date)
        if cache_key in self._calendar_cache:
            is_trading, hours = self._calendar_cache[cache_key]
            return hours

        from ..db import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                # First check if it's a trading day
                cur.execute(
                    """
                    SELECT
                        is_trading_day,
                        actual_open,
                        actual_close
                    FROM trading_days
                    WHERE exchange_code = %s AND trading_date = %s
                    """,
                    (exchange_code, check_date)
                )
                result = cur.fetchone()

                if result is None or not result[0]:
                    # Cache the result
                    self._calendar_cache[cache_key] = (False, None)
                    return None

                actual_open, actual_close = result[1], result[2]

                # If actual times are set (half-day or special hours), use them
                if actual_open and actual_close:
                    hours = (actual_open, actual_close)
                    self._calendar_cache[cache_key] = (True, hours)
                    return hours

                # Otherwise, get default exchange hours
                cur.execute(
                    """
                    SELECT market_open, market_close
                    FROM exchanges
                    WHERE exchange_code = %s
                    """,
                    (exchange_code,)
                )
                result = cur.fetchone()

                if result is None:
                    raise ExchangeCalendarError(f"Exchange {exchange_code} not found")

                hours = (result[0], result[1])
                # Cache the result
                self._calendar_cache[cache_key] = (True, hours)
                return hours

    def _is_recently_synced(self, exchange_code: str) -> bool:
        """Check if exchange was synced within the last 24 hours."""
        from ..db import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT last_synced_at
                    FROM exchanges
                    WHERE exchange_code = %s
                    """,
                    (exchange_code,)
                )
                result = cur.fetchone()

                if result is None or result[0] is None:
                    return False

                last_sync = result[0]
                return (datetime.now(timezone.utc) - last_sync) < timedelta(hours=24)

    def _is_date_in_sync_range(self, exchange_code: str, check_date: date) -> bool:
        """Check if date is within synced calendar range."""
        from ..db import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT sync_range_start, sync_range_end
                    FROM exchanges
                    WHERE exchange_code = %s
                    """,
                    (exchange_code,)
                )
                result = cur.fetchone()

                if result is None or result[0] is None or result[1] is None:
                    return False

                start, end = result[0], result[1]
                return start <= check_date <= end

    def _upsert_exchange_metadata(
        self,
        conn: psycopg.Connection,
        exchange_code: str,
        exchange_data: Dict[str, Any],
    ) -> None:
        """
        Insert or update exchange metadata.

        Args:
            conn: Database connection
            exchange_code: Exchange identifier
            exchange_data: Parsed EODHD exchange details
        """
        # Parse exchange data
        name = exchange_data.get("Name", exchange_code)
        timezone_str = exchange_data.get("Timezone", "America/New_York")
        country = exchange_data.get("Country", "US")
        currency = exchange_data.get("Currency", "USD")

        # Parse trading hours (default to US market hours if not provided)
        # EODHD format varies, so we use defaults for now
        market_open = time(9, 30)
        market_close = time(16, 0)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO exchanges (
                    exchange_code, name, timezone,
                    market_open, market_close,
                    country_code, currency, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (exchange_code) DO UPDATE SET
                    name = EXCLUDED.name,
                    timezone = EXCLUDED.timezone,
                    market_open = EXCLUDED.market_open,
                    market_close = EXCLUDED.market_close,
                    country_code = EXCLUDED.country_code,
                    currency = EXCLUDED.currency,
                    updated_at = NOW()
                """,
                (exchange_code, name, timezone_str, market_open, market_close, country, currency)
            )

    def _sync_holidays(
        self,
        conn: psycopg.Connection,
        exchange_code: str,
        exchange_data: Dict[str, Any],
    ) -> int:
        """
        Sync holidays from EODHD data.

        Args:
            conn: Database connection
            exchange_code: Exchange identifier
            exchange_data: Parsed EODHD exchange details

        Returns:
            Number of holidays synced
        """
        holidays = exchange_data.get("ExchangeHolidays", {})
        if not holidays:
            return 0

        count = 0
        with conn.cursor() as cur:
            for holiday_date_str, holiday_name in holidays.items():
                try:
                    holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()

                    # Determine if half-day (simple heuristic: check for "Early Close" in name)
                    is_half_day = "early" in holiday_name.lower() or "half" in holiday_name.lower()
                    early_close = time(13, 0) if is_half_day else None

                    cur.execute(
                        """
                        INSERT INTO market_holidays (
                            exchange_code, holiday_date, holiday_name,
                            is_half_day, early_close_time
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (exchange_code, holiday_date) DO UPDATE SET
                            holiday_name = EXCLUDED.holiday_name,
                            is_half_day = EXCLUDED.is_half_day,
                            early_close_time = EXCLUDED.early_close_time
                        """,
                        (exchange_code, holiday_date, holiday_name, is_half_day, early_close)
                    )
                    count += 1

                except ValueError:
                    # Skip invalid dates
                    continue

        return count

    def _generate_trading_days(
        self,
        conn: psycopg.Connection,
        exchange_code: str,
        start_date: date,
        end_date: date,
    ) -> int:
        """
        Generate trading days cache for date range.

        Args:
            conn: Database connection
            exchange_code: Exchange identifier
            start_date: Start of range
            end_date: End of range

        Returns:
            Number of trading days generated
        """
        # Get exchange default hours
        with conn.cursor() as cur:
            cur.execute(
                "SELECT market_open, market_close FROM exchanges WHERE exchange_code = %s",
                (exchange_code,)
            )
            result = cur.fetchone()
            if not result:
                return 0
            default_open, default_close = result

            # Get all holidays in range
            cur.execute(
                """
                SELECT holiday_date, is_half_day, early_close_time
                FROM market_holidays
                WHERE exchange_code = %s
                  AND holiday_date BETWEEN %s AND %s
                """,
                (exchange_code, start_date, end_date)
            )
            holidays = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

        # Generate all dates in range
        count = 0
        current_date = start_date
        with conn.cursor() as cur:
            while current_date <= end_date:
                # Check if weekend
                is_weekend = current_date.weekday() >= 5  # 5=Saturday, 6=Sunday

                # Check if holiday
                is_holiday = current_date in holidays
                is_half_day, early_close = holidays.get(current_date, (False, None))

                # Determine trading status
                is_trading = not is_weekend and not (is_holiday and not is_half_day)

                # Set actual hours if different from defaults
                actual_open = None
                actual_close = early_close if is_half_day else None

                cur.execute(
                    """
                    INSERT INTO trading_days (
                        exchange_code, trading_date, is_trading_day,
                        actual_open, actual_close,
                        notes
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (exchange_code, trading_date) DO UPDATE SET
                        is_trading_day = EXCLUDED.is_trading_day,
                        actual_open = EXCLUDED.actual_open,
                        actual_close = EXCLUDED.actual_close,
                        notes = EXCLUDED.notes
                    """,
                    (
                        exchange_code,
                        current_date,
                        is_trading,
                        actual_open,
                        actual_close,
                        "Half-day" if is_half_day else None
                    )
                )
                count += 1
                current_date += timedelta(days=1)

        return count
