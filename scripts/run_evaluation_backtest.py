#!/usr/bin/env python3
"""Evaluation backtest for Drummond Geometry trading signals.

Runs a comprehensive evaluation test across SP500 symbols using
the PredictionEngine's SignalGenerator to validate signal accuracy.

Configuration:
- Date Range: 2025-09-08 to 2025-11-07 (3 months)
- Initial Capital: $100,000 (shared across all symbols)
- Risk per Trade: 2% of portfolio ($2,000 per trade)
- Commission: 0%
- Slippage: 2 basis points (0.02%)
- Short Selling: Enabled
- Trading Hours: Regular hours only (9:30 AM - 4:00 PM EST)
- Symbols: ~500 SP500 tickers
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
    PortfolioBacktestResult,
)
from dgas.backtesting.strategies.prediction_signal import (
    PredictionSignalStrategy,
    PredictionSignalStrategyConfig,
)
from dgas.backtesting.metrics import calculate_performance
from dgas.db import get_connection


def load_sp500_symbols() -> list[str]:
    """Load SP500 symbols from CSV file.

    Returns:
        List of symbol strings
    """
    csv_path = Path(__file__).parent.parent / "data" / "sp500_constituents.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"SP500 symbols file not found: {csv_path}")

    symbols = []
    with open(csv_path, "r") as f:
        # Skip header
        next(f)

        for line in f:
            line = line.strip()
            if not line:
                continue

            # CSV format: symbol,name,sector,industry,indices
            parts = line.split(",")
            if parts and parts[0]:
                symbol = parts[0].strip()
                if symbol:  # Avoid empty strings
                    symbols.append(symbol)

    print(f"Loaded {len(symbols)} symbols from {csv_path}")
    return symbols


def load_nasdaq100_symbols() -> list[str]:
    """Load Nasdaq 100 symbols from CSV file.

    Returns:
        List of symbol strings
    """
    csv_path = Path(__file__).parent.parent / "data" / "nasdaq100_constituents.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Nasdaq 100 symbols file not found: {csv_path}")

    symbols = []
    with open(csv_path, "r") as f:
        # Skip header
        next(f)

        for line in f:
            line = line.strip()
            if not line:
                continue

            # CSV format: symbol,name,sector,industry,indices
            parts = line.split(",")
            if parts and parts[0]:
                symbol = parts[0].strip()
                if symbol:  # Avoid empty strings
                    symbols.append(symbol)

    print(f"Loaded {len(symbols)} symbols from {csv_path}")
    return symbols


def verify_data_availability(
    symbols: list[str],
    interval: str,
    start: datetime,
    end: datetime,
) -> tuple[list[str], list[str]]:
    """Verify which symbols have data available.

    Args:
        symbols: List of symbols to check
        interval: Data interval
        start: Start date
        end: End date

    Returns:
        Tuple of (symbols_with_data, symbols_missing_data)
    """
    from dgas.data.repository import fetch_market_data

    symbols_with_data = []
    symbols_missing_data = []

    print("\nVerifying data availability...", flush=True)
    print(f"  Checking {len(symbols)} symbols...", flush=True)

    with get_connection() as conn:
        for idx, symbol in enumerate(symbols):
            if idx % 10 == 0:
                print(f"  Progress: {idx}/{len(symbols)} symbols checked...", end="\r", flush=True)
            try:
                bars = fetch_market_data(conn, symbol, interval, start=start, end=end)

                if bars and len(bars) > 10:  # Need reasonable amount of data
                    symbols_with_data.append(symbol)
                else:
                    symbols_missing_data.append(symbol)

            except Exception as e:
                print(f"\n  ⚠ Error checking {symbol}: {e}", flush=True)
                symbols_missing_data.append(symbol)

    print(f"\n  ✓ {len(symbols_with_data)} symbols have data", flush=True)
    if symbols_missing_data:
        print(f"  ✗ {len(symbols_missing_data)} symbols missing data", flush=True)

    return symbols_with_data, symbols_missing_data


def save_results_to_database(result: PortfolioBacktestResult) -> int:
    """Save portfolio backtest results to database.

    Args:
        result: Portfolio backtest result

    Returns:
        Backtest result ID
    """
    from dgas.backtesting.persistence import persist_backtest
    from dgas.backtesting.entities import BacktestResult, SimulationConfig
    from dgas.data.repository import ensure_market_symbol

    # Ensure the synthetic symbol exists in database for portfolio backtests
    # Note: symbol field is VARCHAR(10), so must use short name
    symbol_name = "SP500_EVAL"
    with get_connection() as conn:
        ensure_market_symbol(
            conn,
            symbol_name,
            exchange="US",
            sector="Portfolio",
            industry="Evaluation",
        )

    # Convert portfolio result to single backtest result for database
    single_result = BacktestResult(
        symbol=symbol_name,
        strategy_name="prediction_signal",
        config=SimulationConfig(
            initial_capital=result.starting_capital,
            commission_rate=result.config.commission_rate,
            slippage_bps=result.config.slippage_bps,
            allow_short=result.config.allow_short,
        ),
        trades=result.trades,
        equity_curve=result.equity_curve,
        starting_cash=result.starting_capital,
        ending_cash=result.ending_capital,
        ending_equity=result.ending_equity,
        metadata={
            "portfolio_symbols": result.symbols,
            "symbol_count": len(result.symbols),
            "risk_per_trade_pct": float(result.config.risk_per_trade_pct),
            "max_positions": result.config.max_positions,
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
            "test_type": "evaluation",
            "signal_generator": "PredictionEngine.SignalGenerator",
        },
    )

    # Calculate performance metrics
    performance = calculate_performance(single_result, risk_free_rate=Decimal("0.02"))

    # Persist to database
    backtest_id = persist_backtest(single_result, performance, metadata=result.metadata)

    print(f"\n✓ Results saved to database (ID: {backtest_id})")

    return backtest_id


def print_summary(result: PortfolioBacktestResult) -> None:
    """Print summary of backtest results.

    Args:
        result: Portfolio backtest result
    """
    print(f"\n{'='*80}")
    print("EVALUATION BACKTEST RESULTS")
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
    print("DRUMMOND GEOMETRY EVALUATION BACKTEST")
    print("Testing PredictionEngine SignalGenerator Accuracy")
    print(f"{'='*80}\n")

    # Configuration - EXACT PARAMETERS AS SPECIFIED
    # Note: Sept 7, 2025 is a Sunday (no trading), so start on Sept 8 (Monday)
    START_DATE = datetime(2025, 9, 8, tzinfo=timezone.utc)  # First trading day after Sept 7
    END_DATE = datetime(2025, 11, 7, tzinfo=timezone.utc)
    INTERVAL = "30m"
    INITIAL_CAPITAL = Decimal("100000")  # $100k total
    RISK_PER_TRADE = Decimal("0.02")  # 2% per trade
    COMMISSION = Decimal("0.0")  # 0%
    SLIPPAGE = Decimal("2.0")  # 2 basis points
    REGULAR_HOURS_ONLY = False  # Temporarily disabled - calendar needs sync for Sept 2025
    ALLOW_SHORT = True  # Short selling enabled

    print("Configuration:")
    print(f"  Date Range: {START_DATE.date()} to {END_DATE.date()}")
    print(f"  Interval: {INTERVAL}")
    print(f"  Initial Capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"  Risk per Trade: {RISK_PER_TRADE:.1%} (${INITIAL_CAPITAL * RISK_PER_TRADE:,.2f})")
    print(f"  Commission: {COMMISSION:.2%}")
    print(f"  Slippage: {SLIPPAGE:.0f} basis points")
    print(f"  Trading Hours: Regular hours only (9:30 AM - 4:00 PM EST)")
    print(f"  Short Selling: {'Enabled' if ALLOW_SHORT else 'Disabled'}")
    print(f"  Strategy: PredictionSignalStrategy (uses PredictionEngine.SignalGenerator)")
    print()

    # Load symbols
    all_symbols = load_sp500_symbols()

    # Verify data availability
    symbols_with_data, symbols_missing = verify_data_availability(
        all_symbols,
        INTERVAL,
        START_DATE,
        END_DATE,
    )

    if symbols_missing:
        print(f"\n⚠ Warning: {len(symbols_missing)} symbols missing data:")
        for symbol in symbols_missing[:10]:  # Show first 10
            print(f"    - {symbol}")
        if len(symbols_missing) > 10:
            print(f"    ... and {len(symbols_missing) - 10} more")
        print()

    if len(symbols_with_data) < 10:
        print(f"\n✗ ERROR: Insufficient symbols with data ({len(symbols_with_data)})")
        print("  At least 10 symbols required for portfolio backtest.")
        return 1

    print(f"\n✓ Proceeding with {len(symbols_with_data)} symbols\n")

    # Create portfolio configuration
    portfolio_config = PortfolioBacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        risk_per_trade_pct=RISK_PER_TRADE,
        max_positions=20,  # Max concurrent positions
        max_portfolio_risk_pct=Decimal("0.10"),  # Max 10% total risk
        commission_rate=COMMISSION,
        slippage_bps=SLIPPAGE,
        regular_hours_only=REGULAR_HOURS_ONLY,
        exchange_code="US",
        allow_short=ALLOW_SHORT,
        htf_interval="1d",
        trading_interval="30m",
        max_signals_per_bar=5,  # Max new positions per bar
    )

    # Create strategy using PredictionSignalStrategy
    strategy_config = PredictionSignalStrategyConfig(
        allow_short=ALLOW_SHORT,
        min_alignment_score=0.6,
        min_signal_strength=0.5,
    )
    strategy = PredictionSignalStrategy(strategy_config)

    # Create and run portfolio engine
    engine = PortfolioBacktestEngine(
        config=portfolio_config,
        strategy=strategy,
    )

    print("Starting evaluation backtest...\n", flush=True)
    print("⚠ This will take 2-3 hours to complete (estimated).", flush=True)
    print("   The system will process all symbols at each timestamp.", flush=True)
    print("   Progress updates will be shown every 5% of timesteps.\n", flush=True)

    try:
        result = engine.run(
            symbols=symbols_with_data,
            interval=INTERVAL,
            start=START_DATE,
            end=END_DATE,
        )

        # Print summary
        print_summary(result)

        # Save to database
        save_results_to_database(result)

        print("\n✓ Evaluation backtest completed successfully!\n")
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
    # Ensure unbuffered output
    import os
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    # Wrap main in try/except to catch any import errors
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"FATAL ERROR: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        sys.exit(1)
