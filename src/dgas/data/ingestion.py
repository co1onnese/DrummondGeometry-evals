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


def backfill_intraday(
    symbol: str,
    *,
    exchange: str,
    start_date: str,
    end_date: str,
    interval: str = "30m",
    client: EODHDClient | None = None,
) -> IngestionSummary:
    """Fetch and persist historical intraday data for a symbol."""

    with _client_context(client) as api:
        bars = api.fetch_intraday(symbol, start=start_date, end=end_date, interval=interval)

    quality = analyze_intervals(bars)

    stored = 0
    if bars:
        exchange_value = bars[0].exchange or exchange
        with get_connection() as conn:
            symbol_id = ensure_market_symbol(conn, symbol, exchange_value)
            stored = bulk_upsert_market_data(conn, symbol_id, interval, bars)

    LOGGER.info(
        "Backfill complete: %s (%s) fetched=%s stored=%s duplicates=%s gaps=%s",
        symbol,
        interval,
        len(bars),
        stored,
        quality.duplicate_count,
        quality.gap_count,
    )

    return IngestionSummary(
        symbol=symbol,
        interval=interval,
        fetched=len(bars),
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
        bars = api.fetch_eod(symbol, start=start_date, end=end_date)

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
) -> IngestionSummary:
    """Update a symbol using the most recent data, fetching a small buffer window."""

    latest_ts: datetime | None
    with get_connection() as conn:
        symbol_id = ensure_market_symbol(conn, symbol, exchange)
        latest_ts = get_latest_timestamp(conn, symbol_id, interval)

    if latest_ts is None:
        if not default_start:
            raise ValueError(
                "No existing data for symbol; provide default_start for initial incremental update"
            )
        start_date = default_start
    else:
        start_dt = (latest_ts - timedelta(days=buffer_days)).date()
        start_date = start_dt.isoformat()

    end_date = datetime.now(timezone.utc).date().isoformat()

    return backfill_intraday(
        symbol,
        exchange=exchange,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        client=client,
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
