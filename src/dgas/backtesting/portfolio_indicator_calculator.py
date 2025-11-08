"""On-the-fly indicator calculation for portfolio backtesting.

Calculates multi-timeframe analysis indicators during backtest execution
without requiring pre-computed database storage.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Sequence

from ..data.models import IntervalData
from ..data.repository import fetch_market_data
from ..db import get_connection
from ..calculations import build_timeframe_data, MultiTimeframeCoordinator, TimeframeType
from ..calculations.multi_timeframe import MultiTimeframeAnalysis


@dataclass
class HTFDataCache:
    """Cache for higher timeframe data to avoid repeated database queries."""

    symbol: str
    interval: str
    bars: List[IntervalData]
    start_date: datetime
    end_date: datetime


class PortfolioIndicatorCalculator:
    """Calculate indicators on-the-fly for portfolio backtesting."""

    def __init__(
        self,
        htf_interval: str = "1d",
        trading_interval: str = "30m",
    ):
        """Initialize indicator calculator.

        Args:
            htf_interval: Higher timeframe interval (e.g., "1d")
            trading_interval: Trading timeframe interval (e.g., "30m")
        """
        self.htf_interval = htf_interval
        self.trading_interval = trading_interval
        self.coordinator = MultiTimeframeCoordinator(htf_interval, trading_interval)

        # Cache HTF data by symbol
        self.htf_cache: Dict[str, HTFDataCache] = {}

    def load_htf_data_for_symbol(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> None:
        """Pre-load higher timeframe data for a symbol.

        Args:
            symbol: Symbol to load HTF data for
            start: Start date
            end: End date
        """
        with get_connection() as conn:
            htf_bars = fetch_market_data(
                conn,
                symbol,
                self.htf_interval,
                start=start,
                end=end,
            )

        if htf_bars:
            self.htf_cache[symbol] = HTFDataCache(
                symbol=symbol,
                interval=self.htf_interval,
                bars=list(htf_bars),
                start_date=start,
                end_date=end,
            )

    def calculate_indicators(
        self,
        symbol: str,
        current_bar: IntervalData,
        historical_bars: Sequence[IntervalData],
    ) -> Dict[str, Any]:
        """Calculate multi-timeframe indicators for a symbol at current bar.

        Args:
            symbol: Symbol being analyzed
            current_bar: Current trading bar
            historical_bars: Historical trading bars up to current bar

        Returns:
            Dictionary with 'analysis' key containing MultiTimeframeAnalysis

        Raises:
            ValueError: If insufficient data for calculation
        """
        # Get HTF data up to current timestamp
        htf_bars_up_to_now = self._get_htf_bars_up_to(
            symbol,
            current_bar.timestamp,
        )

        if len(historical_bars) < 3:
            raise ValueError(f"Insufficient trading bars: {len(historical_bars)} < 3")

        if len(htf_bars_up_to_now) < 3:
            raise ValueError(f"Insufficient HTF bars: {len(htf_bars_up_to_now)} < 3")

        # Build timeframe data
        trading_data = build_timeframe_data(
            list(historical_bars),
            self.trading_interval,
            TimeframeType.TRADING,
        )

        htf_data = build_timeframe_data(
            htf_bars_up_to_now,
            self.htf_interval,
            TimeframeType.HIGHER,
        )

        # Run multi-timeframe analysis
        analysis: MultiTimeframeAnalysis = self.coordinator.analyze(
            htf_data,
            trading_data,
            target_timestamp=current_bar.timestamp,
        )

        return {"analysis": analysis}

    def _get_htf_bars_up_to(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> List[IntervalData]:
        """Get HTF bars up to (and including) timestamp.

        Uses binary search for O(log n) lookup instead of linear scan.

        Args:
            symbol: Symbol to get HTF bars for
            timestamp: Cut-off timestamp

        Returns:
            List of HTF bars up to timestamp
        """
        if symbol not in self.htf_cache:
            # HTF data not loaded for this symbol
            return []

        cache = self.htf_cache[symbol]
        bars = cache.bars

        # Bars should be sorted by timestamp (from database ORDER BY timestamp)
        # Use binary search to find insertion point
        # bisect_right returns the index where timestamp would be inserted to maintain sorted order
        idx = bisect.bisect_right(bars, timestamp, key=lambda b: b.timestamp)
        return bars[:idx]

    def preload_htf_data_for_portfolio(
        self,
        symbols: List[str],
        start: datetime,
        end: datetime,
    ) -> None:
        """Pre-load HTF data for all symbols in portfolio.

        Args:
            symbols: List of symbols
            start: Start date
            end: End date
        """
        print(f"Pre-loading HTF data for {len(symbols)} symbols...")

        loaded = 0
        failed = 0

        for symbol in symbols:
            try:
                self.load_htf_data_for_symbol(symbol, start, end)
                loaded += 1
            except Exception as e:
                failed += 1
                print(f"  ⚠ Failed to load HTF data for {symbol}: {e}")

        print(f"✓ Loaded HTF data: {loaded} symbols ({failed} failed)")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about cached HTF data.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "cached_symbols": len(self.htf_cache),
            "total_htf_bars": sum(len(cache.bars) for cache in self.htf_cache.values()),
            "symbols": list(self.htf_cache.keys()),
        }


__all__ = [
    "PortfolioIndicatorCalculator",
    "HTFDataCache",
]
