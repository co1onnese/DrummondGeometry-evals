"""Database repository helpers for market data ingestion."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Sequence

import psycopg
from psycopg import Connection

from .models import IntervalData

LOGGER = logging.getLogger(__name__)


def _normalize_ohlc(bar: IntervalData) -> IntervalData:
    """
    Normalize OHLC values to satisfy database constraints.
    
    During market hours, live data may contain incomplete bars where:
    - close > high (price moved up but high hasn't updated yet)
    - close < low (price moved down but low hasn't updated yet)
    
    This function adjusts high/low to accommodate the close price,
    ensuring the bar satisfies the chk_ohlc_relationships constraint.
    
    Args:
        bar: IntervalData bar that may have invalid OHLC relationships
        
    Returns:
        Normalized IntervalData with valid OHLC relationships
    """
    open_price = bar.open
    high_price = bar.high
    low_price = bar.low
    close_price = bar.close
    
    original_high = high_price
    original_low = low_price
    normalized = False
    
    # Adjust high to be at least as high as open and close
    if high_price < open_price or high_price < close_price:
        high_price = max(high_price, open_price, close_price)
        normalized = True
    
    # Adjust low to be at least as low as open and close
    if low_price > open_price or low_price > close_price:
        low_price = min(low_price, open_price, close_price)
        normalized = True
    
    # Ensure high - low >= |open - close| (range constraint)
    # This constraint ensures the bar's range is at least as wide as the open-close movement
    price_range = abs(open_price - close_price)
    current_range = high_price - low_price
    if current_range < price_range:
        # Expand the range symmetrically around the midpoint of open and close
        # This ensures we maintain high >= max(open, close) and low <= min(open, close)
        midpoint = (open_price + close_price) / 2
        half_range = price_range / 2
        high_price = max(high_price, midpoint + half_range)
        low_price = min(low_price, midpoint - half_range)
        normalized = True
    
    # Log normalization if it occurred (debug level to avoid spam)
    if normalized:
        LOGGER.debug(
            f"{bar.symbol} {bar.timestamp}: Normalized OHLC - "
            f"high: {original_high} -> {high_price}, "
            f"low: {original_low} -> {low_price}"
        )
    
    # Create new IntervalData with normalized values
    # Since IntervalData is frozen, we need to create a new instance
    return IntervalData(
        symbol=bar.symbol,
        exchange=bar.exchange,
        timestamp=bar.timestamp,
        interval=bar.interval,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        adjusted_close=bar.adjusted_close,
        volume=bar.volume,
    )


def ensure_market_symbol(
    conn: Connection,
    symbol: str,
    exchange: str,
    *,
    company_name: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    market_cap: float | None = None,
    is_active: bool = True,
) -> int:
    """Insert or update a market symbol and return its identifier.
    
    Normalizes symbols by removing .US suffix and always uses "US" as exchange code.
    """

    # Normalize symbol: remove .US suffix and convert to uppercase
    if symbol.endswith(".US"):
        symbol = symbol[:-3]
    symbol = symbol.upper()
    
    # Always use "US" as exchange code for EODHD unified exchange
    exchange = "US"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO market_symbols (
                symbol, exchange, company_name, sector, industry,
                market_cap, is_active, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (symbol) DO UPDATE SET
                exchange = EXCLUDED.exchange,
                company_name = COALESCE(EXCLUDED.company_name, market_symbols.company_name),
                sector = COALESCE(EXCLUDED.sector, market_symbols.sector),
                industry = COALESCE(EXCLUDED.industry, market_symbols.industry),
                market_cap = COALESCE(EXCLUDED.market_cap, market_symbols.market_cap),
                -- Preserve existing is_active status unless explicitly provided (not default True)
                -- This prevents data collection from reactivating deactivated symbols
                is_active = CASE 
                    WHEN EXCLUDED.is_active = true AND market_symbols.is_active = false THEN market_symbols.is_active
                    ELSE EXCLUDED.is_active
                END,
                updated_at = NOW()
            RETURNING symbol_id;
            """,
            (
                symbol,
                exchange,
                company_name,
                sector,
                industry,
                market_cap,
                is_active,
            ),
        )
        row = cur.fetchone()
        if row is None:  # pragma: no cover - defensive
            raise psycopg.DatabaseError("Failed to upsert market symbol")
        return int(row[0])


def bulk_upsert_market_data(
    conn: Connection,
    symbol_id: int,
    interval: str,
    data: Sequence[IntervalData],
) -> int:
    """
    Insert or update OHLCV bars for a symbol.
    
    Automatically normalizes OHLC values to satisfy database constraints.
    This is especially important for live/intraday data during market hours
    where incomplete bars may violate OHLC relationships.
    """

    if not data:
        return 0

    # Normalize OHLC values to satisfy database constraints
    normalized_data = [_normalize_ohlc(bar) for bar in data]

    records = [
        (
            symbol_id,
            row.timestamp,
            interval,
            row.open,
            row.high,
            row.low,
            row.close,
            row.volume,
            None,
            None,
        )
        for row in normalized_data
    ]

    insert_sql = """
        INSERT INTO market_data (
            symbol_id,
            timestamp,
            interval_type,
            open_price,
            high_price,
            low_price,
            close_price,
            volume,
            vwap,
            true_range
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (symbol_id, timestamp, interval_type) DO UPDATE SET
            open_price = EXCLUDED.open_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            close_price = EXCLUDED.close_price,
            volume = EXCLUDED.volume,
            vwap = EXCLUDED.vwap,
            true_range = EXCLUDED.true_range;
    """

    with conn.cursor() as cur:
        cur.executemany(insert_sql, records)

    return len(records)


def get_latest_timestamp(
    conn: Connection,
    symbol_id: int,
    interval: str,
) -> datetime | None:
    """Return the most recent timestamp stored for a symbol and interval."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT timestamp
            FROM market_data
            WHERE symbol_id = %s AND interval_type = %s
            ORDER BY timestamp DESC
            LIMIT 1;
            """,
            (symbol_id, interval),
        )
        row = cur.fetchone()
        return row[0] if row else None


def ensure_symbols_bulk(
    conn: Connection,
    symbols: Iterable[tuple[str, str]],
) -> dict[str, int]:
    """Ensure multiple symbols exist and return mapping to IDs."""

    result: dict[str, int] = {}
    for symbol, exchange in symbols:
        result[symbol] = ensure_market_symbol(conn, symbol, exchange)
    return result


__all__ = [
    "ensure_market_symbol",
    "bulk_upsert_market_data",
    "get_latest_timestamp",
    "ensure_symbols_bulk",
    "get_symbol_id",
]


def get_symbol_id(conn: Connection, symbol: str) -> int | None:
    """Return the symbol_id for a given ticker if it exists."""

    with conn.cursor() as cur:
        cur.execute("SELECT symbol_id FROM market_symbols WHERE symbol = %s", (symbol,))
        row = cur.fetchone()
    return int(row[0]) if row else None


def fetch_market_data(
    conn: Connection,
    symbol: str,
    interval: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
) -> list[IntervalData]:
    """Fetch chronological OHLCV bars for a symbol and interval.

    Args:
        conn: Active psycopg connection.
        symbol: Market symbol (e.g., "AAPL").
        interval: Stored interval string (e.g., "30min").
        start: Optional starting timestamp (inclusive).
        end: Optional ending timestamp (inclusive).
        limit: Optional maximum number of rows to return (applied after filtering).

    Returns:
        List of IntervalData sorted in ascending timestamp order.
    """

    base_query = [
        "SELECT",
        "    md.timestamp,",
        "    md.open_price,",
        "    md.high_price,",
        "    md.low_price,",
        "    md.close_price,",
        "    md.volume,",
        "    s.exchange",
        "FROM market_data md",
        "JOIN market_symbols s ON s.symbol_id = md.symbol_id",
        "WHERE s.symbol = %s AND md.interval_type = %s",
    ]

    params: list[object] = [symbol, interval]

    if start is not None:
        base_query.append("AND md.timestamp >= %s")
        params.append(start)

    if end is not None:
        base_query.append("AND md.timestamp <= %s")
        params.append(end)

    base_query.append("ORDER BY md.timestamp ASC")

    if limit is not None:
        base_query.append("LIMIT %s")
        params.append(limit)

    sql = "\n".join(base_query)

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    results: list[IntervalData] = []
    for row in rows:
        timestamp, open_price, high_price, low_price, close_price, volume, exchange = row
        results.append(
            IntervalData(
                symbol=symbol,
                exchange=exchange,
                timestamp=timestamp,
                interval=interval,
                open=Decimal(str(open_price)),
                high=Decimal(str(high_price)),
                low=Decimal(str(low_price)),
                close=Decimal(str(close_price)),
                adjusted_close=Decimal(str(close_price)),
                volume=int(volume),
            )
        )

    return results


def fetch_market_data_with_aggregation(
    conn: Connection,
    symbol: str,
    interval: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
) -> list[IntervalData]:
    """
    Fetch market data, aggregating from smaller intervals if needed.
    
    This function first tries to fetch data at the requested interval.
    If no data exists, it attempts to aggregate from a smaller interval:
    - 30m requested -> fetch 5m and aggregate
    - 1h requested -> fetch 5m and aggregate  
    - 4h requested -> fetch 1h and aggregate
    
    This allows the system to store native 5m data from the API and
    aggregate to larger intervals on-demand, reducing API call waste.
    
    Args:
        conn: Active psycopg connection
        symbol: Market symbol (e.g., "AAPL")
        interval: Requested interval (e.g., "30m")
        start: Optional starting timestamp (inclusive)
        end: Optional ending timestamp (inclusive)
        limit: Optional maximum number of bars to return
        
    Returns:
        List of IntervalData in chronological order, either direct from DB
        or aggregated from smaller interval
    """
    # Try direct fetch first
    data = fetch_market_data(conn, symbol, interval, start=start, end=end, limit=limit)
    
    if data:
        LOGGER.debug(f"{symbol}: Found {len(data)} bars at {interval} interval (direct)")
        return data
    
    # Map intervals to their smaller source intervals for aggregation
    # Interval seconds for ratio calculation
    from .bar_aggregator import INTERVAL_SECONDS
    
    AGGREGATION_MAP = {
        "30m": "5m",   # Aggregate 5m -> 30m (6:1 ratio)
        "1h": "5m",    # Aggregate 5m -> 1h (12:1 ratio)
        "4h": "1h",    # Aggregate 1h -> 4h (4:1 ratio)
    }
    
    source_interval = AGGREGATION_MAP.get(interval)
    if not source_interval:
        LOGGER.debug(f"{symbol}: No data at {interval} and no aggregation path available")
        return []  # No aggregation path available
    
    # Calculate how many source bars we need to get enough aggregated bars
    source_limit = None
    if limit:
        if interval in INTERVAL_SECONDS and source_interval in INTERVAL_SECONDS:
            ratio = INTERVAL_SECONDS[interval] // INTERVAL_SECONDS[source_interval]
            source_limit = limit * ratio
            LOGGER.debug(
                f"{symbol}: Requesting {source_limit} {source_interval} bars "
                f"to aggregate {limit} {interval} bars (ratio: {ratio}:1)"
            )
    
    # Fetch source data
    source_data = fetch_market_data(
        conn, symbol, source_interval,
        start=start, end=end, limit=source_limit
    )
    
    if not source_data:
        LOGGER.debug(f"{symbol}: No {source_interval} data available for aggregation to {interval}")
        return []
    
    # Aggregate to target interval
    from .bar_aggregator import aggregate_bars
    aggregated = aggregate_bars(source_data, interval)
    
    # Apply limit to aggregated data if needed
    if limit and len(aggregated) > limit:
        aggregated = aggregated[-limit:]  # Take most recent N bars
    
    LOGGER.debug(
        f"{symbol}: Aggregated {len(source_data)} {source_interval} bars "
        f"to {len(aggregated)} {interval} bars"
    )
    
    return aggregated


__all__.append("fetch_market_data")
__all__.append("fetch_market_data_with_aggregation")
