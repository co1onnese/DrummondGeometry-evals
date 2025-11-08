#!/usr/bin/env python3
"""Small-scale test for evaluation backtest.

Tests with 5 symbols over 1 week to validate the evaluation system works correctly.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.backtesting.portfolio_engine import (
    PortfolioBacktestConfig,
    PortfolioBacktestEngine,
)
from dgas.backtesting.strategies.prediction_signal import (
    PredictionSignalStrategy,
    PredictionSignalStrategyConfig,
)


def main() -> int:
    """Run small-scale validation test."""
    print("\n" + "="*80)
    print("EVALUATION BACKTEST - SMALL SCALE TEST")
    print("="*80 + "\n")

    # Test with just a few symbols for 1 week
    TEST_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]
    
    # Use a date range that should have data (part of the evaluation period)
    # Use first week of the evaluation period: 2025-09-07 to 2025-09-14
    START_DATE = datetime(2025, 9, 7, tzinfo=timezone.utc)
    END_DATE = datetime(2025, 9, 14, tzinfo=timezone.utc)
    
    INTERVAL = "30m"

    print("Test Configuration:")
    print(f"  Symbols: {', '.join(TEST_SYMBOLS)}")
    print(f"  Date Range: {START_DATE.date()} to {END_DATE.date()}")
    print(f"  Interval: {INTERVAL}")
    print(f"  Initial Capital: $100,000")
    print(f"  Risk per Trade: 2%")
    print(f"  Strategy: PredictionSignalStrategy\n")

    # Create configuration
    portfolio_config = PortfolioBacktestConfig(
        initial_capital=Decimal("100000"),
        risk_per_trade_pct=Decimal("0.02"),
        max_positions=5,
        commission_rate=Decimal("0.0"),
        slippage_bps=Decimal("2.0"),
        regular_hours_only=True,
        allow_short=True,
        htf_interval="1d",
        trading_interval="30m",
    )

    # Create strategy
    strategy_config = PredictionSignalStrategyConfig(
        allow_short=True,
        min_alignment_score=0.6,
        min_signal_strength=0.5,
    )
    strategy = PredictionSignalStrategy(strategy_config)

    # Create engine
    engine = PortfolioBacktestEngine(
        config=portfolio_config,
        strategy=strategy,
    )

    print("Running test...\n")

    try:
        result = engine.run(
            symbols=TEST_SYMBOLS,
            interval=INTERVAL,
            start=START_DATE,
            end=END_DATE,
        )

        print("\n" + "="*80)
        print("TEST RESULTS")
        print("="*80)
        print(f"\nSymbols Processed: {len(result.symbols)}")
        print(f"Total Trades: {result.trade_count}")
        print(f"Starting Capital: ${result.starting_capital:,.2f}")
        print(f"Ending Equity: ${result.ending_equity:,.2f}")
        print(f"Total Return: {result.total_return:.2%}")
        
        # Print signal accuracy if available
        if "signal_accuracy" in result.metadata:
            accuracy = result.metadata["signal_accuracy"]
            print(f"\nSignal Accuracy:")
            print(f"  Total Signals: {accuracy.get('total_signals', 0)}")
            print(f"  Executed Signals: {accuracy.get('executed_signals', 0)}")
            print(f"  Win Rate: {accuracy.get('win_rate', 0):.1%}")
            print(f"  Avg Confidence (Winning): {accuracy.get('avg_confidence_winning', 0):.1%}")
            print(f"  Avg Confidence (Losing): {accuracy.get('avg_confidence_losing', 0):.1%}")

        print("\n✓ Test completed successfully!\n")
        return 0

    except Exception as e:
        print(f"\n✗ ERROR: Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
