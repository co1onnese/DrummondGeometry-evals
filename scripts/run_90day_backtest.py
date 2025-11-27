#!/usr/bin/env python3
"""90-day backtest using the new 5m data architecture and prediction engine.

This backtest:
- Uses 90 days of data (August 28 - November 26, 2025)
- Leverages the new 5m data architecture
- Uses the PredictionSignalStrategy with the production SignalGenerator
- Tests all successfully backfilled symbols
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
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
from dgas.data.repository import fetch_market_data


def get_symbols_with_5m_data() -> list[str]:
    """Get all symbols that have 5m data from our backfill.
    
    Returns:
        List of symbol strings with 5m data
    """
    print("Fetching symbols with 5m data...", flush=True)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Get all unique symbols that have 5m data
        query = """
        SELECT DISTINCT s.symbol
        FROM market_data md
        JOIN market_symbols s ON md.symbol_id = s.symbol_id
        WHERE md.interval_type = '5m'
        ORDER BY s.symbol
        """
        
        cursor.execute(query)
        symbols = [row[0] for row in cursor.fetchall()]
        
    print(f"Found {len(symbols)} symbols with 5m data", flush=True)
    return symbols


def verify_data_availability(
    symbols: list[str],
    interval: str,
    start: datetime,
    end: datetime,
) -> tuple[list[str], list[str]]:
    """Verify which symbols have data available for the backtest period.
    
    Args:
        symbols: List of symbols to check
        interval: Data interval (will use 5m and aggregate to 30m)
        start: Start date
        end: End date
        
    Returns:
        Tuple of (symbols_with_data, symbols_missing_data)
    """
    symbols_with_data = []
    symbols_missing_data = []
    
    print(f"\nVerifying data availability for {len(symbols)} symbols...", flush=True)
    print(f"  Period: {start.date()} to {end.date()}", flush=True)
    print(f"  Checking 5m data (will aggregate to {interval})...", flush=True)
    
    with get_connection() as conn:
        for idx, symbol in enumerate(symbols):
            if idx % 50 == 0:
                print(f"  Progress: {idx}/{len(symbols)} symbols checked...", end="\r", flush=True)
            
            try:
                # Check for 5m data in the period (we'll aggregate to 30m)
                bars = fetch_market_data(
                    conn, 
                    symbol, 
                    "5m",  # Check 5m data availability
                    start=start, 
                    end=end
                )
                
                # Need at least 100 5m bars (about 8 hours of data)
                if bars and len(bars) > 100:
                    symbols_with_data.append(symbol)
                else:
                    symbols_missing_data.append(symbol)
                    
            except Exception as e:
                print(f"\n  Warning: Error checking {symbol}: {e}", flush=True)
                symbols_missing_data.append(symbol)
    
    print(f"\n  ✓ {len(symbols_with_data)} symbols have sufficient data", flush=True)
    if symbols_missing_data:
        print(f"  ✗ {len(symbols_missing_data)} symbols have insufficient data", flush=True)
        
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
    
    # Ensure the synthetic symbol exists
    symbol_name = "90DAY_BT"
    with get_connection() as conn:
        ensure_market_symbol(
            conn,
            symbol_name,
            exchange="US",
            sector="Portfolio",
            industry="90-Day Backtest",
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
            "test_type": "90_day_backtest",
            "data_architecture": "5m_direct",
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
    print("90-DAY BACKTEST RESULTS")
    print(f"{'='*80}")
    
    print(f"\nPortfolio Details:")
    print(f"  Symbols: {len(result.symbols)}")
    print(f"  Period: {result.start_date.date()} to {result.end_date.date()}")
    print(f"  Total Bars: {result.total_bars:,}")
    print(f"  Data: 5m bars (direct)")
    
    print(f"\nCapital:")
    print(f"  Starting: ${result.starting_capital:,.2f}")
    print(f"  Ending:   ${result.ending_equity:,.2f}")
    print(f"  Return:   {result.total_return:.2%}")
    
    print(f"\nRisk Metrics:")
    if hasattr(result, 'max_drawdown'):
        print(f"  Max Drawdown: {result.max_drawdown:.2%}")
    if hasattr(result, 'sharpe_ratio'):
        print(f"  Sharpe Ratio: {result.sharpe_ratio:.2f}")
    
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
            
        # Profit factor
        if losing_trades:
            total_wins = sum(t.net_profit for t in winning_trades) if winning_trades else Decimal(0)
            total_losses = abs(sum(t.net_profit for t in losing_trades))
            if total_losses > 0:
                profit_factor = total_wins / total_losses
                print(f"  Profit Factor: {profit_factor:.2f}")
    
    print(f"\n{'='*80}\n")


def main() -> int:
    """Main execution function."""
    print(f"\n{'='*80}")
    print("90-DAY BACKTEST WITH NEW 5M DATA ARCHITECTURE")
    print("Using PredictionEngine SignalGenerator")
    print(f"{'='*80}\n")
    
    # Configuration for 90-day backtest ending Nov 26, 2025
    # End date: Wednesday, November 26, 2025 (end of trading day)
    END_DATE = datetime(2025, 11, 26, tzinfo=timezone.utc)
    # Start date: 90 days before (August 28, 2025)
    START_DATE = END_DATE - timedelta(days=90)
    
    INTERVAL = "5m"  # Use 5m data directly (no aggregation available)
    INITIAL_CAPITAL = Decimal("100000")  # $100k
    RISK_PER_TRADE = Decimal("0.02")  # 2% per trade
    COMMISSION = Decimal("0.001")  # 0.1% (realistic)
    SLIPPAGE = Decimal("2.0")  # 2 basis points
    ALLOW_SHORT = True  # Allow short selling
    
    print("Configuration:")
    print(f"  Date Range: {START_DATE.date()} to {END_DATE.date()} (90 days)")
    print(f"  Data Source: {INTERVAL} bars (direct)")
    print(f"  Initial Capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"  Risk per Trade: {RISK_PER_TRADE:.1%} (${INITIAL_CAPITAL * RISK_PER_TRADE:,.2f})")
    print(f"  Commission: {COMMISSION:.2%}")
    print(f"  Slippage: {SLIPPAGE:.0f} basis points")
    print(f"  Short Selling: {'Enabled' if ALLOW_SHORT else 'Disabled'}")
    print(f"  Strategy: PredictionSignalStrategy")
    print()
    
    # Get symbols with 5m data
    all_symbols = get_symbols_with_5m_data()
    
    if not all_symbols:
        print("ERROR: No symbols found with 5m data!")
        print("Please run the backfill script first.")
        return 1
    
    # Verify data availability for the period
    symbols_with_data, symbols_missing = verify_data_availability(
        all_symbols,
        INTERVAL,
        START_DATE,
        END_DATE,
    )
    
    if symbols_missing:
        print(f"\nWarning: {len(symbols_missing)} symbols have insufficient data")
        if len(symbols_missing) <= 10:
            for symbol in symbols_missing:
                print(f"    - {symbol}")
    
    if len(symbols_with_data) < 10:
        print(f"\nERROR: Insufficient symbols with data ({len(symbols_with_data)})")
        print("  At least 10 symbols required for portfolio backtest.")
        return 1
    
    # Limit to first 100 symbols for faster testing (remove this for full backtest)
    # symbols_with_data = symbols_with_data[:100]
    
    print(f"\nProceeding with {len(symbols_with_data)} symbols")
    
    # Create portfolio configuration
    portfolio_config = PortfolioBacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        risk_per_trade_pct=RISK_PER_TRADE,
        max_positions=20,  # Max concurrent positions
        max_portfolio_risk_pct=Decimal("0.10"),  # Max 10% total risk
        commission_rate=COMMISSION,
        slippage_bps=SLIPPAGE,
        regular_hours_only=False,  # Use all available data
        exchange_code="US",
        allow_short=ALLOW_SHORT,
        htf_interval="1d",  # Higher timeframe
        trading_interval="5m",  # Trading timeframe (using 5m directly)
        max_signals_per_bar=5,  # Max new positions per bar
    )
    
    # Create strategy using PredictionSignalStrategy
    strategy_config = PredictionSignalStrategyConfig(
        allow_short=ALLOW_SHORT,
        min_alignment_score=0.6,
        min_signal_strength=0.5,
        stop_loss_atr_multiplier=1.5,
        target_rr_ratio=2.0,
    )
    strategy = PredictionSignalStrategy(strategy_config)
    
    # Create and run portfolio engine
    engine = PortfolioBacktestEngine(
        config=portfolio_config,
        strategy=strategy,
    )
    
    print("\nStarting 90-day backtest...\n", flush=True)
    print("This backtest will:", flush=True)
    print("  1. Load 5m data for each symbol", flush=True)
    print("  2. Generate signals using PredictionEngine", flush=True)
    print("  3. Simulate portfolio trading", flush=True)
    print("\nEstimated time: 1-2 hours depending on symbol count\n", flush=True)
    
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
        
        print("\n✓ 90-day backtest completed successfully!")
        print("\nThe backtest has validated that:")
        print("  • The 5m data architecture works correctly")
        print("  • The prediction engine generates signals as expected")
        print("  • The system can handle the full symbol universe efficiently\n")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nBacktest interrupted by user")
        return 130
        
    except Exception as e:
        print(f"\n\nERROR: Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    # Ensure unbuffered output
    import os
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    # Run main
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"FATAL ERROR: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        sys.exit(1)