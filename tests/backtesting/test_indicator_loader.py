"""Tests for indicator loading from database."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest

from dgas.backtesting.indicator_loader import load_indicators_from_db, load_indicators_batch


def test_load_indicators_from_db_not_found(monkeypatch):
    """Test loading when indicator not found in database."""
    # Mock get_symbol_id to return None (symbol not found)
    monkeypatch.setattr(
        "dgas.backtesting.indicator_loader.get_symbol_id",
        lambda conn, symbol: None,
    )
    
    result = load_indicators_from_db(
        "AAPL",
        datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        "1d",
        "30m",
    )
    
    assert result is None


def test_load_indicators_from_db_no_row(monkeypatch):
    """Test loading when database query returns no row."""
    # Mock get_symbol_id
    monkeypatch.setattr(
        "dgas.backtesting.indicator_loader.get_symbol_id",
        lambda conn, symbol: 1,
    )
    
    # Mock connection and cursor
    mock_cursor = Mock()
    mock_cursor.fetchone.return_value = None  # No row found
    mock_cursor.__enter__ = Mock(return_value=mock_cursor)
    mock_cursor.__exit__ = Mock(return_value=None)
    
    mock_conn = Mock()
    mock_conn.cursor.return_value = mock_cursor
    
    monkeypatch.setattr(
        "dgas.backtesting.indicator_loader.get_connection",
        lambda: Mock(__enter__=Mock(return_value=mock_conn), __exit__=Mock(return_value=None)),
    )
    
    result = load_indicators_from_db(
        "AAPL",
        datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        "1d",
        "30m",
    )
    
    assert result is None


def test_load_indicators_batch_empty_list():
    """Test batch loading with empty timestamp list."""
    result = load_indicators_batch("AAPL", [], "1d", "30m")
    assert result == {}


@pytest.mark.skip(reason="Requires database setup - integration test")
def test_load_indicators_integration():
    """Integration test for indicator loading (requires database)."""
    # This would be an integration test that actually queries the database
    pass
