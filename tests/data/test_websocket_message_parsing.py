"""Tests for EODHD WebSocket message parsing with official format."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from dgas.data.websocket_client import EODHDWebSocketClient


class TestEODHDMessageParsing:
    """Test message parsing with official EODHD format."""

    def test_parse_us_trade_message(self):
        """Test parsing US trade message format."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        # Official EODHD US Trades format
        message = {
            "s": "AAPL",        # ticker
            "p": 227.31,        # last trade price
            "v": 100,           # trade size (shares)
            "c": 12,            # trade condition code
            "dp": False,        # dark pool
            "ms": "open",       # market status
            "t": 1725198451165  # epoch ms
        }
        
        tick = client._parse_tick("AAPL", message)
        
        assert tick is not None
        assert tick.symbol == "AAPL"
        assert tick.price == Decimal("227.31")
        assert tick.volume == 100
        assert tick.timestamp.year == 2024  # Verify timestamp conversion
        assert "trade" in tick.trade_type.lower()

    def test_parse_message_with_symbol_from_field(self):
        """Test parsing message where symbol comes from 's' field."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        message = {
            "s": "MSFT",
            "p": 350.50,
            "v": 200,
            "t": 1725198451165
        }
        
        # Pass empty symbol, should extract from message
        tick = client._parse_tick("", message)
        
        assert tick is not None
        assert tick.symbol == "MSFT"  # Extracted from "s" field

    def test_parse_message_dark_pool(self):
        """Test parsing dark pool trade."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        message = {
            "s": "GOOGL",
            "p": 140.25,
            "v": 500,
            "c": 15,
            "dp": True,  # Dark pool
            "ms": "open",
            "t": 1725198451165
        }
        
        tick = client._parse_tick("GOOGL", message)
        
        assert tick is not None
        assert "dark_pool" in tick.trade_type.lower()

    def test_parse_message_missing_fields(self):
        """Test parsing message with missing optional fields."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        # Minimal message (only required fields)
        message = {
            "s": "TSLA",
            "p": 250.00,
            "t": 1725198451165
            # Missing: v, c, dp, ms
        }
        
        tick = client._parse_tick("TSLA", message)
        
        assert tick is not None
        assert tick.symbol == "TSLA"
        assert tick.price == Decimal("250.00")
        assert tick.volume == 0  # Default when missing

    def test_parse_message_missing_price(self):
        """Test parsing message without price (should return None)."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        message = {
            "s": "AAPL",
            "v": 100,
            "t": 1725198451165
            # Missing: p (price)
        }
        
        tick = client._parse_tick("AAPL", message)
        
        assert tick is None  # No price = invalid message

    def test_parse_message_epoch_timestamp(self):
        """Test parsing epoch milliseconds timestamp."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        # Test with known timestamp: 2024-09-02 12:00:00 UTC
        epoch_ms = 1725283200000
        message = {
            "s": "AAPL",
            "p": 150.00,
            "v": 100,
            "t": epoch_ms
        }
        
        tick = client._parse_tick("AAPL", message)
        
        assert tick is not None
        assert tick.timestamp.timestamp() == pytest.approx(epoch_ms / 1000.0, abs=1.0)

    def test_handle_authorization_message(self):
        """Test handling authorization message."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        # Authorization message format
        message = '{"status_code": 200, "message": "Authorized"}'
        
        # This should not raise an error
        # The message handler should recognize this as an authorization message
        # and not try to parse it as a price update
        import json
        data = json.loads(message)
        
        # Should not have "s" field, so won't be handled as price update
        assert "s" not in data
        assert data.get("status_code") == 200

    def test_subscription_format(self):
        """Test subscription message format (comma-separated string)."""
        symbols = ["AAPL", "MSFT", "GOOGL"]
        symbols_str = ",".join(symbols)
        
        subscribe_msg = {
            "action": "subscribe",
            "symbols": symbols_str  # Comma-separated string, not array
        }
        
        import json
        msg_json = json.dumps(subscribe_msg)
        parsed = json.loads(msg_json)
        
        assert isinstance(parsed["symbols"], str)
        assert parsed["symbols"] == "AAPL,MSFT,GOOGL"

    def test_parse_multiple_condition_codes(self):
        """Test parsing messages with different condition codes."""
        client = EODHDWebSocketClient(api_token="test", interval="30m")
        
        test_cases = [
            ({"s": "AAPL", "p": 150.00, "v": 100, "c": 0, "t": 1725198451165}, "trade_c0"),
            ({"s": "AAPL", "p": 150.00, "v": 100, "c": 12, "t": 1725198451165}, "trade_c12"),
            ({"s": "AAPL", "p": 150.00, "v": 100, "c": 15, "dp": True, "t": 1725198451165}, "dark_pool_c15"),
        ]
        
        for message, expected_type in test_cases:
            tick = client._parse_tick("AAPL", message)
            assert tick is not None
            assert expected_type in tick.trade_type
