"""Tests for shared trade execution logic."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from dgas.backtesting.entities import Position, PositionSide, Trade
from dgas.backtesting.execution.trade_executor import BaseTradeExecutor


@pytest.fixture
def executor():
    """Create a trade executor for testing."""
    return BaseTradeExecutor(
        commission_rate=Decimal("0.001"),  # 0.1%
        slippage_bps=Decimal("2.0"),  # 2 basis points
    )


def test_apply_slippage_long_entry(executor):
    """Test slippage application for long entry."""
    price = Decimal("100.00")
    result = executor.apply_slippage(price, PositionSide.LONG, is_entry=True)
    # Long entry: price + slippage
    expected = price * (Decimal("1") + Decimal("2") / Decimal("10000"))
    assert result == expected


def test_apply_slippage_long_exit(executor):
    """Test slippage application for long exit."""
    price = Decimal("100.00")
    result = executor.apply_slippage(price, PositionSide.LONG, is_entry=False)
    # Long exit: price - slippage
    expected = price * (Decimal("1") - Decimal("2") / Decimal("10000"))
    assert result == expected


def test_apply_slippage_short_entry(executor):
    """Test slippage application for short entry."""
    price = Decimal("100.00")
    result = executor.apply_slippage(price, PositionSide.SHORT, is_entry=True)
    # Short entry: price - slippage
    expected = price * (Decimal("1") - Decimal("2") / Decimal("10000"))
    assert result == expected


def test_apply_slippage_short_exit(executor):
    """Test slippage application for short exit."""
    price = Decimal("100.00")
    result = executor.apply_slippage(price, PositionSide.SHORT, is_entry=False)
    # Short exit: price + slippage
    expected = price * (Decimal("1") + Decimal("2") / Decimal("10000"))
    assert result == expected


def test_apply_slippage_zero_slippage():
    """Test that zero slippage returns original price."""
    executor = BaseTradeExecutor(slippage_bps=Decimal("0"))
    price = Decimal("100.00")
    result = executor.apply_slippage(price, PositionSide.LONG, is_entry=True)
    assert result == price


def test_compute_commission(executor):
    """Test commission calculation."""
    quantity = Decimal("10")
    price = Decimal("100.00")
    commission = executor.compute_commission(quantity, price)
    expected = quantity * price * Decimal("0.001")
    assert commission == expected


def test_compute_commission_zero_rate():
    """Test that zero commission rate returns zero."""
    executor = BaseTradeExecutor(commission_rate=Decimal("0"))
    commission = executor.compute_commission(Decimal("10"), Decimal("100"))
    assert commission == Decimal("0")


def test_calculate_gross_profit_long(executor):
    """Test gross profit calculation for long position."""
    position = Position(
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=Decimal("10"),
        entry_price=Decimal("100.00"),
        entry_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    
    exit_price = Decimal("110.00")
    gross_profit = executor.calculate_gross_profit(position, exit_price)
    expected = Decimal("10") * (exit_price - position.entry_price)
    assert gross_profit == expected


def test_calculate_gross_profit_short(executor):
    """Test gross profit calculation for short position."""
    position = Position(
        symbol="AAPL",
        side=PositionSide.SHORT,
        quantity=Decimal("10"),
        entry_price=Decimal("100.00"),
        entry_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    
    exit_price = Decimal("90.00")
    gross_profit = executor.calculate_gross_profit(position, exit_price)
    expected = Decimal("-10") * (exit_price - position.entry_price)
    assert gross_profit == expected


def test_calculate_net_profit(executor):
    """Test net profit calculation after commissions."""
    position = Position(
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=Decimal("10"),
        entry_price=Decimal("100.00"),
        entry_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        entry_commission=Decimal("1.00"),
    )
    
    exit_price = Decimal("110.00")
    exit_commission = Decimal("1.10")
    net_profit = executor.calculate_net_profit(position, exit_price, exit_commission)
    
    gross_profit = Decimal("10") * (exit_price - position.entry_price)  # $100
    total_commission = position.entry_commission + exit_commission  # $2.10
    expected = gross_profit - total_commission  # $97.90
    
    assert net_profit == expected


def test_normalize_quantity(executor):
    """Test quantity normalization."""
    quantity = Decimal("10.123456")
    normalized = executor.normalize_quantity(quantity)
    assert normalized == Decimal("10.1234")  # Rounded to 4 decimal places


def test_normalize_quantity_zero(executor):
    """Test that zero or negative quantities return zero."""
    assert executor.normalize_quantity(Decimal("0")) == Decimal("0")
    assert executor.normalize_quantity(Decimal("-5")) == Decimal("0")


def test_open_position(executor):
    """Test opening a position."""
    timestamp = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    position, commission = executor.open_position(
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=Decimal("10"),
        entry_price=Decimal("100.00"),
        entry_time=timestamp,
        metadata={"test": "value"},
    )
    
    assert position.symbol == "AAPL"
    assert position.side == PositionSide.LONG
    assert position.quantity == Decimal("10")
    assert position.entry_time == timestamp
    assert position.notes == {"test": "value"}
    # Entry price should have slippage applied
    assert position.entry_price > Decimal("100.00")
    assert commission > Decimal("0")


def test_close_position(executor):
    """Test closing a position."""
    entry_time = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    exit_time = datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc)
    
    position = Position(
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=Decimal("10"),
        entry_price=Decimal("100.00"),
        entry_time=entry_time,
        entry_commission=Decimal("1.00"),
    )
    
    trade = executor.close_position(
        position=position,
        exit_price=Decimal("110.00"),
        exit_time=exit_time,
    )
    
    assert trade.symbol == "AAPL"
    assert trade.side == PositionSide.LONG
    assert trade.quantity == Decimal("10")
    assert trade.entry_time == entry_time
    assert trade.exit_time == exit_time
    assert trade.entry_price == Decimal("100.00")
    # Exit price should have slippage applied (slightly less than 110)
    assert trade.exit_price < Decimal("110.00")
    assert trade.gross_profit > Decimal("0")
    assert trade.net_profit > Decimal("0")
    assert trade.commission_paid > position.entry_commission
