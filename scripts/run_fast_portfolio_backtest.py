#!/usr/bin/env python3
"""Fast portfolio backtest with optimized configuration.

Skips slow symbol verification and uses a focused subset of 30 symbols
for a complete portfolio backtest in reasonable time.
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
    PortfolioBacktestResult,
)
from dgas.backtesting.strategies.multi_timeframe import (
    MultiTimeframeStrategy,
    MultiTimeframeStrategyConfig,
)
from dgas.backtesting.metrics import calculate_performance
from dgas.db import get_connection


def print_summary(result: PortfolioBacktestResult) -> None:
    """Print summary of backtest results."""
    print(f"\n{'='*80}")
    print("PORTFOLIO BACKTEST RESULTS")
    print(f"{'='*80}")

    print(f"\nPortfolio Details:")
    print(f"  Symbols: {len(result.symbols)}")
    print(f"  Period: {result.start_date.date()} to {result.end_date.date()}")
    print(f"  Total Bars: {result.total_bars:,}")

    print(f"\nCapital:")
    print(f"  Starting: ${result.starting_capital:,.2f}")
    print(f"  Ending:   ${result.ending_equity:,.2f}")
    print(f"  Return:   {result.total_return:.2%}")

    print(f"\nTrading Activity:")
    print(f"  Total Trades: {result.trade_count}")

    if result.trades:
        winning_trades = [t for t in result.trades if t.net_profit > 0]
        losing_trades = [t for t in result.trades if t.net_profit <= 0]

        print(f"  Winning Trades: {len(winning_trades)}")
        print(f"  Losing Trades: {len(losing_trades)}")

        if result.trade_count > 0:
            win_rate = len(winning_trades) / result.trade_count
            print(f"  Win Rate: {win_rate:.1%}")

        if winning_trades:
            avg_win = sum(t.net_profit for t in winning_trades) / len(winning_trades)
            print(f"  Avg Win: ${avg_win:,.2f}")

        if losing_trades:
            avg_loss = sum(t.net_profit for t in losing_trades) / len(losing_trades)
            print(f"  Avg Loss: ${avg_loss:,.2f}")

    print(f"\n{'='*80}\n")


def main() -> int:
    """Main execution function."""
    print(f"\n{'='*80}")
    print("FAST PORTFOLIO BACKTEST")
    print("Optimized: 30 symbols, no verification delay")
    print(f"{'='*80}\n")

    # Configuration
    START_DATE = datetime(2025, 8, 8, tzinfo=timezone.utc)
    END_DATE = datetime(2025, 11, 1, tzinfo=timezone.utc)
    INTERVAL = "30m"
    INITIAL_CAPITAL = Decimal("100000")
    RISK_PER_TRADE = Decimal("0.02")
    COMMISSION = Decimal("0.0")
    SLIPPAGE = Decimal("2.0")
    REGULAR_HOURS_ONLY = True

    print("Configuration:")
    print(f"  Date Range: {START_DATE.date()} to {END_DATE.date()}")
    print(f"  Symbols: 30 (focused subset)")
    print(f"  Initial Capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"  Risk per Trade: {RISK_PER_TRADE:.1%}")
    print(f"  Parallel Processing: Enabled (3 workers)")
    print()

    # Use a focused subset of 30 major symbols (no verification delay)
    # This is the optimal balance of breadth and speed
    symbols = [
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
        "AVGO", "PEP", "COST", "ADBE", "NFLX", "CMCSA", "CSCO", "INTC",
        "AMD", "PYPL", "QCOM", "TXN", "PYPL", "INTU", "AMAT", "MU",
        "ADI", "KLAC", "MRVL", "LRCX", "MCHP", "SNPS"
    ]

    print(f"✓ Using {len(symbols)} symbols (focused portfolio)\n")

    # Create portfolio configuration
    portfolio_config = PortfolioBacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        risk_per_trade_pct=RISK_PER_TRADE,
        max_positions=15,
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

    # Create and run portfolio engine
    engine = PortfolioBacktestEngine(
        config=portfolio_config,
        strategy=strategy,
    )

    print("Starting portfolio backtest (parallel processing enabled)...")
    print("Expected runtime: 2-3 hours\n")

    try:
        result = engine.run(
            symbols=symbols,
            interval=INTERVAL,
            start=START_DATE,
            end=END_DATE,
        )

        # Print summary
        print_summary(result)

        print("\n✓ Fast portfolio backtest completed successfully!\n")
        return 0

    except KeyboardInterrupt:
        print("\n\n⚠ Backtest interrupted by user")
        return 130

    except Exception as e:
        print(f"\n\n✗ ERROR: Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
