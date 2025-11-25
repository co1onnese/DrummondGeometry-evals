"""Historical backfill and incremental update workflows."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Sequence

from ..db import get_connection
from .client import EODHDClient, EODHDConfig
from .quality import DataQualityReport, analyze_intervals
from .repository import bulk_upsert_market_data, ensure_market_symbol, get_latest_timestamp

LOGGER = logging.getLogger(__name__)


@dataclass
class IngestionSummary:
    symbol: str
    interval: str
    fetched: int
    stored: int
    quality: DataQualityReport
    start: str | None = None
    end: str | None = None


@contextmanager
def _client_context(client: EODHDClient | None) -> Iterable[EODHDClient]:
    if client is not None:
        yield client
        return

    config = EODHDConfig.from_settings()
    client = EODHDClient(config)
    try:
        yield client
    finally:
        client.close()


def _get_data_finalization_cutoff() -> datetime:
    """
    Get the cutoff time for when historical data is finalized.
    
    EODHD historical data is finalized 2-3 hours after market close (4pm ET).
    We use 7pm ET (3 hours after close) as the safe cutoff.
    
    Returns:
        Datetime representing when today's historical data becomes available
    """
    from zoneinfo import ZoneInfo
    
    et_tz = ZoneInfo("America/New_York")
    now_et = datetime.now(timezone.utc).astimezone(et_tz)
    
    # Data finalized at 7pm ET (3 hours after 4pm market close)
    return now_et.replace(hour=19, minute=0, second=0, microsecond=0)


def _select_data_source(
    target_date: datetime.date,
    current_time: datetime,
    finalization_cutoff: datetime
) -> str:
    """
    Select the appropriate data source based on data recency.
    
    Decision tree:
    1. Historical: For data >3 hours old (finalized)
    2. Live: For today's data when historical not yet available
    3. Skip: When data is too recent to be available
    
    Args:
        target_date: Date we want data for
        current_time: Current time (UTC)
        finalization_cutoff: When historical data becomes available
        
    Returns:
        "historical", "live", or "skip"
    """
    today = current_time.date()
    
    # For dates before today, always use historical
    if target_date < today:
        return "historical"
    
    # For today's data, check if historical is available
    if target_date == today:
        et_time = current_time.astimezone(finalization_cutoff.tzinfo)
        if et_time >= finalization_cutoff:
            # Past finalization window - historical available
            return "historical"
        else:
            # Within delay window - use live endpoint
            return "live"
    
    # Future date - no data available
    return "skip"


def backfill_intraday(
    symbol: str,
    *,
    exchange: str,
    start_date: str,
    end_date: str,
    interval: str = "5m",
    client: EODHDClient | None = None,
    use_live_for_today: bool = True,
) -> IngestionSummary:
    """
    Fetch and persist intraday data for a symbol.
    
    Uses a clear decision tree for endpoint selection:
    - Historical endpoint: For finalized data (>3 hours after market close)
    - Live endpoint: For today's data when historical not yet available
    - WebSocket: Handled separately by collection service
    
    Args:
        symbol: Stock symbol
        exchange: Exchange code
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        interval: Data interval (native API intervals: 1m, 5m, 1h)
        client: Optional EODHD client
        use_live_for_today: If True, use live endpoint for today's data
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    now = datetime.now(timezone.utc)
    today = now.date()
    
    # Get finalization cutoff (7pm ET)
    finalization_cutoff = _get_data_finalization_cutoff()
    
    # Determine latest date we can safely request via historical endpoint
    source = _select_data_source(today, now, finalization_cutoff)
    if source == "historical":
        latest_safe_date = today
    else:
        # Historical not available for today yet
        latest_safe_date = today - timedelta(days=1)
        LOGGER.info(f"{symbol}: Historical data not finalized for today, using {latest_safe_date} as cutoff")
    
    all_bars: List[IntervalData] = []
    
    LOGGER.info(f"{symbol}: Starting backfill from {start_date} to {end_date}, interval={interval}")
    LOGGER.debug(f"{symbol}: Latest safe date for historical endpoint: {latest_safe_date}")
    
    with _client_context(client) as api:
        # Fetch historical data
        # Cap to latest_safe_date to avoid requesting data that isn't finalized yet
        if end_dt > latest_safe_date:
            # End date is too recent - only fetch up to latest_safe_date
            historical_end = latest_safe_date
            LOGGER.info(f"{symbol}: End date {end_dt} is too recent, capping to {historical_end} for historical endpoint")
        else:
            # Use the requested end_date (could be today or in the past)
            historical_end = end_dt
        
        if start_dt <= historical_end:
            # fetch_intraday now handles 30m -> 5m conversion and aggregation automatically
            LOGGER.debug(f"{symbol}: Calling API fetch_intraday for {interval} data (will auto-convert 30m to 5m if needed)...")
            bars = api.fetch_intraday(symbol, start=start_date, end=historical_end.isoformat(), interval=interval, exchange=exchange)
            LOGGER.debug(f"{symbol}: API returned {len(bars) if bars else 0} {interval} bars")
            
            all_bars.extend(bars)
            LOGGER.debug(f"{symbol}: Fetched {len(bars)} historical bars from {start_date} to {historical_end}")
        
        # Fetch today's data using live endpoint if end_date includes today
        # Only try live endpoint if we're requesting today's data
        # Note: Live endpoint may work even if historical doesn't (due to delay)
        if end_dt >= today and use_live_for_today:
            try:
                LOGGER.info(f"{symbol}: Attempting to fetch today's data via live endpoint (data may be delayed 2-3h after market close)...")
                live_bars = api.fetch_live_ohlcv(symbol, interval=interval, exchange=exchange)
                LOGGER.debug(f"{symbol}: API returned {len(live_bars) if live_bars else 0} live bars")
                if live_bars:
                    # Filter to only today's bars
                    today_bars = [b for b in live_bars if b.timestamp.date() == today]
                    
                    all_bars.extend(today_bars)
                    LOGGER.info(f"{symbol}: Fetched {len(today_bars)} live bars for today")
                else:
                    LOGGER.warning(f"{symbol}: Live endpoint returned no data for today (may be outside trading hours or data not available yet)")
            except Exception as e:
                LOGGER.warning(f"{symbol}: Failed to fetch live data: {e}")
                # Don't fall back to historical for today if we're within delay window
                # Historical endpoint won't have today's data until 2-3 hours after market close
                if end_dt >= today and now_et >= data_available_et:
                    # Past delay window - try historical as fallback
                    try:
                        LOGGER.info(f"{symbol}: Past delay window, trying historical endpoint for today as fallback...")
                        today_bars = api.fetch_intraday(
                            symbol, 
                            start=today.isoformat(), 
                            end=today.isoformat(), 
                            interval=interval,
                            exchange=exchange
                        )
                        all_bars.extend(today_bars)
                        LOGGER.info(f"{symbol}: Fetched {len(today_bars)} historical {interval} bars for today (fallback)")
                    except Exception as e2:
                        LOGGER.warning(f"{symbol}: Failed to fetch today's data via historical endpoint: {e2}")
                else:
                    LOGGER.info(f"{symbol}: Within delay window, skipping historical fallback for today (data not finalized yet)")

    LOGGER.debug(f"{symbol}: Analyzing quality of {len(all_bars)} bars...")
    quality = analyze_intervals(all_bars)
    LOGGER.debug(f"{symbol}: Quality analysis complete")

    stored = 0
    if all_bars:
        exchange_value = all_bars[0].exchange or exchange
        LOGGER.debug(f"{symbol}: Storing {len(all_bars)} bars to database...")
        with get_connection() as conn:
            symbol_id = ensure_market_symbol(conn, symbol, exchange_value)
            stored = bulk_upsert_market_data(conn, symbol_id, interval, all_bars)
        LOGGER.debug(f"{symbol}: Stored {stored} bars to database")

    LOGGER.info(
        "Backfill complete: %s (%s) fetched=%s stored=%s duplicates=%s gaps=%s",
        symbol,
        interval,
        len(all_bars),
        stored,
        quality.duplicate_count,
        quality.gap_count,
    )

    return IngestionSummary(
        symbol=symbol,
        interval=interval,
        fetched=len(all_bars),
        stored=stored,
        quality=quality,
        start=start_date,
        end=end_date,
    )


def backfill_eod(
    symbol: str,
    *,
    exchange: str,
    start_date: str,
    end_date: str,
    client: EODHDClient | None = None,
) -> IngestionSummary:
    """Fetch and persist historical end-of-day (daily) data for a symbol."""

    with _client_context(client) as api:
        bars = api.fetch_eod(symbol, start=start_date, end=end_date, exchange=exchange)

    quality = analyze_intervals(bars)

    stored = 0
    if bars:
        exchange_value = bars[0].exchange or exchange
        with get_connection() as conn:
            symbol_id = ensure_market_symbol(conn, symbol, exchange_value)
            stored = bulk_upsert_market_data(conn, symbol_id, "1d", bars)

    LOGGER.info(
        "Backfill complete: %s (1d) fetched=%s stored=%s duplicates=%s gaps=%s",
        symbol,
        len(bars),
        stored,
        quality.duplicate_count,
        quality.gap_count,
    )

    return IngestionSummary(
        symbol=symbol,
        interval="1d",
        fetched=len(bars),
        stored=stored,
        quality=quality,
        start=start_date,
        end=end_date,
    )


def incremental_update_intraday(
    symbol: str,
    *,
    exchange: str,
    interval: str = "5m",
    buffer_days: int = 2,
    default_start: str | None = None,
    client: EODHDClient | None = None,
    use_live_data: bool = True,
) -> IngestionSummary:
    """
    Update a symbol using the most recent data.
    
    For today's data: Uses live/realtime OHLCV endpoint (faster, more up-to-date)
    For past dates: Uses historical intraday endpoint
    
    Args:
        symbol: Stock symbol
        exchange: Exchange code
        interval: Data interval
        buffer_days: Days of buffer to fetch for historical data
        default_start: Default start date if no existing data
        client: Optional EODHD client
        use_live_data: If True, use live endpoint for today's data (default: True)
    """
    LOGGER.debug(f"{symbol}: Starting incremental update, interval={interval}")

    latest_ts: datetime | None
    with get_connection() as conn:
        symbol_id = ensure_market_symbol(conn, symbol, exchange)
        latest_ts = get_latest_timestamp(conn, symbol_id, interval)
    LOGGER.debug(f"{symbol}: Latest timestamp from DB: {latest_ts}")

    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)
    
    # Determine what data we need
    # Use live data for recent dates (today or yesterday) - live endpoint has most recent available
    # Use historical for older dates
    # Fix: Always fetch recent data if latest is before today (even if it's from yesterday)
    # Also fetch if latest is from today but more than 1 hour old (stale intraday data)
    if latest_ts is None:
        need_recent_data = True
        need_historical_data = True
    else:
        latest_date = latest_ts.date()
        hours_since_latest = (now - latest_ts).total_seconds() / 3600.0
        
        # Need recent data if:
        # 1. Latest data is from yesterday or earlier
        # 2. Latest data is from today but more than 1 hour old (stale)
        need_recent_data = latest_date < today or (latest_date == today and hours_since_latest > 1.0)
        
        # Need historical data if latest is more than buffer_days old
        need_historical_data = latest_date < (today - timedelta(days=buffer_days))
    
    all_bars: List[IntervalData] = []
    total_fetched = 0
    total_stored = 0
    
    with _client_context(client) as api:
        # Step 1: Fetch recent data (today/yesterday) using live endpoint if needed and enabled
        # Live endpoint returns the most recent available data (could be today or yesterday)
        if need_recent_data and use_live_data:
            try:
                LOGGER.debug(f"{symbol}: Fetching live/realtime data")
                live_bars = api.fetch_live_ohlcv(symbol, interval=interval, exchange=exchange)
                if live_bars:
                    # Filter to recent bars (today or yesterday) - live endpoint has latest available
                    recent_bars = [b for b in live_bars if b.timestamp.date() >= yesterday]
                    
                    all_bars.extend(recent_bars)
                    total_fetched += len(recent_bars)
                    LOGGER.debug(f"{symbol}: Fetched {len(recent_bars)} live {interval} bars (dates: {[b.timestamp.date() for b in recent_bars]})")
            except Exception as e:
                LOGGER.warning(f"{symbol}: Failed to fetch live data: {e}, falling back to historical")
                # Fall back to historical for recent dates if live fails
        
        # Step 2: Fetch historical data (2+ days ago) if needed
        if need_historical_data:
            if latest_ts is None:
                if not default_start:
                    raise ValueError(
                        "No existing data for symbol; provide default_start for initial incremental update"
                    )
                start_date = default_start
            else:
                start_dt = (latest_ts - timedelta(days=buffer_days)).date()
                start_date = start_dt.isoformat()
            
            # End date: 2 days ago (live endpoint handles recent dates)
            end_date = (today - timedelta(days=2)).isoformat()
            
            # Only fetch historical if start_date <= end_date
            if start_date <= end_date:
                try:
                    LOGGER.debug(f"{symbol}: Fetching historical data from {start_date} to {end_date}")
                    historical_bars = api.fetch_intraday(
                        symbol,
                        start=start_date,
                        end=end_date,
                        interval=interval,
                        exchange=exchange,
                    )
                    all_bars.extend(historical_bars)
                    total_fetched += len(historical_bars)
                    LOGGER.debug(f"{symbol}: Fetched {len(historical_bars)} historical bars")
                except Exception as e:
                    LOGGER.warning(f"{symbol}: Failed to fetch historical data: {e}")
                    # Continue - we may still have today's data from live endpoint
    
    # Step 3: Filter out bars that are older than what we already have
    if all_bars and latest_ts:
        # Only keep bars that are newer than the latest timestamp in DB
        filtered_bars = [b for b in all_bars if b.timestamp > latest_ts]
        if len(filtered_bars) < len(all_bars):
            skipped = len(all_bars) - len(filtered_bars)
            LOGGER.info(f"{symbol}: Filtered out {skipped} bars that are older than latest DB timestamp ({latest_ts})")
            all_bars = filtered_bars
    
    # Step 4: Store all bars
    if all_bars:
        LOGGER.debug(f"{symbol}: Analyzing quality of {len(all_bars)} bars...")
        quality = analyze_intervals(all_bars)
        exchange_value = all_bars[0].exchange or exchange
        LOGGER.debug(f"{symbol}: Storing {len(all_bars)} bars to database...")
        with get_connection() as conn:
            symbol_id = ensure_market_symbol(conn, symbol, exchange_value)
            total_stored = bulk_upsert_market_data(conn, symbol_id, interval, all_bars)
        LOGGER.debug(f"{symbol}: Stored {total_stored} bars to database")
        
        LOGGER.info(
            f"Incremental update: {symbol} ({interval}) fetched={total_fetched} stored={total_stored} "
            f"(live={need_recent_data and use_live_data}, historical={need_historical_data})"
        )
    else:
        # No new data
        from .quality import DataQualityReport
        quality = DataQualityReport(
            symbol=symbol,
            interval=interval,
            total_bars=0,
            duplicate_count=0,
            gap_count=0,
            is_chronological=True,
            notes=["no new data available"],
        )
    
    return IngestionSummary(
        symbol=symbol,
        interval=interval,
        fetched=total_fetched,
        stored=total_stored,
        quality=quality,
        start=None,  # Mixed sources
        end=None,
    )


def backfill_many(
    symbols: Sequence[tuple[str, str]],
    *,
    start_date: str,
    end_date: str,
    interval: str = "30m",
    client: EODHDClient | None = None,
) -> List[IngestionSummary]:
    """Backfill multiple symbols sequentially."""

    summaries: List[IngestionSummary] = []
    with _client_context(client) as api:
        for symbol, exchange in symbols:
            try:
                summary = backfill_intraday(
                    symbol,
                    exchange=exchange,
                    start_date=start_date,
                    end_date=end_date,
                    interval=interval,
                    client=api,
                )
            except Exception as exc:  # pragma: no cover - logged and re-raised
                LOGGER.exception("Backfill failed for %s: %s", symbol, exc)
                raise
            summaries.append(summary)
    return summaries


__all__ = ["IngestionSummary", "backfill_intraday", "backfill_eod", "incremental_update_intraday", "backfill_many"]
