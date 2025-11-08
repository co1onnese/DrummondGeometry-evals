#!/usr/bin/env python3
"""Test portfolio backtest on small dataset.

Quick validation test before running full 3-month backtest.
Tests with 5 symbols over 1-2 days to ensure everything works.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.backtesting.portfolio_engine import (
    PortfolioBacktestConfig,
    PortfolioBacktestEngine,
)
from dgas.backtesting.strategies.multi_timeframe import (
    MultiTimeframeStrategy,
    MultiTimeframeStrategyConfig,
)


def main() -> int:
    """Run quick validation test."""
    print("\n" + "="*80)
    print("PORTFOLIO BACKTEST VALIDATION TEST")
    print("="*80 + "\n")

    # Test with just a few symbols for 2 days
    TEST_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]
    START_DATE = datetime(2025, 10, 30, tzinfo=timezone.utc)  # Use available data
    END_DATE = datetime(2025, 11, 1, tzinfo=timezone.utc)
    INTERVAL = "30m"

    print("Test Configuration:")
    print(f"  Symbols: {', '.join(TEST_SYMBOLS)}")
    print(f"  Date Range: {START_DATE.date()} to {END_DATE.date()}")
    print(f"  Interval: {INTERVAL}")
    print(f"  Initial Capital: $100,000")
    print(f"  Risk per Trade: 2%\n")

    # Create configuration
    portfolio_config = PortfolioBacktestConfig(
        initial_capital=Decimal("100000"),
        risk_per_trade_pct=Decimal("0.02"),
        max_positions=5,
        commission_rate=Decimal("0.0"),
        slippage_bps=Decimal("2.0"),
        regular_hours_only=True,  # ✓ Market hours filtering now enabled!
        allow_short=True,
    )

    # Create strategy
    strategy_config = MultiTimeframeStrategyConfig(
        allow_short=True,
        max_risk_fraction=Decimal("0.02"),
    )
    strategy = MultiTimeframeStrategy(strategy_config)

    # Create engine
    engine = PortfolioBacktestEngine(
        config=portfolio_config,
        strategy=strategy,
    )

    print("Running test backtest...\n")

    try:
        result = engine.run(
            symbols=TEST_SYMBOLS,
            interval=INTERVAL,
            start=START_DATE,
            end=END_DATE,
        )

        print(f"\n{'='*80}")
        print("TEST RESULTS")
        print(f"{'='*80}")
        print(f"\nStarting Capital: ${result.starting_capital:,.2f}")
        print(f"Ending Equity:    ${result.ending_equity:,.2f}")
        print(f"Return:           {result.total_return:.2%}")
        print(f"Total Trades:     {result.trade_count}")
        print(f"Total Bars:       {result.total_bars:,}")

        if result.trades:
            print(f"\nSample Trades:")
            for i, trade in enumerate(result.trades[:5], 1):
                print(f"  {i}. {trade.symbol} {trade.side.value.upper()}: "
                      f"${trade.net_profit:,.2f} P&L")

        print(f"\n{'='*80}")
        print("✓ VALIDATION TEST PASSED")
        print(f"{'='*80}\n")

        return 0

    except Exception as e:
        print(f"\n{'='*80}")
        print("✗ VALIDATION TEST FAILED")
        print(f"{'='*80}")
        print(f"\nError: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
