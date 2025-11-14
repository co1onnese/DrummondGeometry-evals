"""Historical backfill and incremental update workflows."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Sequence

from ..db import get_connection
from .bar_aggregator import aggregate_bars
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


def backfill_intraday(
    symbol: str,
    *,
    exchange: str,
    start_date: str,
    end_date: str,
    interval: str = "30m",
    client: EODHDClient | None = None,
    use_live_for_today: bool = True,
) -> IngestionSummary:
    """
    Fetch and persist intraday data for a symbol.
    
    For dates up to yesterday: Uses historical intraday endpoint
    For today: Uses live/realtime OHLCV endpoint (if use_live_for_today=True)
    
    Args:
        symbol: Stock symbol
        exchange: Exchange code
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        interval: Data interval
        client: Optional EODHD client
        use_live_for_today: If True, use live endpoint for today's data (default: True)
    """
    from datetime import date as date_type
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    today = datetime.now(timezone.utc).date()
    
    all_bars: List[IntervalData] = []
    
    with _client_context(client) as api:
        # Fetch historical data
        # If end_date is in the future, only fetch up to today
        # If end_date is today or in the past, use the requested end_date
        # (Don't cap to yesterday - let the user request specific dates)
        if end_dt > today:
            # End date is in future - only fetch up to today
            historical_end = today
        else:
            # Use the requested end_date (could be today or in the past)
            historical_end = end_dt
        
        if start_dt <= historical_end:
            # EODHD API only supports 1m, 5m, and 1h intervals
            # If requesting 30m, fetch 5m and aggregate to 30m
            if interval == "30m":
                LOGGER.info(f"{symbol}: 30m not supported by API, fetching 5m and aggregating")
                bars_5m = api.fetch_intraday(symbol, start=start_date, end=historical_end.isoformat(), interval="5m", exchange=exchange)
                if bars_5m:
                    LOGGER.info(f"{symbol}: Fetched {len(bars_5m)} 5m bars, aggregating to 30m")
                    bars = aggregate_bars(bars_5m, "30m")
                    LOGGER.info(f"{symbol}: Aggregated to {len(bars)} 30m bars")
                else:
                    bars = []
            else:
                # For valid intervals (1m, 5m, 1h), fetch directly
                bars = api.fetch_intraday(symbol, start=start_date, end=historical_end.isoformat(), interval=interval, exchange=exchange)
            
            all_bars.extend(bars)
            LOGGER.debug(f"{symbol}: Fetched {len(bars)} historical bars from {start_date} to {historical_end}")
        
        # Fetch today's data using live endpoint if end_date includes today
        if end_dt >= today and use_live_for_today:
            try:
                # Live endpoint: use 5m if requesting 30m (API only supports 1m, 5m, 1h)
                live_interval = "5m" if interval == "30m" else interval
                live_bars = api.fetch_live_ohlcv(symbol, interval=live_interval, exchange=exchange)
                if live_bars:
                    # Filter to only today's bars
                    today_bars = [b for b in live_bars if b.timestamp.date() == today]
                    
                    # If we fetched 5m but need 30m, aggregate
                    if interval == "30m" and today_bars:
                        today_bars = aggregate_bars(today_bars, "30m")
                        LOGGER.debug(f"{symbol}: Aggregated {len(live_bars)} live 5m bars to {len(today_bars)} 30m bars")
                    
                    all_bars.extend(today_bars)
                    LOGGER.debug(f"{symbol}: Fetched {len(today_bars)} live bars for today")
            except Exception as e:
                LOGGER.warning(f"{symbol}: Failed to fetch live data: {e}, using historical only")
                # Fall back: try historical for today if live fails
                if end_dt >= today:
                    try:
                        today_bars = api.fetch_intraday(symbol, start=today.isoformat(), end=today.isoformat(), interval=interval, exchange=exchange)
                        all_bars.extend(today_bars)
                        LOGGER.debug(f"{symbol}: Fetched {len(today_bars)} historical bars for today (fallback)")
                    except Exception as e2:
                        LOGGER.warning(f"{symbol}: Failed to fetch today's data via historical endpoint: {e2}")

    quality = analyze_intervals(all_bars)

    stored = 0
    if all_bars:
        exchange_value = all_bars[0].exchange or exchange
        with get_connection() as conn:
            symbol_id = ensure_market_symbol(conn, symbol, exchange_value)
            stored = bulk_upsert_market_data(conn, symbol_id, interval, all_bars)

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
    interval: str = "30m",
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

    latest_ts: datetime | None
    with get_connection() as conn:
        symbol_id = ensure_market_symbol(conn, symbol, exchange)
        latest_ts = get_latest_timestamp(conn, symbol_id, interval)

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
                    LOGGER.debug(f"{symbol}: Fetched {len(recent_bars)} live bars (dates: {[b.timestamp.date() for b in recent_bars]})")
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
    
    # Step 3: Store all bars
    if all_bars:
        quality = analyze_intervals(all_bars)
        exchange_value = all_bars[0].exchange or exchange
        with get_connection() as conn:
            symbol_id = ensure_market_symbol(conn, symbol, exchange_value)
            total_stored = bulk_upsert_market_data(conn, symbol_id, interval, all_bars)
        
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
