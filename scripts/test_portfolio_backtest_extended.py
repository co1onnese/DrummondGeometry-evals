#!/usr/bin/env python3
"""Extended test with more data for signal generation validation."""

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


def main() -> int:
    """Run extended validation test with more data."""
    print("\n" + "="*80)
    print("EXTENDED PORTFOLIO BACKTEST TEST (1 WEEK)")
    print("="*80 + "\n")

    # Test with 1 week of data
    TEST_SYMBOLS = ["AAPL", "MSFT", "GOOGL"]
    START_DATE = datetime(2025, 10, 20, tzinfo=timezone.utc)  # 1+ weeks
    END_DATE = datetime(2025, 11, 1, tzinfo=timezone.utc)
    INTERVAL = "30m"

    print("Test Configuration:")
    print(f"  Symbols: {', '.join(TEST_SYMBOLS)}")
    print(f"  Date Range: {START_DATE.date()} to {END_DATE.date()} (11 days)")
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
        regular_hours_only=True,
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

    print("Running extended test backtest...\n")

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
            print(f"\n✓ SUCCESS: Signals Generated!")
            print(f"\nTrade Details:")
            for i, trade in enumerate(result.trades[:10], 1):
                pnl_pct = (trade.net_profit / (trade.quantity * trade.entry_price)) * 100
                print(f"  {i}. {trade.symbol} {trade.side.value.upper()}: "
                      f"${trade.net_profit:+,.2f} ({pnl_pct:+.2f}%)")
        else:
            print(f"\n⚠ No trades generated (strategy may need more data or tuning)")

        print(f"\n{'='*80}")
        print("✓ EXTENDED TEST COMPLETE")
        print(f"{'='*80}\n")

        return 0

    except Exception as e:
        print(f"\n{'='*80}")
        print("✗ EXTENDED TEST FAILED")
        print(f"{'='*80}")
        print(f"\nError: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
