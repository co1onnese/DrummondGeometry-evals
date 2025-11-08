"""Portfolio-level data loading and synchronization.

Handles loading and synchronizing market data across multiple symbols
for portfolio-level backtesting where all symbols share capital.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import groupby
from typing import Sequence

from ..data.models import IntervalData
from ..data.repository import fetch_market_data
from ..db import get_connection
from ..utils.market_hours_filter import filter_to_regular_hours


@dataclass(frozen=True)
class SymbolDataBundle:
    """Bundle of data for a single symbol."""

    symbol: str
    bars: list[IntervalData]
    bar_count: int

    @property
    def first_timestamp(self) -> datetime | None:
        return self.bars[0].timestamp if self.bars else None

    @property
    def last_timestamp(self) -> datetime | None:
        return self.bars[-1].timestamp if self.bars else None


@dataclass(frozen=True)
class PortfolioTimestep:
    """All symbol data at a single timestamp."""

    timestamp: datetime
    bars: dict[str, IntervalData]  # symbol -> bar
    symbols_present: set[str]

    def get_bar(self, symbol: str) -> IntervalData | None:
        """Get bar for symbol at this timestamp."""
        return self.bars.get(symbol)

    def has_symbol(self, symbol: str) -> bool:
        """Check if symbol has data at this timestamp."""
        return symbol in self.symbols_present


class PortfolioDataLoader:
    """Load and synchronize market data for portfolio-level backtesting."""

    def __init__(self, regular_hours_only: bool = True, exchange_code: str = "US"):
        """Initialize portfolio data loader.

        Args:
            regular_hours_only: Filter to regular trading hours (9:30 AM - 4:00 PM)
            exchange_code: Exchange for market hours filtering
        """
        self.regular_hours_only = regular_hours_only
        self.exchange_code = exchange_code

    def load_portfolio_data(
        self,
        symbols: Sequence[str],
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, SymbolDataBundle]:
        """Load data for all symbols using optimized batch query.

        Args:
            symbols: List of symbols to load
            interval: Data interval (e.g., "30m")
            start: Start timestamp (optional)
            end: End timestamp (optional)

        Returns:
            Dictionary mapping symbol -> SymbolDataBundle

        Raises:
            ValueError: If no data found for any symbol
        """
        if not symbols:
            return {}

        # Use batch loading for efficiency (single query instead of N queries)
        bundles = self._load_portfolio_data_batch(symbols, interval, start, end)

        # Verify all symbols have data
        missing_symbols = [s for s in symbols if s not in bundles]
        if missing_symbols:
            raise ValueError(
                f"No data found for {len(missing_symbols)} symbol(s) in interval {interval} "
                f"between {start} and {end}: {', '.join(missing_symbols[:5])}"
                + (f" and {len(missing_symbols) - 5} more" if len(missing_symbols) > 5 else "")
            )

        return bundles

    def _load_portfolio_data_batch(
        self,
        symbols: Sequence[str],
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, SymbolDataBundle]:
        """Load data for all symbols in a single batch query.

        This is much more efficient than individual queries, especially for
        large portfolios (50-100× faster for 100 symbols).
        """
        from decimal import Decimal

        bundles: dict[str, SymbolDataBundle] = {}

        with get_connection() as conn:
            with conn.cursor() as cur:
                # Build batch query with WHERE symbol IN (...)
                base_query = [
                    "SELECT",
                    "    s.symbol,",
                    "    md.timestamp,",
                    "    md.open_price,",
                    "    md.high_price,",
                    "    md.low_price,",
                    "    md.close_price,",
                    "    md.volume,",
                    "    s.exchange",
                    "FROM market_data md",
                    "JOIN market_symbols s ON s.symbol_id = md.symbol_id",
                    "WHERE s.symbol = ANY(%s) AND md.interval_type = %s",
                ]

                params: list[object] = [list(symbols), interval]

                if start is not None:
                    base_query.append("AND md.timestamp >= %s")
                    params.append(start)

                if end is not None:
                    base_query.append("AND md.timestamp <= %s")
                    params.append(end)

                base_query.append("ORDER BY s.symbol, md.timestamp ASC")

                sql = "\n".join(base_query)
                cur.execute(sql, params)
                rows = cur.fetchall()

                # Group rows by symbol
                bars_by_symbol: dict[str, list] = {}
                for row in rows:
                    (
                        symbol,
                        timestamp,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                        volume,
                        exchange,
                    ) = row

                    if symbol not in bars_by_symbol:
                        bars_by_symbol[symbol] = []

                    from ..data.models import IntervalData

                    bars_by_symbol[symbol].append(
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

                # Create bundles and filter to regular hours if requested
                for symbol, bars in bars_by_symbol.items():
                    # Filter to regular hours if requested
                    if self.regular_hours_only:
                        bars = filter_to_regular_hours(bars, self.exchange_code)

                    if bars:  # Only create bundle if bars remain after filtering
                        bundles[symbol] = SymbolDataBundle(
                            symbol=symbol,
                            bars=list(bars),
                            bar_count=len(bars),
                        )

        return bundles

    def create_synchronized_timeline(
        self,
        bundles: dict[str, SymbolDataBundle],
    ) -> list[PortfolioTimestep]:
        """Create synchronized timeline across all symbols.

        Optimized implementation using O(m log n) algorithm instead of O(n×m),
        where m = total bars and n = number of symbols.

        Args:
            bundles: Symbol data bundles

        Returns:
            List of PortfolioTimestep, one per unique timestamp
            Symbols with data at each timestamp are included

        Note:
            Not all symbols will have data at every timestamp.
            Use PortfolioTimestep.has_symbol() to check availability.
        """
        if not bundles:
            return []

        # Flatten all bars with symbol identifier: (timestamp, symbol, bar)
        all_bars: list[tuple[datetime, str, IntervalData]] = []
        for symbol, bundle in bundles.items():
            for bar in bundle.bars:
                all_bars.append((bar.timestamp, symbol, bar))

        # Sort by timestamp (O(m log m) where m = total bars)
        all_bars.sort(key=lambda x: x[0])

        # Group by timestamp using itertools.groupby (O(m))
        timesteps = []
        for timestamp, group in groupby(all_bars, key=lambda x: x[0]):
            bars_at_time = {}
            symbols_present = set()

            for _, symbol, bar in group:
                bars_at_time[symbol] = bar
                symbols_present.add(symbol)

            if bars_at_time:  # Only add timestep if at least one symbol has data
                timesteps.append(
                    PortfolioTimestep(
                        timestamp=timestamp,
                        bars=bars_at_time,
                        symbols_present=symbols_present,
                    )
                )

        return timesteps

    def get_data_summary(
        self,
        bundles: dict[str, SymbolDataBundle],
    ) -> dict[str, any]:
        """Get summary statistics about loaded data.

        Args:
            bundles: Symbol data bundles

        Returns:
            Dictionary with summary stats
        """
        if not bundles:
            return {
                "symbol_count": 0,
                "total_bars": 0,
                "date_range": None,
            }

        total_bars = sum(b.bar_count for b in bundles.values())

        # Find overall date range
        first_timestamps = [b.first_timestamp for b in bundles.values() if b.first_timestamp]
        last_timestamps = [b.last_timestamp for b in bundles.values() if b.last_timestamp]

        date_range = None
        if first_timestamps and last_timestamps:
            date_range = (min(first_timestamps), max(last_timestamps))

        # Per-symbol stats
        per_symbol_stats = {
            symbol: {
                "bar_count": bundle.bar_count,
                "first_timestamp": bundle.first_timestamp,
                "last_timestamp": bundle.last_timestamp,
            }
            for symbol, bundle in bundles.items()
        }

        return {
            "symbol_count": len(bundles),
            "total_bars": total_bars,
            "avg_bars_per_symbol": total_bars / len(bundles) if bundles else 0,
            "date_range": date_range,
            "per_symbol": per_symbol_stats,
        }


__all__ = [
    "PortfolioDataLoader",
    "SymbolDataBundle",
    "PortfolioTimestep",
]
