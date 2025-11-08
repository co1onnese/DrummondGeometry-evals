"""Tests for portfolio data loader optimizations."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from dgas.backtesting.portfolio_data_loader import PortfolioDataLoader, PortfolioTimestep
from dgas.data.models import IntervalData


def make_bar(symbol: str, timestamp: datetime, close: str) -> IntervalData:
    """Create a test bar."""
    price = Decimal(close)
    return IntervalData(
        symbol=symbol,
        exchange="NASDAQ",
        timestamp=timestamp.isoformat(),
        interval="30m",
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price,
        adjusted_close=price,
        volume=1000,
    )


def test_timeline_synchronization_optimization():
    """Test that timeline synchronization produces correct results."""
    loader = PortfolioDataLoader(regular_hours_only=False)
    
    # Create test bundles
    timestamp1 = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    timestamp2 = datetime(2025, 1, 1, 12, 30, tzinfo=timezone.utc)
    timestamp3 = datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc)
    
    from dgas.backtesting.portfolio_data_loader import SymbolDataBundle
    
    bundles = {
        "AAPL": SymbolDataBundle(
            symbol="AAPL",
            bars=[
                make_bar("AAPL", timestamp1, "100"),
                make_bar("AAPL", timestamp2, "101"),
                make_bar("AAPL", timestamp3, "102"),
            ],
            bar_count=3,
        ),
        "MSFT": SymbolDataBundle(
            symbol="MSFT",
            bars=[
                make_bar("MSFT", timestamp1, "200"),
                make_bar("MSFT", timestamp3, "201"),  # Missing timestamp2
            ],
            bar_count=2,
        ),
    }
    
    timeline = loader.create_synchronized_timeline(bundles)
    
    # Should have 3 timesteps
    assert len(timeline) == 3
    
    # Check first timestep
    assert timeline[0].timestamp == timestamp1
    assert "AAPL" in timeline[0].symbols_present
    assert "MSFT" in timeline[0].symbols_present
    
    # Check second timestep (only AAPL)
    assert timeline[1].timestamp == timestamp2
    assert "AAPL" in timeline[1].symbols_present
    assert "MSFT" not in timeline[1].symbols_present
    
    # Check third timestep
    assert timeline[2].timestamp == timestamp3
    assert "AAPL" in timeline[2].symbols_present
    assert "MSFT" in timeline[2].symbols_present


def test_timeline_synchronization_empty_bundles():
    """Test timeline synchronization with empty bundles."""
    loader = PortfolioDataLoader()
    timeline = loader.create_synchronized_timeline({})
    assert timeline == []


def test_timeline_synchronization_single_symbol():
    """Test timeline synchronization with single symbol."""
    loader = PortfolioDataLoader(regular_hours_only=False)
    
    timestamp1 = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    timestamp2 = datetime(2025, 1, 1, 12, 30, tzinfo=timezone.utc)
    
    from dgas.backtesting.portfolio_data_loader import SymbolDataBundle
    
    bundles = {
        "AAPL": SymbolDataBundle(
            symbol="AAPL",
            bars=[
                make_bar("AAPL", timestamp1, "100"),
                make_bar("AAPL", timestamp2, "101"),
            ],
            bar_count=2,
        ),
    }
    
    timeline = loader.create_synchronized_timeline(bundles)
    assert len(timeline) == 2
    assert timeline[0].timestamp == timestamp1
    assert timeline[1].timestamp == timestamp2
