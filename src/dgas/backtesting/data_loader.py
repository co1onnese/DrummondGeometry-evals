"""Utilities for loading historical market data for backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, MutableMapping, Sequence

from psycopg import Connection

from ..data.models import IntervalData
from ..data.repository import fetch_market_data
from ..db import get_connection


@dataclass(frozen=True)
class BacktestBar:
    """Single bar plus optional indicator snapshot."""

    bar: IntervalData
    indicators: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestDataset:
    """Complete set of data required for a symbol backtest."""

    symbol: str
    interval: str
    bars: Sequence[BacktestBar]

    def __iter__(self):
        return iter(self.bars)


def load_ohlcv(
    symbol: str,
    interval: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
    conn: Connection | None = None,
) -> list[IntervalData]:
    """Load historical OHLCV bars for a given symbol/interval."""

    if conn is None:
        with get_connection() as owned_conn:
            return fetch_market_data(owned_conn, symbol, interval, start=start, end=end, limit=limit)
    return fetch_market_data(conn, symbol, interval, start=start, end=end, limit=limit)


def load_indicator_snapshots(
    symbol: str,
    interval: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    conn: Connection | None = None,
) -> MutableMapping[datetime, Mapping[str, Any]]:
    """Load precomputed indicator snapshots keyed by timestamp.

    Placeholder implementation returns an empty mapping. Future iterations will
    pull from market_states_v2, pattern_events, and multi_timeframe_analysis to
    enrich strategy context.
    """

    _ = (symbol, interval, start, end, conn)
    return {}


def assemble_bars(
    bars: Sequence[IntervalData],
    indicators: Mapping[datetime, Mapping[str, Any]] | None = None,
) -> list[BacktestBar]:
    """Combine OHLCV bars with their indicator snapshots."""

    indicator_lookup = indicators or {}
    return [BacktestBar(bar=item, indicators=indicator_lookup.get(item.timestamp, {})) for item in bars]


def load_dataset(
    symbol: str,
    interval: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    include_indicators: bool = True,
    limit: int | None = None,
    conn: Connection | None = None,
) -> BacktestDataset:
    """Load a full dataset ready for simulation."""

    bars = load_ohlcv(symbol, interval, start=start, end=end, limit=limit, conn=conn)
    indicator_map = (
        load_indicator_snapshots(symbol, interval, start=start, end=end, conn=conn)
        if include_indicators
        else {}
    )
    assembled = assemble_bars(bars, indicator_map)
    return BacktestDataset(symbol=symbol, interval=interval, bars=assembled)


__all__ = [
    "BacktestBar",
    "BacktestDataset",
    "load_ohlcv",
    "load_indicator_snapshots",
    "assemble_bars",
    "load_dataset",
]
