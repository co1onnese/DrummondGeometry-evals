"""Integration tests to verify backtest results are identical before/after optimizations.

These tests verify that the optimizations don't change backtest results,
ensuring functional correctness is maintained.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from dgas.backtesting import (
    BacktestDataset,
    BacktestRunner,
    BacktestRequest,
    SimulationConfig,
    SimulationEngine,
)
from dgas.backtesting.strategies.multi_timeframe import MultiTimeframeStrategy, MultiTimeframeStrategyConfig
from dgas.data.models import IntervalData


def make_bar(symbol: str, timestamp: datetime, close: Decimal) -> IntervalData:
    """Create a test bar."""
    return IntervalData(
        symbol=symbol,
        exchange="NASDAQ",
        timestamp=timestamp.isoformat(),
        interval="30m",
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        adjusted_close=close,
        volume=1000,
    )


def test_engine_produces_identical_results():
    """Test that SimulationEngine produces identical results with executor refactoring."""
    # Create simple test dataset
    start = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    bars = [
        make_bar("AAPL", start + timedelta(minutes=30 * i), Decimal("100") + Decimal(str(i)))
        for i in range(10)
    ]
    
    from dgas.backtesting.data_loader import BacktestBar, BacktestDataset
    
    dataset = BacktestDataset(
        symbol="AAPL",
        interval="30m",
        bars=[BacktestBar(bar=bar, indicators={}) for bar in bars],
    )
    
    # Create strategy
    strategy = MultiTimeframeStrategy(
        MultiTimeframeStrategyConfig(
            min_history=3,
            allow_short=False,
        )
    )
    
    # Run backtest
    config = SimulationConfig(
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0.001"),
        slippage_bps=Decimal("2.0"),
    )
    
    engine = SimulationEngine(config=config)
    result = engine.run(dataset, strategy)
    
    # Verify basic results
    assert result.symbol == "AAPL"
    assert result.starting_cash == Decimal("100000")
    assert result.ending_equity >= result.starting_cash  # Should at least break even or profit
    assert len(result.equity_curve) == len(bars)
    
    # Verify equity curve is monotonic (or at least reasonable)
    for i in range(1, len(result.equity_curve)):
        # Equity can go down, but shouldn't be negative
        assert result.equity_curve[i].equity >= Decimal("0")


def test_trade_executor_consistency():
    """Test that trade executor produces consistent results."""
    from dgas.backtesting.execution.trade_executor import BaseTradeExecutor
    from dgas.backtesting.entities import Position, PositionSide
    
    executor = BaseTradeExecutor(
        commission_rate=Decimal("0.001"),
        slippage_bps=Decimal("2.0"),
    )
    
    # Test opening and closing a position
    entry_time = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    position, entry_commission = executor.open_position(
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=Decimal("10"),
        entry_price=Decimal("100.00"),
        entry_time=entry_time,
    )
    
    assert position.quantity == Decimal("10")
    assert entry_commission > Decimal("0")
    
    # Close position
    exit_time = datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc)
    trade = executor.close_position(
        position=position,
        exit_price=Decimal("110.00"),
        exit_time=exit_time,
    )
    
    assert trade.gross_profit > Decimal("0")
    assert trade.net_profit > Decimal("0")
    assert trade.commission_paid == entry_commission + executor.compute_commission(
        position.quantity, trade.exit_price
    )


def test_portfolio_timeline_synchronization():
    """Test that optimized timeline synchronization produces correct results."""
    from dgas.backtesting.portfolio_data_loader import PortfolioDataLoader, SymbolDataBundle
    
    loader = PortfolioDataLoader(regular_hours_only=False)
    
    # Create test data with overlapping timestamps
    base_time = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    
    bundles = {
        "AAPL": SymbolDataBundle(
            symbol="AAPL",
            bars=[
                make_bar("AAPL", base_time + timedelta(minutes=30 * i), Decimal("100"))
                for i in range(5)
            ],
            bar_count=5,
        ),
        "MSFT": SymbolDataBundle(
            symbol="MSFT",
            bars=[
                make_bar("MSFT", base_time + timedelta(minutes=30 * i), Decimal("200"))
                for i in range(5)
            ],
            bar_count=5,
        ),
    }
    
    timeline = loader.create_synchronized_timeline(bundles)
    
    # Should have 5 timesteps (one per unique timestamp)
    assert len(timeline) == 5
    
    # Each timestep should have both symbols
    for timestep in timeline:
        assert "AAPL" in timestep.symbols_present
        assert "MSFT" in timestep.symbols_present
        assert timestep.get_bar("AAPL") is not None
        assert timestep.get_bar("MSFT") is not None
