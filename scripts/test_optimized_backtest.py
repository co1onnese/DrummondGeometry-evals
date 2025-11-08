#!/usr/bin/env python3
"""Test portfolio backtest with optimized data loading.

Tests with 10 symbols to verify the backtest can complete, then
we can scale to the full 101 symbols.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.backtesting.portfolio_engine import (
    PortfolioBacktestConfig,
    PortfolioBacktestEngine,
)
from dgas.backtesting.strategies.multi_timeframe import (
    MultiTimeframeStrategy,
    MultiTimeframeStrategyConfig,
)
# No bulk import needed - using portfolio engine's built-in loader


def main():
    print("="*80)
    print("OPTIMIZED PORTFOLIO BACKTEST TEST (10 symbols)")
    print("="*80)

    # Configuration (same as full backtest)
    START_DATE = datetime(2025, 8, 8, tzinfo=timezone.utc)
    END_DATE = datetime(2025, 11, 1, tzinfo=timezone.utc)
    INTERVAL = "30m"
    INITIAL_CAPITAL = Decimal("100000")
    RISK_PER_TRADE = Decimal("0.02")
    COMMISSION = Decimal("0.0")
    SLIPPAGE = Decimal("2.0")
    REGULAR_HOURS_ONLY = True

    print("\nConfiguration:")
    print(f"  Symbols: 10 (AAPL, MSFT, GOOGL, NVDA, META, AMZN, TSLA, AVGO, PEP, COST)")
    print(f"  Period: {START_DATE.date()} to {END_DATE.date()}")
    print(f"  Initial Capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"  Risk per Trade: {RISK_PER_TRADE:.1%}")
    print()

    # Use just 10 symbols for testing
    symbols = ["AAPL", "MSFT", "GOOGL", "NVDA", "META", "AMZN", "TSLA", "AVGO", "PEP", "COST"]

    # Create config
    portfolio_config = PortfolioBacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        risk_per_trade_pct=RISK_PER_TRADE,
        max_positions=10,
        max_portfolio_risk_pct=Decimal("0.10"),
        commission_rate=COMMISSION,
        slippage_bps=SLIPPAGE,
        regular_hours_only=REGULAR_HOURS_ONLY,
        exchange_code="US",
        allow_short=True,
        htf_interval="1d",
        trading_interval="30m",
        max_signals_per_bar=5,
    )

    # Create strategy
    strategy_config = MultiTimeframeStrategyConfig(
        allow_short=True,
        max_risk_fraction=RISK_PER_TRADE,
    )
    strategy = MultiTimeframeStrategy(strategy_config)

    # Create and run engine
    engine = PortfolioBacktestEngine(
        config=portfolio_config,
        strategy=strategy,
    )

    print("Starting optimized backtest...")
    print("(Using bulk data loading)\n")

    try:
        result = engine.run(
            symbols=symbols,
            interval=INTERVAL,
            start=START_DATE,
            end=END_DATE,
        )

        # Print summary
        print("\n" + "="*80)
        print("TEST RESULTS")
        print("="*80)
        print(f"\nStarting Capital: ${result.starting_capital:,.2f}")
        print(f"Ending Equity:    ${result.ending_equity:,.2f}")
        print(f"Return:           {result.total_return:.2%}")
        print(f"Total Trades:     {result.trade_count}")
        print(f"Total Bars:       {result.total_bars:,}")

        if result.trades:
            print("\nTrade Details:")
            for i, trade in enumerate(result.trades[:5], 1):
                print(f"  {i}. {trade.symbol} {trade.direction}: ${trade.net_profit:.2f}")

        print("\n" + "="*80)
        print("✓ OPTIMIZED TEST COMPLETE")
        print("="*80)

        return 0

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
