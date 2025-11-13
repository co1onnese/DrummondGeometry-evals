"""Integration tests for WebSocket with collection service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dgas.config.schema import DataCollectionConfig
from dgas.data.collection_service import DataCollectionService


class TestWebSocketCollectionService:
    """Test WebSocket integration with collection service."""

    def test_service_creates_websocket_manager(self):
        """Test service creates WebSocket manager when enabled."""
        config = DataCollectionConfig(use_websocket=True, websocket_interval="30m")
        
        with patch("dgas.data.collection_service.get_settings") as mock_settings:
            mock_settings.return_value.eodhd_api_token = "test_token"
            
            service = DataCollectionService(config)
            
            assert service._websocket_manager is not None

    def test_service_no_websocket_when_disabled(self):
        """Test service doesn't create manager when disabled."""
        config = DataCollectionConfig(use_websocket=False)
        service = DataCollectionService(config)
        
        assert service._websocket_manager is None

    def test_start_websocket_collection(self):
        """Test starting WebSocket collection."""
        config = DataCollectionConfig(use_websocket=True, websocket_interval="30m")
        
        with patch("dgas.data.collection_service.get_settings") as mock_settings:
            mock_settings.return_value.eodhd_api_token = "test_token"
            
            service = DataCollectionService(config)
            
            # Mock WebSocket manager
            mock_manager = MagicMock()
            mock_manager.is_connected.return_value = False
            service._websocket_manager = mock_manager
            
            symbols = ["AAPL", "MSFT"]
            service.start_websocket_collection(symbols)
            
            mock_manager.start.assert_called_once_with(symbols)

    def test_stop_websocket_collection(self):
        """Test stopping WebSocket collection."""
        config = DataCollectionConfig(use_websocket=True)
        
        with patch("dgas.data.collection_service.get_settings") as mock_settings:
            mock_settings.return_value.eodhd_api_token = "test_token"
            
            service = DataCollectionService(config)
            
            # Mock WebSocket manager
            mock_manager = MagicMock()
            service._websocket_manager = mock_manager
            
            service.stop_websocket_collection()
            
            mock_manager.stop.assert_called_once()

    def test_store_websocket_bars(self):
        """Test storing WebSocket bars."""
        config = DataCollectionConfig(use_websocket=True)
        
        with patch("dgas.data.collection_service.get_settings") as mock_settings:
            mock_settings.return_value.eodhd_api_token = "test_token"
            
            service = DataCollectionService(config)
            
            # Mock WebSocket manager
            mock_manager = MagicMock()
            mock_manager.store_buffered_bars.return_value = 10
            service._websocket_manager = mock_manager
            
            stored = service.store_websocket_bars(batch_size=100)
            
            assert stored == 10
            mock_manager.store_buffered_bars.assert_called_once_with(batch_size=100)

    def test_get_websocket_status(self):
        """Test getting WebSocket status."""
        config = DataCollectionConfig(use_websocket=True)
        
        with patch("dgas.data.collection_service.get_settings") as mock_settings:
            mock_settings.return_value.eodhd_api_token = "test_token"
            
            service = DataCollectionService(config)
            
            # Mock WebSocket manager
            mock_manager = MagicMock()
            mock_manager.get_status.return_value = {"running": True}
            service._websocket_manager = mock_manager
            
            status = service.get_websocket_status()
            
            assert status == {"running": True}
            mock_manager.get_status.assert_called_once()
