"""Tests for WebSocket integration in collection scheduler."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from dgas.config.schema import DataCollectionConfig
from dgas.data.collection_scheduler import DataCollectionScheduler
from dgas.prediction.scheduler import MarketHoursManager, TradingSession


class TestCollectionSchedulerWebSocket:
    """Test WebSocket lifecycle in collection scheduler."""

    def test_scheduler_initialization(self):
        """Test scheduler initializes with WebSocket support."""
        config = DataCollectionConfig(use_websocket=True)
        symbols = ["AAPL", "MSFT"]
        
        scheduler = DataCollectionScheduler(
            config=config,
            symbols=symbols,
        )
        
        assert scheduler.config == config
        assert scheduler.symbols == symbols
        assert not scheduler._websocket_started

    @patch("dgas.data.collection_scheduler.BackgroundScheduler")
    def test_start_websocket_when_market_open(self, mock_scheduler_class):
        """Test WebSocket starts when market is open."""
        config = DataCollectionConfig(use_websocket=True)
        symbols = ["AAPL", "MSFT"]
        
        scheduler = DataCollectionScheduler(
            config=config,
            symbols=symbols,
        )
        
        # Mock market hours
        mock_market_hours = MagicMock()
        mock_market_hours.is_market_open.return_value = True
        scheduler.market_hours = mock_market_hours
        
        # Mock service
        mock_service = MagicMock()
        mock_service.start_websocket_collection = MagicMock()
        scheduler.service = mock_service
        
        # Mock scheduler
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler
        
        scheduler.start()
        
        # Should start WebSocket
        mock_service.start_websocket_collection.assert_called_once_with(symbols)
        assert scheduler._websocket_started

    @patch("dgas.data.collection_scheduler.BackgroundScheduler")
    def test_start_no_websocket_when_market_closed(self, mock_scheduler_class):
        """Test WebSocket doesn't start when market is closed."""
        config = DataCollectionConfig(use_websocket=True)
        symbols = ["AAPL", "MSFT"]
        
        scheduler = DataCollectionScheduler(
            config=config,
            symbols=symbols,
        )
        
        # Mock market hours
        mock_market_hours = MagicMock()
        mock_market_hours.is_market_open.return_value = False
        scheduler.market_hours = mock_market_hours
        
        # Mock service
        mock_service = MagicMock()
        scheduler.service = mock_service
        
        # Mock scheduler
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler
        
        scheduler.start()
        
        # Should not start WebSocket
        mock_service.start_websocket_collection.assert_not_called()
        assert not scheduler._websocket_started

    def test_execute_cycle_starts_websocket_on_market_open(self):
        """Test cycle starts WebSocket when market opens."""
        config = DataCollectionConfig(use_websocket=True)
        symbols = ["AAPL", "MSFT"]
        
        scheduler = DataCollectionScheduler(
            config=config,
            symbols=symbols,
        )
        
        # Mock market hours
        mock_market_hours = MagicMock()
        mock_market_hours.is_market_open.return_value = True
        scheduler.market_hours = mock_market_hours
        
        # Mock service
        mock_service = MagicMock()
        mock_service.start_websocket_collection = MagicMock()
        scheduler.service = mock_service
        
        scheduler._websocket_started = False
        
        # Execute cycle
        scheduler._execute_collection_cycle()
        
        # Should start WebSocket
        mock_service.start_websocket_collection.assert_called_once_with(symbols)
        assert scheduler._websocket_started

    def test_execute_cycle_stops_websocket_on_market_close(self):
        """Test cycle stops WebSocket when market closes."""
        config = DataCollectionConfig(use_websocket=True)
        symbols = ["AAPL", "MSFT"]
        
        scheduler = DataCollectionScheduler(
            config=config,
            symbols=symbols,
        )
        
        # Mock market hours
        mock_market_hours = MagicMock()
        mock_market_hours.is_market_open.return_value = False
        scheduler.market_hours = mock_market_hours
        
        # Mock service
        mock_service = MagicMock()
        mock_service.stop_websocket_collection = MagicMock()
        mock_service.store_websocket_bars.return_value = 5
        scheduler.service = mock_service
        
        scheduler._websocket_started = True
        
        # Execute cycle
        scheduler._execute_collection_cycle()
        
        # Should stop WebSocket
        mock_service.stop_websocket_collection.assert_called_once()
        mock_service.store_websocket_bars.assert_called_once()
        assert not scheduler._websocket_started

    def test_store_websocket_bars_periodic(self):
        """Test periodic bar storage."""
        config = DataCollectionConfig(use_websocket=True)
        symbols = ["AAPL", "MSFT"]
        
        scheduler = DataCollectionScheduler(
            config=config,
            symbols=symbols,
        )
        
        # Mock service
        mock_service = MagicMock()
        mock_service.store_websocket_bars.return_value = 10
        scheduler.service = mock_service
        
        scheduler._websocket_started = True
        
        # Store bars
        scheduler._store_websocket_bars()
        
        mock_service.store_websocket_bars.assert_called_once_with(batch_size=100)

    def test_store_websocket_bars_skips_when_not_started(self):
        """Test bar storage skips when WebSocket not started."""
        config = DataCollectionConfig(use_websocket=True)
        symbols = ["AAPL", "MSFT"]
        
        scheduler = DataCollectionScheduler(
            config=config,
            symbols=symbols,
        )
        
        # Mock service
        mock_service = MagicMock()
        scheduler.service = mock_service
        
        scheduler._websocket_started = False
        
        # Store bars
        scheduler._store_websocket_bars()
        
        # Should not call store
        mock_service.store_websocket_bars.assert_not_called()
