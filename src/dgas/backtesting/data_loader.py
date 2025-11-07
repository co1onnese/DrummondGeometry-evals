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
    if not trading_bars:
        return {}

    htf_bars = load_ohlcv(symbol, htf_interval, start=start, end=end, conn=conn)
    if not htf_bars:
        return {}

    coordinator = MultiTimeframeCoordinator(htf_interval, trading_interval)
    indicator_map: Dict[datetime, Mapping[str, Any]] = {}

    trading_sorted = sorted(trading_bars, key=lambda bar: bar.timestamp)
    htf_sorted = sorted(htf_bars, key=lambda bar: bar.timestamp)

    accumulated_trading: list[IntervalData] = []
    accumulated_htf: list[IntervalData] = []
    htf_index = 0

    for bar in trading_sorted:
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
        except ValueError:
            continue

        indicator_map[bar.timestamp] = {"analysis": analysis}

    return indicator_map


__all__ = [
    "BacktestBar",
    "BacktestDataset",
    "load_ohlcv",
    "load_indicator_snapshots",
    "assemble_bars",
    "load_dataset",
]
