"""Comprehensive tests for notification system."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from decimal import Decimal

from dgas.prediction.notifications.router import (
    NotificationConfig,
    NotificationRouter,
    NotificationAdapter,
)
from dgas.prediction.notifications.adapters.discord import DiscordAdapter
from dgas.prediction.notifications.adapters.console import ConsoleAdapter
from dgas.prediction.engine import GeneratedSignal, SignalType
from dgas.calculations.states import TrendDirection


@pytest.fixture
def sample_signal():
    """Create sample signal for testing."""
    return GeneratedSignal(
        symbol="AAPL",
        signal_timestamp=datetime(2025, 11, 6, 14, 30, tzinfo=timezone.utc),
        signal_type=SignalType.LONG,
        entry_price=Decimal("150.00"),
        stop_loss=Decimal("148.00"),
        target_price=Decimal("154.00"),
        confidence=0.75,
        signal_strength=0.80,
        timeframe_alignment=0.85,
        risk_reward_ratio=2.0,
        htf_trend=TrendDirection.UP,
        htf_timeframe="4h",
        trading_tf_state="TREND",
        trading_timeframe="1h",
        confluence_zones_count=2,
        pattern_context={"patterns": [{"type": "PLDOT_PUSH"}]},
    )


@pytest.fixture
def sample_short_signal():
    """Create sample SHORT signal for testing."""
    return GeneratedSignal(
        symbol="TSLA",
        signal_timestamp=datetime(2025, 11, 6, 15, 0, tzinfo=timezone.utc),
        signal_type=SignalType.SHORT,
        entry_price=Decimal("200.00"),
        stop_loss=Decimal("202.00"),
        target_price=Decimal("196.00"),
        confidence=0.68,
        signal_strength=0.72,
        timeframe_alignment=0.78,
        risk_reward_ratio=2.0,
        htf_trend=TrendDirection.DOWN,
        htf_timeframe="4h",
        trading_tf_state="TREND",
        trading_timeframe="1h",
        confluence_zones_count=1,
        pattern_context={"patterns": [{"type": "EXHAUST"}]},
    )


class TestNotificationConfig:
    """Tests for NotificationConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = NotificationConfig()
        assert "console" in config.enabled_channels
        assert "discord" in config.enabled_channels
        assert config.discord_min_confidence == 0.5
        assert config.console_max_signals == 10

    def test_from_env(self, monkeypatch):
        """Test config creation from environment."""
        monkeypatch.setenv("DGAS_DISCORD_BOT_TOKEN", "test_token_123")
        monkeypatch.setenv("DGAS_DISCORD_CHANNEL_ID", "1234567890")

        config = NotificationConfig.from_env()
        assert config.discord_bot_token == "test_token_123"
        assert config.discord_channel_id == "1234567890"

    def test_from_env_missing_vars(self):
        """Test config creation with missing environment variables."""
        config = NotificationConfig.from_env()
        assert config.discord_bot_token is None
        assert config.discord_channel_id is None


class TestNotificationRouter:
    """Tests for NotificationRouter."""

    def test_send_notifications_success(self, sample_signal):
        """Test successful notification delivery."""
        # Mock adapters
        mock_adapter = Mock(spec=NotificationAdapter)
        mock_adapter.send.return_value = True

        config = NotificationConfig(enabled_channels=["mock"])
        router = NotificationRouter(config, {"mock": mock_adapter})

        results = router.send_notifications([sample_signal], {})

        assert results["mock"] is True
        mock_adapter.send.assert_called_once()

    def test_send_notifications_empty_list(self):
        """Test handling of empty signal list."""
        config = NotificationConfig(enabled_channels=["console"])
        router = NotificationRouter(config, {})

        results = router.send_notifications([], {})

        assert results == {}

    def test_send_notifications_filters_by_confidence(self, sample_signal):
        """Test signals filtered by channel confidence threshold."""
        # Create low confidence signal
        low_conf_signal = GeneratedSignal(
            symbol="MSFT",
            signal_timestamp=datetime(2025, 11, 6, 14, 30, tzinfo=timezone.utc),
            signal_type=SignalType.LONG,
            entry_price=Decimal("350.00"),
            stop_loss=Decimal("348.00"),
            target_price=Decimal("354.00"),
            confidence=0.4,  # Below discord threshold (0.5)
            signal_strength=0.50,
            timeframe_alignment=0.60,
            risk_reward_ratio=2.0,
            htf_trend=TrendDirection.UP,
            htf_timeframe="4h",
            trading_tf_state="TREND",
            trading_timeframe="1h",
            confluence_zones_count=1,
            pattern_context={},
        )

        mock_adapter = Mock(spec=NotificationAdapter)
        mock_adapter.send.return_value = True

        config = NotificationConfig(
            enabled_channels=["discord"],
            discord_min_confidence=0.5,
        )
        router = NotificationRouter(config, {"discord": mock_adapter})

        results = router.send_notifications([low_conf_signal], {})

        # Should succeed but not call adapter (no signals passed filter)
        assert results["discord"] is True
        mock_adapter.send.assert_not_called()

    def test_send_notifications_handles_errors(self, sample_signal):
        """Test error handling in notification delivery."""
        mock_adapter = Mock(spec=NotificationAdapter)
        mock_adapter.send.side_effect = Exception("Network error")

        config = NotificationConfig(enabled_channels=["mock"])
        router = NotificationRouter(config, {"mock": mock_adapter})

        results = router.send_notifications([sample_signal], {})

        assert results["mock"] is False

    def test_send_notifications_missing_adapter(self, sample_signal):
        """Test handling of missing adapter."""
        config = NotificationConfig(enabled_channels=["missing_channel"])
        router = NotificationRouter(config, {})

        results = router.send_notifications([sample_signal], {})

        assert results["missing_channel"] is False

    def test_send_notifications_multiple_channels(self, sample_signal):
        """Test delivery to multiple channels."""
        mock_adapter1 = Mock(spec=NotificationAdapter)
        mock_adapter1.send.return_value = True

        mock_adapter2 = Mock(spec=NotificationAdapter)
        mock_adapter2.send.return_value = True

        config = NotificationConfig(enabled_channels=["channel1", "channel2"])
        router = NotificationRouter(
            config,
            {"channel1": mock_adapter1, "channel2": mock_adapter2},
        )

        results = router.send_notifications([sample_signal], {})

        assert results["channel1"] is True
        assert results["channel2"] is True
        assert mock_adapter1.send.call_count == 1
        assert mock_adapter2.send.call_count == 1


class TestDiscordAdapter:
    """Tests for DiscordAdapter."""

    def test_init_requires_token(self):
        """Test Discord adapter validates bot token."""
        with pytest.raises(ValueError, match="bot token is required"):
            DiscordAdapter(bot_token="", channel_id="123")

    def test_init_requires_channel_id(self):
        """Test Discord adapter validates channel ID."""
        with pytest.raises(ValueError, match="channel ID is required"):
            DiscordAdapter(bot_token="token", channel_id="")

    def test_create_embed_long_signal(self, sample_signal):
        """Test Discord embed creation for LONG signal."""
        adapter = DiscordAdapter(
            bot_token="test_token",
            channel_id="123456",
        )

        embed = adapter._create_embed(sample_signal, {})

        assert "AAPL" in embed["title"]
        assert "LONG" in embed["title"]
        assert embed["color"] == 0x00FF00  # Green
        assert len(embed["fields"]) >= 9  # All required fields
        assert embed["fields"][0]["name"] == "Entry Price"
        assert "$150.00" in embed["fields"][0]["value"]

    def test_create_embed_short_signal(self, sample_short_signal):
        """Test Discord embed creation for SHORT signal."""
        adapter = DiscordAdapter(
            bot_token="test_token",
            channel_id="123456",
        )

        embed = adapter._create_embed(sample_short_signal, {})

        assert "TSLA" in embed["title"]
        assert "SHORT" in embed["title"]
        assert embed["color"] == 0xFF0000  # Red
        assert "📉" in embed["title"]

    def test_create_embed_with_patterns(self, sample_signal):
        """Test embed includes pattern context."""
        adapter = DiscordAdapter(
            bot_token="test_token",
            channel_id="123456",
        )

        embed = adapter._create_embed(sample_signal, {})

        # Check for pattern field
        pattern_fields = [f for f in embed["fields"] if f["name"] == "Triggering Patterns"]
        assert len(pattern_fields) == 1
        assert "PLDOT_PUSH" in pattern_fields[0]["value"]

    def test_format_confidence_bar(self, sample_signal):
        """Test confidence bar formatting."""
        adapter = DiscordAdapter(
            bot_token="test_token",
            channel_id="123456",
        )

        bar = adapter._format_confidence_bar(0.75)

        assert "█" in bar  # Filled blocks
        assert "░" in bar  # Empty blocks
        assert "75%" in bar

    @patch("requests.post")
    def test_send_to_discord_success(self, mock_post, sample_signal):
        """Test successful Discord API call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        adapter = DiscordAdapter(
            bot_token="test_token",
            channel_id="123456",
        )

        result = adapter.send([sample_signal], {})

        assert result is True
        assert mock_post.call_count == 1

        # Verify API call parameters
        call_args = mock_post.call_args
        assert "https://discord.com/api/v10/channels/123456/messages" in call_args[0][0]
        assert call_args[1]["headers"]["Authorization"] == "Bot test_token"

    @patch("requests.post")
    def test_send_to_discord_rate_limit_retry(self, mock_post, sample_signal):
        """Test Discord rate limit handling with retry."""
        # First call: rate limited
        rate_limit_response = Mock()
        rate_limit_response.status_code = 429
        rate_limit_response.json.return_value = {"retry_after": 0.1}

        # Second call: success
        success_response = Mock()
        success_response.status_code = 200
        success_response.raise_for_status = Mock()

        mock_post.side_effect = [rate_limit_response, success_response]

        adapter = DiscordAdapter(
            bot_token="test_token",
            channel_id="123456",
            rate_limit_delay=0.1,  # Speed up test
        )

        result = adapter.send([sample_signal], {})

        assert result is True
        assert mock_post.call_count == 2  # Initial + retry

    @patch("requests.post")
    def test_send_multiple_signals_with_delay(
        self, mock_post, sample_signal, sample_short_signal
    ):
        """Test sending multiple signals with rate limiting delay."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        adapter = DiscordAdapter(
            bot_token="test_token",
            channel_id="123456",
            rate_limit_delay=0.1,  # Speed up test
        )

        result = adapter.send([sample_signal, sample_short_signal], {})

        assert result is True
        assert mock_post.call_count == 2  # One per signal

    @patch("requests.post")
    def test_send_partial_success(self, mock_post, sample_signal, sample_short_signal):
        """Test partial success (>80% success rate)."""
        # First signal succeeds, second fails
        success_response = Mock()
        success_response.status_code = 200
        success_response.raise_for_status = Mock()

        failure_response = Mock()
        failure_response.status_code = 500
        failure_response.raise_for_status = Mock(side_effect=Exception("Server error"))

        mock_post.side_effect = [success_response, failure_response]

        adapter = DiscordAdapter(
            bot_token="test_token",
            channel_id="123456",
            rate_limit_delay=0.1,
        )

        # With 2 signals and 1 success, that's 50% success - should fail
        result = adapter.send([sample_signal, sample_short_signal], {})

        assert result is False  # <80% success threshold


class TestConsoleAdapter:
    """Tests for ConsoleAdapter."""

    def test_console_output_summary(self, sample_signal, capsys):
        """Test console summary output."""
        adapter = ConsoleAdapter(output_format="summary")

        result = adapter.send([sample_signal], {"run_timestamp": "2025-11-06 14:30 UTC"})

        assert result is True
        # Output captured in capsys (Rich formatting)

    def test_console_output_detailed(self, sample_signal, capsys):
        """Test console detailed output."""
        adapter = ConsoleAdapter(output_format="detailed")

        result = adapter.send([sample_signal], {})

        assert result is True

    def test_console_limits_signals(self, sample_signal):
        """Test console respects max_signals limit."""
        adapter = ConsoleAdapter(max_signals=5)

        # Create 10 signals
        signals = [sample_signal] * 10

        result = adapter.send(signals, {})

        assert result is True
        # Only first 5 should be displayed (visual check in real test)

    def test_console_no_signals(self, capsys):
        """Test console handles empty signal list."""
        adapter = ConsoleAdapter()

        result = adapter.send([], {})

        assert result is True
        captured = capsys.readouterr()
        assert "No signals" in captured.out

    def test_format_signal_type_long(self):
        """Test signal type formatting for LONG."""
        adapter = ConsoleAdapter()

        formatted = adapter._format_signal_type(SignalType.LONG)

        assert "LONG" in formatted
        assert "green" in formatted

    def test_format_signal_type_short(self):
        """Test signal type formatting for SHORT."""
        adapter = ConsoleAdapter()

        formatted = adapter._format_signal_type(SignalType.SHORT)

        assert "SHORT" in formatted
        assert "red" in formatted

    def test_format_confidence_high(self):
        """Test confidence formatting for high confidence."""
        adapter = ConsoleAdapter()

        formatted = adapter._format_confidence(0.85)

        assert "85%" in formatted or "85.0%" in formatted
        assert "green" in formatted

    def test_format_confidence_medium(self):
        """Test confidence formatting for medium confidence."""
        adapter = ConsoleAdapter()

        formatted = adapter._format_confidence(0.65)

        assert "65%" in formatted or "65.0%" in formatted
        assert "yellow" in formatted

    def test_format_confidence_low(self):
        """Test confidence formatting for low confidence."""
        adapter = ConsoleAdapter()

        formatted = adapter._format_confidence(0.45)

        assert "45%" in formatted or "45.0%" in formatted
        assert "dim" in formatted

    def test_format_alignment(self):
        """Test alignment formatting."""
        adapter = ConsoleAdapter()

        # High alignment
        formatted_high = adapter._format_alignment(0.75)
        assert "75%" in formatted_high or "75.0%" in formatted_high
        assert "green" in formatted_high

        # Medium alignment
        formatted_med = adapter._format_alignment(0.55)
        assert "yellow" in formatted_med

        # Low alignment
        formatted_low = adapter._format_alignment(0.35)
        assert "dim" in formatted_low
