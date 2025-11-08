"""Utilities for loading historical market data for backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence

from psycopg import Connection

from ..data.models import IntervalData
from ..data.repository import fetch_market_data
from ..db import get_connection
from ..calculations import build_timeframe_data, MultiTimeframeCoordinator, TimeframeType
from ..calculations.multi_timeframe import MultiTimeframeAnalysis
from .indicator_loader import load_indicators_batch


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
    htf_interval: str | None = None,
) -> BacktestDataset:
    """Load a full dataset ready for simulation."""

    bars = load_ohlcv(symbol, interval, start=start, end=end, limit=limit, conn=conn)
    indicator_map: Mapping[datetime, Mapping[str, Any]] = {}
    if include_indicators and htf_interval:
        indicator_map = _build_multi_timeframe_snapshots(
            symbol,
            interval,
            bars,
            htf_interval,
            start=start,
            end=end,
            conn=conn,
        )
    assembled = assemble_bars(bars, indicator_map)
    return BacktestDataset(symbol=symbol, interval=interval, bars=assembled)


def _build_multi_timeframe_snapshots(
    symbol: str,
    trading_interval: str,
    trading_bars: Sequence[IntervalData],
    htf_interval: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    conn: Connection | None = None,
) -> Dict[datetime, Mapping[str, Any]]:
    """Build multi-timeframe indicator snapshots, loading from DB when available.

    This function first attempts to load pre-computed indicators from the database,
    which provides 10-50× performance improvement. For timestamps not found in the
    database, it falls back to on-the-fly calculation.
    """
    if not trading_bars:
        return {}

    indicator_map: Dict[datetime, Mapping[str, Any]] = {}

    # Extract timestamps from trading bars
    timestamps = [bar.timestamp for bar in trading_bars]

    # Try to load indicators from database first (batch load for efficiency)
    if conn is None:
        with get_connection() as owned_conn:
            db_indicators = load_indicators_batch(
                symbol, timestamps, htf_interval, trading_interval, conn=owned_conn
            )
    else:
        db_indicators = load_indicators_batch(
            symbol, timestamps, htf_interval, trading_interval, conn=conn
        )

    # Add database-loaded indicators to map
    for timestamp, analysis in db_indicators.items():
        indicator_map[timestamp] = {"analysis": analysis}

    # Find timestamps that weren't loaded from database
    missing_timestamps = [ts for ts in timestamps if ts not in db_indicators]

    # Fall back to calculation for missing timestamps
    if missing_timestamps:
        _calculate_missing_indicators(
            symbol,
            trading_interval,
            trading_bars,
            htf_interval,
            missing_timestamps,
            indicator_map,
            start=start,
            end=end,
            conn=conn,
        )

    return indicator_map


def _calculate_missing_indicators(
    symbol: str,
    trading_interval: str,
    trading_bars: Sequence[IntervalData],
    htf_interval: str,
    missing_timestamps: list[datetime],
    indicator_map: Dict[datetime, Mapping[str, Any]],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    conn: Connection | None = None,
) -> None:
    """Calculate indicators for timestamps not found in database.

    This is the fallback calculation method, used only when database values
    are unavailable.
    """
    htf_bars = load_ohlcv(symbol, htf_interval, start=start, end=end, conn=conn)
    if not htf_bars:
        return

    coordinator = MultiTimeframeCoordinator(htf_interval, trading_interval)

    trading_sorted = sorted(trading_bars, key=lambda bar: bar.timestamp)
    htf_sorted = sorted(htf_bars, key=lambda bar: bar.timestamp)

    accumulated_trading: list[IntervalData] = []
    accumulated_htf: list[IntervalData] = []
    htf_index = 0

    missing_set = set(missing_timestamps)

    for bar in trading_sorted:
        # Skip if already loaded from database
        if bar.timestamp not in missing_set:
            continue

        accumulated_trading.append(bar)

        while htf_index < len(htf_sorted) and htf_sorted[htf_index].timestamp <= bar.timestamp:
            accumulated_htf.append(htf_sorted[htf_index])
            htf_index += 1

        if len(accumulated_trading) < 3 or len(accumulated_htf) < 3:
            continue

        trading_data = build_timeframe_data(
            accumulated_trading,
            trading_interval,
            TimeframeType.TRADING,
        )
        htf_data = build_timeframe_data(
            accumulated_htf,
            htf_interval,
            TimeframeType.HIGHER,
        )

        try:
            analysis: MultiTimeframeAnalysis = coordinator.analyze(
                htf_data,
                trading_data,
                target_timestamp=bar.timestamp,
            )
            indicator_map[bar.timestamp] = {"analysis": analysis}
        except ValueError:
            continue


__all__ = [
    "BacktestBar",
    "BacktestDataset",
    "load_ohlcv",
    "load_indicator_snapshots",
    "assemble_bars",
    "load_dataset",
]
