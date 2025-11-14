#!/usr/bin/env python3
"""Evaluation backtest for Nov 6-13, 2025.

Runs a comprehensive evaluation test across all active symbols using
the PredictionEngine's SignalGenerator to validate signal accuracy.

Configuration:
- Date Range: 2025-11-06 to 2025-11-13 (1 week)
- Initial Capital: $100,000 (shared across all symbols)
- Risk per Trade: 2% of portfolio ($2,000 per trade)
- Commission: 0%
- Slippage: 2 basis points (0.02%)
- Short Selling: Enabled
- Trading Hours: Regular hours only (9:30 AM - 4:00 PM EST)
- Symbols: All 518 active symbols from database
"""

from __future__ import annotations

import json
import os
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
from dgas.data.repository import fetch_market_data, get_latest_timestamp, ensure_market_symbol


def cleanup_old_evaluations() -> None:
    """Remove old evaluation backtest results from database."""
    print("\nCleaning up old evaluation backtest results...", flush=True)
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Find old evaluation backtest IDs by joining with market_symbols
            # to match by symbol name
            cur.execute("""
                SELECT br.backtest_id 
                FROM backtest_results br
                JOIN market_symbols ms ON br.symbol_id = ms.symbol_id
                WHERE ms.symbol IN ('SP500_EVAL', 'EVAL_NOV6', 'SP500_EVAL_NOV6')
            """)
            old_ids = [row[0] for row in cur.fetchall()]
            
            if old_ids:
                # Delete trades first (foreign key constraint)
                cur.execute("""
                    DELETE FROM backtest_trades 
                    WHERE backtest_id = ANY(%s)
                """, (old_ids,))
                
                # Delete backtest results
                cur.execute("""
                    DELETE FROM backtest_results 
                    WHERE backtest_id = ANY(%s)
                """, (old_ids,))
                
                conn.commit()
                print(f"✓ Cleaned up {len(old_ids)} old evaluation backtests", flush=True)
            else:
                print("✓ No old evaluation backtests found", flush=True)


def get_all_active_symbols() -> list[str]:
    """Get all active symbols from database.
    
    Returns:
        List of symbol strings
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            symbols = [row[0] for row in cur.fetchall()]
    
    print(f"Loaded {len(symbols)} active symbols from database")
    return symbols


def verify_data_availability(
    symbols: list[str],
    interval: str,
    start: datetime,
    end: datetime,
    min_bars: int = 10,
) -> tuple[list[str], list[str]]:
    """Verify which symbols have data available for the date range.
    
    Args:
        symbols: List of symbols to check
        interval: Data interval (e.g., "30m", "1d")
        start: Start date
        end: End date
        min_bars: Minimum number of bars required
        
    Returns:
        Tuple of (symbols_with_data, symbols_missing_data)
    """
    symbols_with_data = []
    symbols_missing_data = []
    
    print(f"\nVerifying {interval} data availability...", flush=True)
    print(f"  Checking {len(symbols)} symbols for {start.date()} to {end.date()}...", flush=True)
    
    with get_connection() as conn:
        for idx, symbol in enumerate(symbols):
            if idx % 50 == 0:
                print(f"  Progress: {idx}/{len(symbols)} symbols checked...", end="\r", flush=True)
            try:
                symbol_id = ensure_market_symbol(conn, symbol, "US")
                bars = fetch_market_data(conn, symbol, interval, start=start, end=end)
                
                # Check that we have data and it meets minimum bar requirement
                if bars and len(bars) >= min_bars:
                    # Also verify that data actually exists in the requested range
                    # (not just before or after)
                    bars_in_range = [b for b in bars if start <= b.timestamp <= end]
                    if len(bars_in_range) >= min_bars:
                        symbols_with_data.append(symbol)
                    else:
                        symbols_missing_data.append(symbol)
                else:
                    symbols_missing_data.append(symbol)
                    
            except Exception as e:
                print(f"\n  ⚠ Error checking {symbol}: {e}", flush=True)
                symbols_missing_data.append(symbol)
    
    print(f"\n  ✓ {len(symbols_with_data)} symbols have {interval} data", flush=True)
    if symbols_missing_data:
        print(f"  ✗ {len(symbols_missing_data)} symbols missing {interval} data", flush=True)
    
    return symbols_with_data, symbols_missing_data


def validate_data_for_backtest(
    symbols: list[str],
    start: datetime,
    end: datetime,
) -> tuple[list[str], list[str], list[str]]:
    """Validate data availability for both 30m and 1d intervals.
    
    Args:
        symbols: List of symbols to validate
        start: Start date for backtest (Nov 6, 2025)
        end: End date for backtest (Nov 13, 2025)
        
    Returns:
        Tuple of (symbols_with_complete_data, symbols_missing_30m, symbols_missing_1d)
    """
    print("\n" + "="*80)
    print("DATA VALIDATION")
    print("="*80)
    
    # First, check that data exists in the actual trading period (Nov 6-13)
    # This is what the backtest engine will request
    print("\nStep 1: Checking data in trading period (Nov 6-13)...")
    symbols_with_trading_data_30m, symbols_missing_trading_30m = verify_data_availability(
        symbols, "30m", start, end, min_bars=10
    )
    
    # Then check for lookback data (Nov 1-5) for indicator calculation
    print("\nStep 2: Checking lookback data (Nov 1-5) for indicator calculation...")
    lookback_start_30m = datetime(2025, 11, 1, tzinfo=timezone.utc)
    lookback_end_30m = datetime(2025, 11, 5, 23, 59, 59, tzinfo=timezone.utc)
    symbols_with_lookback_30m, symbols_missing_lookback_30m = verify_data_availability(
        symbols_with_trading_data_30m, "30m", lookback_start_30m, lookback_end_30m, min_bars=5
    )
    
    # Symbols with complete 30m data (both trading period and lookback)
    symbols_with_30m = symbols_with_lookback_30m
    symbols_missing_30m = list(set(symbols) - set(symbols_with_30m))
    
    # Check 1d data:
    # - Need data from Oct 1 for HTF trend analysis (lookback)
    # - Need data through Nov 13 for HTF updates during trading
    # - Check full range: Oct 1 - Nov 13
    print("\nStep 3: Checking 1d data (Oct 1 - Nov 13) for HTF analysis...")
    lookback_start_1d = datetime(2025, 10, 1, tzinfo=timezone.utc)
    # Use min_bars=10 to ensure we have enough daily bars for HTF analysis
    symbols_with_1d, symbols_missing_1d = verify_data_availability(
        symbols, "1d", lookback_start_1d, end, min_bars=10
    )
    
    # Find symbols with both intervals
    symbols_with_complete_data = [
        s for s in symbols_with_30m if s in symbols_with_1d
    ]
    
    # Find symbols missing either interval
    all_missing_30m = set(symbols_missing_30m)
    all_missing_1d = set(symbols_missing_1d)
    missing_either = list(all_missing_30m | all_missing_1d)
    
    print(f"\n{'='*80}")
    print("VALIDATION SUMMARY")
    print(f"{'='*80}")
    print(f"  Total symbols checked: {len(symbols)}")
    print(f"  Symbols with complete data (30m + 1d): {len(symbols_with_complete_data)}")
    print(f"  Symbols missing 30m data: {len(symbols_missing_30m)}")
    print(f"  Symbols missing 1d data: {len(symbols_missing_1d)}")
    print(f"  Symbols missing either interval: {len(missing_either)}")
    
    if missing_either:
        print(f"\n⚠ Symbols with missing data (showing first 20):")
        for symbol in missing_either[:20]:
            missing_intervals = []
            if symbol in all_missing_30m:
                missing_intervals.append("30m")
            if symbol in all_missing_1d:
                missing_intervals.append("1d")
            print(f"    - {symbol}: missing {', '.join(missing_intervals)}")
        if len(missing_either) > 20:
            print(f"    ... and {len(missing_either) - 20} more")
    
    print(f"{'='*80}\n")
    
    return symbols_with_complete_data, symbols_missing_30m, symbols_missing_1d


def save_results_to_database(result: PortfolioBacktestResult) -> int:
    """Save portfolio backtest results to database.
    
    Args:
        result: Portfolio backtest result
        
    Returns:
        Backtest result ID
    """
    from dgas.backtesting.persistence import persist_backtest
    from dgas.backtesting.entities import BacktestResult, SimulationConfig
    
    # Ensure the synthetic symbol exists in database for portfolio backtests
    # Note: symbol field is VARCHAR(10), so must use short name
    symbol_name = "EVAL_NOV6"
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
            # Include signal accuracy metrics from metadata
            **result.metadata.get("signal_accuracy", {}),
        },
    )
    
    # Calculate performance metrics
    performance = calculate_performance(single_result, risk_free_rate=Decimal("0.02"))
    
    # Persist to database
    backtest_id = persist_backtest(single_result, performance, metadata=result.metadata)
    
    print(f"\n✓ Results saved to database (ID: {backtest_id})")
    
    return backtest_id


def write_results_to_file(
    result: PortfolioBacktestResult,
    performance: any,
    backtest_id: int | None,
) -> Path:
    """Write comprehensive backtest results to Markdown file.
    
    Args:
        result: Portfolio backtest result
        performance: Performance metrics from calculate_performance
        backtest_id: Database backtest ID (if saved)
        
    Returns:
        Path to written file
    """
    # Create reports directory if it doesn't exist
    reports_dir = Path(__file__).parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    output_file = reports_dir / "nov6_nov13_backtest_results.md"
    
    # Extract signal accuracy metrics from metadata
    signal_accuracy = result.metadata.get("signal_accuracy", {})
    
    with open(output_file, "w") as f:
        f.write("# Backtest Results: Nov 6-13, 2025\n\n")
        f.write("## Executive Summary\n\n")
        f.write(f"- **Date Range**: {result.start_date.date()} to {result.end_date.date()}\n")
        f.write(f"- **Symbols Traded**: {len(result.symbols)}\n")
        f.write(f"- **Total Bars Processed**: {result.total_bars:,}\n")
        f.write(f"- **Initial Capital**: ${result.starting_capital:,.2f}\n")
        f.write(f"- **Ending Equity**: ${result.ending_equity:,.2f}\n")
        f.write(f"- **Total Return**: {result.total_return:.2%}\n")
        f.write(f"- **Total Trades**: {result.trade_count}\n")
        if backtest_id:
            f.write(f"- **Database ID**: {backtest_id}\n")
        f.write("\n")
        
        # Configuration
        f.write("## Configuration\n\n")
        f.write(f"- **Initial Capital**: ${result.config.initial_capital:,.2f}\n")
        f.write(f"- **Risk per Trade**: {result.config.risk_per_trade_pct:.1%}\n")
        f.write(f"- **Max Positions**: {result.config.max_positions}\n")
        f.write(f"- **Max Portfolio Risk**: {result.config.max_portfolio_risk_pct:.1%}\n")
        f.write(f"- **Commission Rate**: {result.config.commission_rate:.2%}\n")
        f.write(f"- **Slippage**: {result.config.slippage_bps:.0f} basis points\n")
        f.write(f"- **Short Selling**: {'Enabled' if result.config.allow_short else 'Disabled'}\n")
        f.write(f"- **Regular Hours Only**: {'Yes' if result.config.regular_hours_only else 'No'}\n")
        f.write(f"- **HTF Interval**: {result.config.htf_interval}\n")
        f.write(f"- **Trading Interval**: {result.config.trading_interval}\n")
        f.write("\n")
        
        # Performance Metrics
        f.write("## Performance Metrics\n\n")
        f.write(f"- **Total Return**: {performance.total_return:.2%}\n")
        annualized_str = f"{performance.annualized_return:.2%}" if performance.annualized_return is not None else "N/A"
        sharpe_str = f"{performance.sharpe_ratio:.2f}" if performance.sharpe_ratio is not None else "N/A"
        sortino_str = f"{performance.sortino_ratio:.2f}" if performance.sortino_ratio is not None else "N/A"
        volatility_str = f"{performance.volatility:.2%}" if performance.volatility is not None else "N/A"
        f.write(f"- **Annualized Return**: {annualized_str}\n")
        f.write(f"- **Sharpe Ratio**: {sharpe_str}\n")
        f.write(f"- **Sortino Ratio**: {sortino_str}\n")
        f.write(f"- **Max Drawdown**: {performance.max_drawdown:.2%}\n")
        f.write(f"- **Volatility**: {volatility_str}\n")
        f.write(f"- **Net Profit**: ${performance.net_profit:,.2f}\n")
        f.write("\n")
        
        # Trade Statistics
        f.write("## Trade Statistics\n\n")
        f.write(f"- **Total Trades**: {performance.total_trades}\n")
        f.write(f"- **Winning Trades**: {performance.winning_trades}\n")
        f.write(f"- **Losing Trades**: {performance.losing_trades}\n")
        win_rate_str = f"{performance.win_rate:.1%}" if performance.win_rate is not None else "N/A"
        f.write(f"- **Win Rate**: {win_rate_str}\n")
        if performance.avg_win is not None:
            f.write(f"- **Average Win**: ${performance.avg_win:,.2f}\n")
        if performance.avg_loss is not None:
            f.write(f"- **Average Loss**: ${performance.avg_loss:,.2f}\n")
        if performance.profit_factor is not None:
            f.write(f"- **Profit Factor**: {performance.profit_factor:.2f}\n")
        f.write("\n")
        
        # Signal Accuracy Metrics
        if signal_accuracy:
            f.write("## Signal Accuracy Metrics\n\n")
            f.write(f"- **Total Signals Generated**: {signal_accuracy.get('total_signals', 0)}\n")
            f.write(f"- **Executed Signals**: {signal_accuracy.get('executed_signals', 0)}\n")
            f.write(f"- **Winning Signals**: {signal_accuracy.get('winning_signals', 0)}\n")
            f.write(f"- **Losing Signals**: {signal_accuracy.get('losing_signals', 0)}\n")
            win_rate_val = signal_accuracy.get('win_rate')
            win_rate_str = f"{win_rate_val:.1%}" if win_rate_val is not None else "N/A"
            f.write(f"- **Win Rate**: {win_rate_str}\n")
            
            avg_conf_win = signal_accuracy.get('avg_confidence_winning')
            avg_conf_win_str = f"{avg_conf_win:.1%}" if avg_conf_win is not None else "N/A"
            f.write(f"- **Avg Confidence (Winning)**: {avg_conf_win_str}\n")
            
            avg_conf_lose = signal_accuracy.get('avg_confidence_losing')
            avg_conf_lose_str = f"{avg_conf_lose:.1%}" if avg_conf_lose is not None else "N/A"
            f.write(f"- **Avg Confidence (Losing)**: {avg_conf_lose_str}\n")
            
            avg_conf_all = signal_accuracy.get('avg_confidence_all')
            avg_conf_all_str = f"{avg_conf_all:.1%}" if avg_conf_all is not None else "N/A"
            f.write(f"- **Avg Confidence (All)**: {avg_conf_all_str}\n")
            f.write("\n")
            
            # Signals by type
            signals_by_type = signal_accuracy.get('signals_by_type', {})
            if signals_by_type:
                f.write("### Signals by Type\n\n")
                for signal_type, count in signals_by_type.items():
                    f.write(f"- **{signal_type}**: {count}\n")
                f.write("\n")
            
            # Win rate by type
            win_rate_by_type = signal_accuracy.get('win_rate_by_type', {})
            if win_rate_by_type:
                f.write("### Win Rate by Signal Type\n\n")
                for signal_type, win_rate in win_rate_by_type.items():
                    win_rate_str = f"{win_rate:.1%}" if win_rate is not None else "N/A"
                    f.write(f"- **{signal_type}**: {win_rate_str}\n")
                f.write("\n")
            
            # Win rate by confidence bucket
            win_rate_by_confidence = signal_accuracy.get('win_rate_by_confidence_bucket', {})
            if win_rate_by_confidence:
                f.write("### Win Rate by Confidence Bucket\n\n")
                for bucket, win_rate in win_rate_by_confidence.items():
                    win_rate_str = f"{win_rate:.1%}" if win_rate is not None else "N/A"
                    f.write(f"- **{bucket}**: {win_rate_str}\n")
                f.write("\n")
        
        # Data Summary
        data_summary = result.metadata.get("data_summary", {})
        if data_summary:
            f.write("## Data Summary\n\n")
            f.write(f"- **Total Symbols**: {data_summary.get('total_symbols', 'N/A')}\n")
            f.write(f"- **Symbols with Data**: {data_summary.get('symbols_with_data', 'N/A')}\n")
            f.write("\n")
        
        # Symbol List
        f.write("## Symbols Traded\n\n")
        f.write(f"Total: {len(result.symbols)} symbols\n\n")
        # Write symbols in columns for readability
        symbols_per_line = 10
        for i in range(0, len(result.symbols), symbols_per_line):
            line_symbols = result.symbols[i:i+symbols_per_line]
            f.write(", ".join(line_symbols) + "\n")
        f.write("\n")
        
        # Footer
        f.write("---\n\n")
        f.write(f"*Report generated on {datetime.now(timezone.utc).isoformat()}*\n")
    
    print(f"✓ Results written to {output_file}")
    return output_file


def print_summary(result: PortfolioBacktestResult, performance: any) -> None:
    """Print summary of backtest results.
    
    Args:
        result: Portfolio backtest result
        performance: Performance metrics
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
    
    print(f"\nPerformance Metrics:")
    sharpe_str = f"{performance.sharpe_ratio:.2f}" if performance.sharpe_ratio is not None else "N/A"
    sortino_str = f"{performance.sortino_ratio:.2f}" if performance.sortino_ratio is not None else "N/A"
    print(f"  Sharpe Ratio: {sharpe_str}")
    print(f"  Sortino Ratio: {sortino_str}")
    print(f"  Max Drawdown: {performance.max_drawdown:.2%}")
    
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
    
    # Signal accuracy summary
    signal_accuracy = result.metadata.get("signal_accuracy", {})
    if signal_accuracy:
        print(f"\nSignal Accuracy:")
        print(f"  Total Signals: {signal_accuracy.get('total_signals', 0)}")
        print(f"  Executed Signals: {signal_accuracy.get('executed_signals', 0)}")
        win_rate_val = signal_accuracy.get('win_rate')
        win_rate_str = f"{win_rate_val:.1%}" if win_rate_val is not None else "N/A"
        print(f"  Win Rate: {win_rate_str}")
    
    print(f"\n{'='*80}\n")


def main() -> int:
    """Main execution function."""
    print(f"\n{'='*80}")
    print("DRUMMOND GEOMETRY EVALUATION BACKTEST")
    print("Nov 6-13, 2025 - Testing PredictionEngine SignalGenerator Accuracy")
    print(f"{'='*80}\n")
    
    # Configuration
    START_DATE = datetime(2025, 11, 6, tzinfo=timezone.utc)
    END_DATE = datetime(2025, 11, 13, 23, 59, 59, tzinfo=timezone.utc)  # End of Nov 13
    INTERVAL = "30m"
    INITIAL_CAPITAL = Decimal("100000")  # $100k total
    RISK_PER_TRADE = Decimal("0.02")  # 2% per trade
    COMMISSION = Decimal("0.0")  # 0%
    SLIPPAGE = Decimal("2.0")  # 2 basis points
    REGULAR_HOURS_ONLY = True  # Enabled - regular trading hours only
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
    
    # Cleanup old evaluations
    cleanup_old_evaluations()
    
    # Load all active symbols from database
    all_symbols = get_all_active_symbols()
    
    if not all_symbols:
        print("\n✗ ERROR: No active symbols found in database")
        return 1
    
    # Validate data availability
    symbols_with_data, symbols_missing_30m, symbols_missing_1d = validate_data_for_backtest(
        all_symbols,
        START_DATE,
        END_DATE,
    )
    
    if len(symbols_with_data) < 10:
        print(f"\n✗ ERROR: Insufficient symbols with complete data ({len(symbols_with_data)})")
        print("  At least 10 symbols required for portfolio backtest.")
        print("  Please backfill missing data before running backtest.")
        return 1
    
    print(f"\n✓ Proceeding with {len(symbols_with_data)} symbols with complete data\n")
    
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
    print("⚠ This will take 30-60 minutes to complete (estimated).", flush=True)
    print("   The system will process all symbols at each timestamp.", flush=True)
    print("   Progress updates will be shown periodically.\n", flush=True)
    
    try:
        result = engine.run(
            symbols=symbols_with_data,
            interval=INTERVAL,
            start=START_DATE,
            end=END_DATE,
        )
        
        # Calculate performance metrics
        from dgas.backtesting.entities import BacktestResult, SimulationConfig
        single_result = BacktestResult(
            symbol="EVAL_NOV6",
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
        )
        performance = calculate_performance(single_result, risk_free_rate=Decimal("0.02"))
        
        # Print summary
        print_summary(result, performance)
        
        # Save to database
        backtest_id = save_results_to_database(result)
        
        # Write results to file
        write_results_to_file(result, performance, backtest_id)
        
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
