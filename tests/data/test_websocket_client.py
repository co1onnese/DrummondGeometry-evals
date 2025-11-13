"""Tests for EODHD WebSocket client."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dgas.data.tick_aggregator import Tick, TickAggregator
from dgas.data.websocket_client import EODHDWebSocketClient, MAX_SYMBOLS_PER_CONNECTION


class TestTickAggregator:
    """Test tick aggregation into bars."""

    def test_aggregator_initialization(self):
        """Test aggregator initializes correctly."""
        agg = TickAggregator(interval="30m")
        assert agg.interval == "30m"
        assert agg.interval_seconds == 1800
        assert len(agg._pending_bars) == 0

    def test_add_tick_creates_bar(self):
        """Test adding tick creates pending bar."""
        agg = TickAggregator(interval="30m")
        
        # Create tick aligned to interval boundary
        bar_start = agg._align_to_interval(datetime.now(timezone.utc))
        tick = Tick(
            symbol="AAPL",
            timestamp=bar_start,
            price=Decimal("150.00"),
            volume=1000,
        )
        
        result = agg.add_tick(tick)
        assert result is None  # Bar not complete yet
        assert len(agg._pending_bars) == 1
        
        pending = agg.get_pending_bar("AAPL")
        assert pending is not None
        assert pending.symbol == "AAPL"
        assert pending.open == Decimal("150.00")
        assert pending.high == Decimal("150.00")
        assert pending.low == Decimal("150.00")
        assert pending.close == Decimal("150.00")
        assert pending.volume == 1000

    def test_add_tick_updates_bar(self):
        """Test adding multiple ticks updates bar."""
        agg = TickAggregator(interval="30m")
        
        bar_start = agg._align_to_interval(datetime.now(timezone.utc))
        
        # Add first tick
        tick1 = Tick("AAPL", bar_start, Decimal("150.00"), 1000)
        agg.add_tick(tick1)
        
        # Add second tick with higher price
        tick2 = Tick("AAPL", bar_start, Decimal("151.00"), 500)
        agg.add_tick(tick2)
        
        pending = agg.get_pending_bar("AAPL")
        assert pending.open == Decimal("150.00")
        assert pending.high == Decimal("151.00")
        assert pending.low == Decimal("150.00")
        assert pending.close == Decimal("151.00")
        assert pending.volume == 1500
        assert pending.tick_count == 2

    def test_bar_completion(self):
        """Test bar completes when interval ends."""
        agg = TickAggregator(interval="30m")
        
        # Create tick at start of interval
        bar_start = agg._align_to_interval(datetime.now(timezone.utc))
        tick = Tick("AAPL", bar_start, Decimal("150.00"), 1000)
        
        # Add tick
        result = agg.add_tick(tick)
        assert result is None  # Not complete yet
        
        # Flush with time past bar end
        bar_end = bar_start.replace(minute=bar_start.minute + 30)
        completed = agg.flush_pending_bars(bar_end)
        
        assert len(completed) == 1
        assert completed[0].symbol == "AAPL"
        assert completed[0].timestamp == bar_start
        assert len(agg._pending_bars) == 0

    def test_align_to_interval(self):
        """Test interval alignment."""
        agg = TickAggregator(interval="30m")
        
        # Test at :00
        dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        aligned = agg._align_to_interval(dt)
        assert aligned == dt
        
        # Test at :15 (should align to :00)
        dt = datetime(2024, 1, 1, 10, 15, 0, tzinfo=timezone.utc)
        aligned = agg._align_to_interval(dt)
        assert aligned == datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        
        # Test at :30 (should align to :30)
        dt = datetime(2024, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
        aligned = agg._align_to_interval(dt)
        assert aligned == dt
        
        # Test at :45 (should align to :30)
        dt = datetime(2024, 1, 1, 10, 45, 0, tzinfo=timezone.utc)
        aligned = agg._align_to_interval(dt)
        assert aligned == datetime(2024, 1, 1, 10, 30, 0, tzinfo=timezone.utc)

    def test_multiple_symbols(self):
        """Test aggregator handles multiple symbols."""
        agg = TickAggregator(interval="30m")
        
        bar_start = agg._align_to_interval(datetime.now(timezone.utc))
        
        tick1 = Tick("AAPL", bar_start, Decimal("150.00"), 1000)
        tick2 = Tick("MSFT", bar_start, Decimal("300.00"), 500)
        
        agg.add_tick(tick1)
        agg.add_tick(tick2)
        
        assert len(agg._pending_bars) == 2
        assert agg.get_pending_bar("AAPL") is not None
        assert agg.get_pending_bar("MSFT") is not None


class TestWebSocketClientParsing:
    """Test WebSocket message parsing."""

    def test_parse_tick_with_price(self):
        """Test parsing tick with price field."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        data = {
            "symbol": "AAPL",
            "price": 150.25,
            "volume": 1000,
            "timestamp": 1704110400,  # Unix timestamp
        }
        
        tick = client._parse_tick("AAPL", data)
        assert tick is not None
        assert tick.symbol == "AAPL"
        assert tick.price == Decimal("150.25")
        assert tick.volume == 1000

    def test_parse_tick_with_bid_ask(self):
        """Test parsing tick with bid/ask fields."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        data = {
            "symbol": "AAPL",
            "bid": 150.20,
            "ask": 150.30,
            "volume": 1000,
            "timestamp": "2024-01-01T10:00:00Z",
        }
        
        tick = client._parse_tick("AAPL", data)
        assert tick is not None
        # Should use midpoint
        assert tick.price == Decimal("150.25")  # (150.20 + 150.30) / 2

    def test_parse_tick_normalizes_symbol(self):
        """Test symbol normalization (removes .US suffix)."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        data = {
            "symbol": "AAPL.US",
            "price": 150.25,
            "volume": 1000,
            "timestamp": 1704110400,
        }
        
        tick = client._parse_tick("AAPL.US", data)
        assert tick is not None
        assert tick.symbol == "AAPL"  # .US removed

    def test_parse_tick_handles_milliseconds(self):
        """Test parsing timestamp in milliseconds."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        data = {
            "symbol": "AAPL",
            "price": 150.25,
            "volume": 1000,
            "timestamp": 1704110400000,  # Milliseconds
        }
        
        tick = client._parse_tick("AAPL", data)
        assert tick is not None
        # Should convert milliseconds to seconds
        assert tick.timestamp.timestamp() == pytest.approx(1704110400, abs=1)

    def test_parse_tick_missing_price(self):
        """Test parsing fails gracefully when price missing."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        data = {
            "symbol": "AAPL",
            "volume": 1000,
            "timestamp": 1704110400,
        }
        
        tick = client._parse_tick("AAPL", data)
        assert tick is None  # Should return None when price missing

    def test_parse_tick_invalid_data(self):
        """Test parsing handles invalid data."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        # Invalid data
        tick = client._parse_tick("AAPL", {})
        assert tick is None
        
        # Missing symbol
        tick = client._parse_tick("", {"price": 150.25})
        assert tick is None


class TestWebSocketClientConnection:
    """Test WebSocket connection management."""

    @pytest.mark.asyncio
    async def test_connect_splits_symbols(self):
        """Test connection splits symbols into chunks of 50."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        # Create 120 symbols (should create 3 connections: 50, 50, 20)
        symbols = [f"SYM{i}" for i in range(120)]
        
        with patch("dgas.data.websocket_client.websockets.connect") as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_ws
            mock_ws.__aiter__.return_value = iter([])  # No messages
            
            # Start connection (will create tasks)
            await client.connect(symbols)
            
            # Give tasks time to start
            await asyncio.sleep(0.1)
            
            # Should have 3 connections (120 / 50 = 2.4, rounded up to 3)
            assert len(client.connections) == 3
            assert len(client.connections[0].symbols) == 50
            assert len(client.connections[1].symbols) == 50
            assert len(client.connections[2].symbols) == 20

    @pytest.mark.asyncio
    async def test_connect_max_symbols_per_connection(self):
        """Test connection respects max symbols per connection."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        # Try to create connection with too many symbols
        symbols = [f"SYM{i}" for i in range(MAX_SYMBOLS_PER_CONNECTION + 1)]
        
        with pytest.raises(ValueError, match="Too many symbols"):
            await client._create_connection(0, symbols)

    @pytest.mark.asyncio
    async def test_disconnect_closes_connections(self):
        """Test disconnect closes all connections."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        client.running = True
        
        # Create mock connections
        mock_ws = AsyncMock()
        state = MagicMock()
        state.connection = mock_ws
        client.connections[0] = state
        
        await client.disconnect()
        
        # Should close connection
        mock_ws.close.assert_called_once()
        assert not client.running

    def test_get_status(self):
        """Test status reporting."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        # Create mock connections
        from dgas.data.websocket_client import WebSocketConnectionState
        
        state1 = WebSocketConnectionState(symbols=["AAPL", "MSFT"], connected=True)
        state1.messages_received = 10
        client.connections[0] = state1
        
        state2 = WebSocketConnectionState(symbols=["GOOGL"], connected=False)
        state2.messages_received = 5
        client.connections[1] = state2
        
        status = client.get_status()
        
        assert status["connections"] == 2
        assert status["connected"] == 1
        assert status["total_symbols"] == 3
        assert status["total_messages_received"] == 15


class TestWebSocketManager:
    """Test WebSocket manager (async/sync bridge)."""

    def test_manager_initialization(self):
        """Test manager initializes correctly."""
        from dgas.data.websocket_manager import WebSocketManager
        
        manager = WebSocketManager(api_token="test", interval="30m")
        assert manager.api_token == "test"
        assert manager.interval == "30m"
        assert not manager._running
        assert manager._websocket_manager is None  # Not started yet

    def test_start_websocket_collection(self):
        """Test starting WebSocket collection."""
        from dgas.data.collection_service import DataCollectionService
        from dgas.config.schema import DataCollectionConfig
        
        config = DataCollectionConfig(use_websocket=True, websocket_interval="30m")
        service = DataCollectionService(config)
        
        symbols = ["AAPL", "MSFT", "GOOGL"]
        
        # Mock settings
        with patch("dgas.data.collection_service.get_settings") as mock_settings:
            mock_settings.return_value.eodhd_api_token = "test_token"
            
            service.start_websocket_collection(symbols)
            
            # Manager should be created
            assert service._websocket_manager is not None

    def test_websocket_status(self):
        """Test WebSocket status reporting."""
        from dgas.data.collection_service import DataCollectionService
        from dgas.config.schema import DataCollectionConfig
        
        config = DataCollectionConfig(use_websocket=True, websocket_interval="30m")
        service = DataCollectionService(config)
        
        status = service.get_websocket_status()
        # Should return None if not started
        assert status is None or isinstance(status, dict)


class TestIntegration:
    """Integration tests for WebSocket flow."""

    @pytest.mark.asyncio
    async def test_tick_to_bar_flow(self):
        """Test complete flow from tick to bar."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        bars_received = []
        
        def on_bar(symbol, bar):
            bars_received.append((symbol, bar))
        
        client.on_bar_complete = on_bar
        
        # Simulate tick
        bar_start = client.aggregator._align_to_interval(datetime.now(timezone.utc))
        tick = Tick("AAPL", bar_start, Decimal("150.00"), 1000)
        
        # Add tick
        completed = client.aggregator.add_tick(tick)
        assert completed is None  # Not complete yet
        
        # Flush completed bars
        bar_end = bar_start.replace(minute=bar_start.minute + 30)
        completed = client.aggregator.flush_pending_bars(bar_end)
        
        assert len(completed) == 1
        assert completed[0].symbol == "AAPL"
