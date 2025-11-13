"""Comprehensive tests for tick aggregator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from dgas.data.tick_aggregator import Tick, TickAggregator


class TestTickAggregatorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_tick_list(self):
        """Test aggregator handles empty tick list."""
        agg = TickAggregator(interval="30m")
        assert len(agg._pending_bars) == 0
        assert agg.get_pending_bar("AAPL") is None

    def test_tick_outside_current_bar(self):
        """Test tick outside current bar creates new bar."""
        agg = TickAggregator(interval="30m")
        
        now = datetime.now(timezone.utc)
        bar1_start = agg._align_to_interval(now)
        bar2_start = bar1_start + timedelta(minutes=30)
        
        # Add tick to first bar
        tick1 = Tick("AAPL", bar1_start, Decimal("150.00"), 1000)
        agg.add_tick(tick1)
        
        # Add tick to second bar (different interval)
        tick2 = Tick("AAPL", bar2_start, Decimal("151.00"), 500)
        agg.add_tick(tick2)
        
        # Should have 2 pending bars
        assert len(agg._pending_bars) == 2

    def test_bar_ohlc_calculation(self):
        """Test OHLC values calculated correctly."""
        agg = TickAggregator(interval="30m")
        
        bar_start = agg._align_to_interval(datetime.now(timezone.utc))
        
        # Add ticks in sequence: 150, 152, 148, 151
        ticks = [
            Tick("AAPL", bar_start, Decimal("150.00"), 100),
            Tick("AAPL", bar_start + timedelta(seconds=10), Decimal("152.00"), 200),
            Tick("AAPL", bar_start + timedelta(seconds=20), Decimal("148.00"), 150),
            Tick("AAPL", bar_start + timedelta(seconds=30), Decimal("151.00"), 100),
        ]
        
        for tick in ticks:
            agg.add_tick(tick)
        
        pending = agg.get_pending_bar("AAPL")
        assert pending.open == Decimal("150.00")
        assert pending.high == Decimal("152.00")
        assert pending.low == Decimal("148.00")
        assert pending.close == Decimal("151.00")
        assert pending.volume == 550

    def test_flush_multiple_bars(self):
        """Test flushing multiple completed bars."""
        agg = TickAggregator(interval="30m")
        
        now = datetime.now(timezone.utc)
        bar1_start = agg._align_to_interval(now)
        bar2_start = bar1_start + timedelta(minutes=30)
        bar3_start = bar2_start + timedelta(minutes=30)
        
        # Add ticks to 3 different bars
        agg.add_tick(Tick("AAPL", bar1_start, Decimal("150.00"), 1000))
        agg.add_tick(Tick("MSFT", bar2_start, Decimal("300.00"), 500))
        agg.add_tick(Tick("GOOGL", bar3_start, Decimal("100.00"), 2000))
        
        # Flush bars ending before bar3_start
        flush_time = bar3_start
        completed = agg.flush_pending_bars(flush_time)
        
        # Should flush bar1 and bar2, but not bar3
        assert len(completed) == 2
        assert len(agg._pending_bars) == 1  # bar3 still pending

    def test_aggregator_statistics(self):
        """Test statistics tracking."""
        agg = TickAggregator(interval="30m")
        
        bar_start = agg._align_to_interval(datetime.now(timezone.utc))
        
        # Add some ticks
        for i in range(5):
            tick = Tick("AAPL", bar_start, Decimal(f"150.{i}"), 100)
            agg.add_tick(tick)
        
        stats = agg.get_stats()
        assert stats["ticks_processed"] == 5
        assert stats["pending_bars"] == 1

    def test_interval_alignment_edge_cases(self):
        """Test interval alignment at boundaries."""
        agg = TickAggregator(interval="30m")
        
        # Test at :00
        dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert agg._align_to_interval(dt) == dt
        
        # Test at :29 (should align to :00)
        dt = datetime(2024, 1, 1, 10, 29, 59, tzinfo=timezone.utc)
        aligned = agg._align_to_interval(dt)
        assert aligned == datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        
        # Test at :30
        dt = datetime(2024, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
        assert agg._align_to_interval(dt) == dt
        
        # Test at :59 (should align to :30)
        dt = datetime(2024, 1, 1, 10, 59, 59, tzinfo=timezone.utc)
        aligned = agg._align_to_interval(dt)
        assert aligned == datetime(2024, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
