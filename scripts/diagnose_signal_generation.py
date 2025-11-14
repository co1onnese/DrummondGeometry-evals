#!/usr/bin/env python3
"""
Diagnose why signals aren't being generated in the backtest.

This script will:
1. Test signal generation with real data from the backtest period
2. Check if indicators are being calculated correctly
3. Verify the strategy is receiving the right data
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.data.repository import fetch_market_data
from dgas.backtesting.portfolio_indicator_calculator import PortfolioIndicatorCalculator
from dgas.backtesting.strategies.prediction_signal import PredictionSignalStrategy, PredictionSignalStrategyConfig
from dgas.backtesting.strategies.base import StrategyContext
from dgas.backtesting.portfolio_data_loader import PortfolioDataLoader

def test_signal_generation():
    """Test signal generation for a few symbols."""
    print("="*80)
    print("SIGNAL GENERATION DIAGNOSTIC")
    print("="*80)
    
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY']
    start = datetime(2025, 11, 6, tzinfo=timezone.utc)
    end = datetime(2025, 11, 13, 23, 59, 59, tzinfo=timezone.utc)
    
    # Load data
    loader = PortfolioDataLoader(regular_hours_only=True, exchange_code='US')
    bundles = loader._load_portfolio_data_batch(symbols, '30m', start, end)
    
    print(f"\nLoaded data for {len(bundles)} symbols")
    
    # Create indicator calculator
    indicator_calc = PortfolioIndicatorCalculator(htf_interval='1d', trading_interval='30m')
    
    # Pre-load HTF data
    indicator_calc.preload_htf_data_for_portfolio(symbols, start, end)
    
    # Create strategy
    strategy_config = PredictionSignalStrategyConfig(
        allow_short=True,
        min_alignment_score=0.6,
        min_signal_strength=0.5,
    )
    strategy = PredictionSignalStrategy(strategy_config)
    
    # Test signal generation for each symbol
    total_signals = 0
    for symbol, bundle in bundles.items():
        if not bundle.bars:
            continue
        
        # Use a bar from the middle of the period
        test_bar_idx = len(bundle.bars) // 2
        test_bar = bundle.bars[test_bar_idx]
        history = bundle.bars[:test_bar_idx + 1]
        
        print(f"\n{symbol}:")
        print(f"  Testing with bar at {test_bar.timestamp}")
        print(f"  History: {len(history)} bars")
        
        try:
            # Calculate indicators
            indicators = indicator_calc.calculate_indicators(
                symbol=symbol,
                current_bar=test_bar,
                historical_bars=history,
            )
            
            print(f"  Indicators calculated: {list(indicators.keys())}")
            
            # Check what we have
            htf_data = indicators.get('htf_data')
            trading_tf_data = indicators.get('trading_tf_data')
            analysis = indicators.get('analysis')
            
            if htf_data is None:
                print(f"  ✗ Missing htf_data")
            else:
                print(f"  ✓ htf_data: {type(htf_data).__name__}, {len(htf_data.bars)} bars")
            
            if trading_tf_data is None:
                print(f"  ✗ Missing trading_tf_data")
            else:
                print(f"  ✓ trading_tf_data: {type(trading_tf_data).__name__}, {len(trading_tf_data.bars)} bars")
            
            if analysis is None:
                print(f"  ✗ Missing analysis")
            else:
                print(f"  ✓ analysis: {type(analysis).__name__}")
                print(f"    Alignment score: {float(analysis.alignment.alignment_score):.3f}")
                print(f"    Signal strength: {float(analysis.signal_strength):.3f}")
                print(f"    Trade permitted: {analysis.alignment.trade_permitted}")
                print(f"    Confluence zones: {len(analysis.confluence_zones)}")
                if analysis.confluence_zones:
                    print(f"    Top zone weight: {float(analysis.confluence_zones[0].weighted_strength):.2f}")
            
            # Create context and test strategy
            context = StrategyContext(
                symbol=symbol,
                bar=test_bar,
                position=None,
                cash=100000,
                equity=100000,
                indicators=indicators,
                history=history,
            )
            
            signals = list(strategy.on_bar(context))
            print(f"  Signals generated: {len(signals)}")
            total_signals += len(signals)
            
            if signals:
                for sig in signals:
                    print(f"    - {sig.action.value}")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*80}")
    print(f"Total signals generated: {total_signals}")
    print(f"{'='*80}")

if __name__ == "__main__":
    test_signal_generation()
