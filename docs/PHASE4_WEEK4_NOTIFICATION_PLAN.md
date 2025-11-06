# Phase 4 Week 4: Notification System - Implementation Plan

**Date**: November 6, 2025
**Phase**: 4 (Prediction System)
**Week**: 4
**Focus**: Discord + Console Notification System

---

## Executive Summary

Week 4 implements a **production-ready notification system** focused on **Discord as the primary channel** with console output for immediate local feedback. The system will deliver trading signals with rich formatting, proper error handling, and rate limiting.

**Key Decisions** (User-Approved):
- **Discord bot token and channel ID**: Ready via environment variables
- **Channels**: Discord (primary) + Console (local feedback)
- **Embed colors**: Green (0x00ff00) for LONG, Red (0xff0000) for SHORT
- **Message format**: Individual embeds (one per signal)

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                    Notification System                          │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│  NotificationRouter                                             │
│    • Routes signals to configured channels                      │
│    • Applies per-channel filtering (confidence thresholds)      │
│    • Tracks delivery status                                     │
│    • Handles errors gracefully                                  │
└──────────────────┬─────────────────────────────────────────────┘
                   │
         ┌─────────┴─────────┐
         ↓                   ↓
┌──────────────────┐   ┌──────────────────┐
│ DiscordAdapter   │   │ ConsoleAdapter   │
│  • Rich embeds   │   │  • Rich tables   │
│  • Rate limiting │   │  • Color output  │
│  • Error retry   │   │  • Summary view  │
│  • Bot API       │   │  • Immediate     │
└──────────────────┘   └──────────────────┘
```

---

## Implementation Tasks

### Task 1: Notification Router Infrastructure

**File**: `src/dgas/prediction/notifications/router.py`

#### 1.1 NotificationConfig Dataclass

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class NotificationConfig:
    """Configuration for notification delivery."""

    # Enabled channels
    enabled_channels: list[str] = field(default_factory=lambda: ["console", "discord"])

    # Discord configuration
    discord_bot_token: str | None = None  # From env: DGAS_DISCORD_BOT_TOKEN
    discord_channel_id: str | None = None  # From env: DGAS_DISCORD_CHANNEL_ID
    discord_min_confidence: float = 0.5

    # Console configuration
    console_max_signals: int = 10
    console_format: str = "summary"  # "summary" or "detailed"

    # Webhook configuration (optional, not implementing in Week 4)
    webhook_urls: list[str] = field(default_factory=list)
    webhook_min_confidence: float = 0.6

    @classmethod
    def from_env(cls) -> "NotificationConfig":
        """Create config from environment variables."""
        import os
        return cls(
            discord_bot_token=os.getenv("DGAS_DISCORD_BOT_TOKEN"),
            discord_channel_id=os.getenv("DGAS_DISCORD_CHANNEL_ID"),
        )
```

#### 1.2 NotificationAdapter Abstract Base

```python
from abc import ABC, abstractmethod
from typing import Any
from ..engine import GeneratedSignal

class NotificationAdapter(ABC):
    """Base class for notification channel implementations."""

    @abstractmethod
    def send(
        self,
        signals: list[GeneratedSignal],
        metadata: dict[str, Any],
    ) -> bool:
        """
        Send notifications for signals.

        Args:
            signals: List of generated signals to notify
            metadata: Run metadata (timestamp, run_id, etc.)

        Returns:
            True if all notifications sent successfully, False otherwise
        """
        pass

    @abstractmethod
    def format_message(
        self,
        signals: list[GeneratedSignal],
    ) -> Any:
        """Format signals for channel (string, dict, etc.)."""
        pass

    def should_notify(self, signal: GeneratedSignal, min_confidence: float) -> bool:
        """Check if signal meets threshold for notification."""
        return signal.confidence >= min_confidence
```

#### 1.3 NotificationRouter Class

```python
import structlog
from typing import Dict

logger = structlog.get_logger(__name__)

class NotificationRouter:
    """Routes signals to configured notification channels."""

    def __init__(
        self,
        config: NotificationConfig,
        adapters: dict[str, NotificationAdapter],
    ):
        """
        Initialize router with config and channel adapters.

        Args:
            config: Notification configuration
            adapters: Map of channel name -> adapter instance
        """
        self.config = config
        self.adapters = adapters
        self.logger = logger.bind(component="notification_router")

    def send_notifications(
        self,
        signals: list[GeneratedSignal],
        run_metadata: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Send notifications for signals through all enabled channels.

        Args:
            signals: List of generated signals
            run_metadata: Metadata from prediction run (run_id, timestamp, etc.)

        Returns:
            Map of channel name -> success status
        """
        if not signals:
            self.logger.info("no_signals_to_notify")
            return {}

        results = {}

        for channel in self.config.enabled_channels:
            adapter = self.adapters.get(channel)
            if not adapter:
                self.logger.warning(
                    "adapter_not_found",
                    channel=channel,
                )
                results[channel] = False
                continue

            # Filter signals by channel-specific confidence threshold
            filtered_signals = self._filter_signals_for_channel(signals, channel)

            if not filtered_signals:
                self.logger.info(
                    "no_signals_after_filtering",
                    channel=channel,
                    original_count=len(signals),
                )
                results[channel] = True
                continue

            # Send notifications
            try:
                success = adapter.send(filtered_signals, run_metadata)
                results[channel] = success

                if success:
                    self.logger.info(
                        "notifications_sent",
                        channel=channel,
                        signal_count=len(filtered_signals),
                    )
                else:
                    self.logger.error(
                        "notifications_failed",
                        channel=channel,
                        signal_count=len(filtered_signals),
                    )
            except Exception as e:
                self.logger.exception(
                    "notification_exception",
                    channel=channel,
                    error=str(e),
                )
                results[channel] = False

        return results

    def _filter_signals_for_channel(
        self,
        signals: list[GeneratedSignal],
        channel: str,
    ) -> list[GeneratedSignal]:
        """Filter signals based on channel-specific thresholds."""
        if channel == "discord":
            min_conf = self.config.discord_min_confidence
        elif channel == "console":
            min_conf = 0.0  # Console shows all signals
        else:
            min_conf = 0.5  # Default threshold

        return [s for s in signals if s.confidence >= min_conf]
```

---

### Task 2: Discord Adapter Implementation

**File**: `src/dgas/prediction/notifications/adapters/discord.py`

#### 2.1 Discord Embed Creation

```python
from datetime import datetime, timezone
from typing import Any
import requests
import structlog
from time import sleep

from dgas import get_version
from dgas.prediction.engine import GeneratedSignal, SignalType
from ..router import NotificationAdapter

logger = structlog.get_logger(__name__)

class DiscordAdapter(NotificationAdapter):
    """Discord bot integration with rich embed formatting."""

    def __init__(
        self,
        bot_token: str,
        channel_id: str,
        rate_limit_delay: float = 1.0,  # Delay between messages (seconds)
        timeout: int = 10,
    ):
        """
        Initialize Discord bot connection.

        Args:
            bot_token: Discord bot token (from DGAS_DISCORD_BOT_TOKEN)
            channel_id: Discord channel ID to post to
            rate_limit_delay: Delay between messages to avoid rate limits
            timeout: HTTP request timeout in seconds
        """
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self.logger = logger.bind(component="discord_adapter")

        # Validate configuration
        if not self.bot_token:
            raise ValueError("Discord bot token is required")
        if not self.channel_id:
            raise ValueError("Discord channel ID is required")

    def send(
        self,
        signals: list[GeneratedSignal],
        metadata: dict[str, Any],
    ) -> bool:
        """Send signals as individual Discord embeds."""
        if not signals:
            return True

        self.logger.info(
            "sending_discord_notifications",
            signal_count=len(signals),
            channel_id=self.channel_id,
        )

        success_count = 0

        for signal in signals:
            try:
                embed = self._create_embed(signal, metadata)
                self._send_to_discord([embed])  # Send one embed at a time
                success_count += 1

                # Rate limiting: delay between messages
                if signal != signals[-1]:  # Don't delay after last signal
                    sleep(self.rate_limit_delay)

            except Exception as e:
                self.logger.error(
                    "discord_send_failed",
                    symbol=signal.symbol,
                    error=str(e),
                )

        # Consider success if >80% of signals sent
        success_rate = success_count / len(signals)
        return success_rate >= 0.8

    def format_message(
        self,
        signals: list[GeneratedSignal],
    ) -> list[dict]:
        """Create Discord embed objects for signals."""
        return [self._create_embed(signal, {}) for signal in signals]

    def _create_embed(
        self,
        signal: GeneratedSignal,
        metadata: dict[str, Any],
    ) -> dict:
        """Create Discord embed object for a single signal."""

        # Determine embed color based on signal type
        if signal.signal_type == SignalType.LONG:
            color = 0x00ff00  # Green for LONG
            emoji = "📈"
        elif signal.signal_type == SignalType.SHORT:
            color = 0xff0000  # Red for SHORT
            emoji = "📉"
        elif signal.signal_type == SignalType.EXIT_LONG:
            color = 0xffa500  # Orange for exits
            emoji = "🚪"
        else:  # EXIT_SHORT
            color = 0xffa500
            emoji = "🚪"

        # Format title
        title = f"{emoji} {signal.symbol} {signal.signal_type.value}"

        # Build field list
        fields = [
            {
                "name": "Entry Price",
                "value": f"${float(signal.entry_price):.2f}",
                "inline": True
            },
            {
                "name": "Stop Loss",
                "value": f"${float(signal.stop_loss):.2f}",
                "inline": True
            },
            {
                "name": "Target Price",
                "value": f"${float(signal.target_price):.2f}",
                "inline": True
            },
            {
                "name": "Confidence",
                "value": self._format_confidence_bar(signal.confidence),
                "inline": True
            },
            {
                "name": "Signal Strength",
                "value": f"{signal.signal_strength:.1%}",
                "inline": True
            },
            {
                "name": "R:R Ratio",
                "value": f"{signal.risk_reward_ratio:.2f}",
                "inline": True
            },
            {
                "name": "HTF Trend",
                "value": f"{signal.htf_trend.value} ({signal.htf_timeframe})",
                "inline": True
            },
            {
                "name": "Trading TF State",
                "value": f"{signal.trading_tf_state} ({signal.trading_timeframe})",
                "inline": True
            },
            {
                "name": "Timeframe Alignment",
                "value": f"{signal.timeframe_alignment:.1%}",
                "inline": True
            },
        ]

        # Add confluence zones if present
        if signal.confluence_zones_count > 0:
            fields.append({
                "name": "Confluence Zones",
                "value": f"{signal.confluence_zones_count} support/resistance zones",
                "inline": False
            })

        # Add pattern context if present
        if signal.pattern_context and "patterns" in signal.pattern_context:
            patterns = signal.pattern_context["patterns"]
            if patterns:
                pattern_names = ", ".join([p["type"] for p in patterns[:3]])
                fields.append({
                    "name": "Triggering Patterns",
                    "value": pattern_names,
                    "inline": False
                })

        # Create embed
        embed = {
            "title": title,
            "color": color,
            "fields": fields,
            "footer": {
                "text": f"Generated: {signal.signal_timestamp.strftime('%Y-%m-%d %H:%M UTC')} | DGAS v{get_version()}"
            },
            "timestamp": signal.signal_timestamp.isoformat(),
        }

        return embed

    def _format_confidence_bar(self, confidence: float) -> str:
        """Create visual confidence bar using Unicode blocks."""
        # Use filled/empty blocks to show confidence visually
        filled_blocks = int(confidence * 10)
        empty_blocks = 10 - filled_blocks
        bar = "█" * filled_blocks + "░" * empty_blocks
        return f"{bar} {confidence:.0%}"

    def _send_to_discord(self, embeds: list[dict]) -> None:
        """Send embeds via Discord API."""
        url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "embeds": embeds
        }

        self.logger.debug(
            "posting_to_discord",
            url=url,
            embed_count=len(embeds),
        )

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )

        if response.status_code == 429:  # Rate limited
            retry_after = response.json().get("retry_after", 1.0)
            self.logger.warning(
                "discord_rate_limited",
                retry_after=retry_after,
            )
            sleep(retry_after)
            # Retry once
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

        response.raise_for_status()

        self.logger.debug(
            "discord_post_success",
            status_code=response.status_code,
        )
```

---

### Task 3: Console Adapter Implementation

**File**: `src/dgas/prediction/notifications/adapters/console.py`

#### 3.1 Rich Table Output

```python
from typing import Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

import structlog

from dgas.prediction.engine import GeneratedSignal, SignalType
from ..router import NotificationAdapter

logger = structlog.get_logger(__name__)

class ConsoleAdapter(NotificationAdapter):
    """Rich console table output for signals."""

    def __init__(
        self,
        max_signals: int = 10,
        output_format: str = "summary",
    ):
        """
        Initialize console adapter.

        Args:
            max_signals: Maximum number of signals to display
            output_format: "summary" or "detailed"
        """
        self.max_signals = max_signals
        self.output_format = output_format
        self.console = Console()
        self.logger = logger.bind(component="console_adapter")

    def send(
        self,
        signals: list[GeneratedSignal],
        metadata: dict[str, Any],
    ) -> bool:
        """Display signals in formatted Rich table."""
        if not signals:
            self.console.print("[yellow]No signals generated this cycle.[/yellow]")
            return True

        # Limit signals if configured
        display_signals = signals[:self.max_signals]

        if self.output_format == "summary":
            self._display_summary_table(display_signals, metadata)
        else:
            self._display_detailed_table(display_signals, metadata)

        # Show truncation warning if needed
        if len(signals) > self.max_signals:
            self.console.print(
                f"\n[dim]... and {len(signals) - self.max_signals} more signals "
                f"(showing top {self.max_signals})[/dim]"
            )

        return True

    def format_message(
        self,
        signals: list[GeneratedSignal],
    ) -> str:
        """Not used for console (uses Rich directly)."""
        return ""

    def _display_summary_table(
        self,
        signals: list[GeneratedSignal],
        metadata: dict[str, Any],
    ) -> None:
        """Display signals in compact summary table."""

        # Create title panel
        run_time = metadata.get("run_timestamp", "Unknown")
        title = Panel(
            f"[bold cyan]🎯 Trading Signals Generated[/bold cyan]\n"
            f"[dim]{run_time}[/dim]",
            border_style="cyan",
        )
        self.console.print(title)

        # Create table
        table = Table(title="Signal Summary", show_header=True, header_style="bold magenta")

        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Type", style="bold", width=6)
        table.add_column("Entry", justify="right", style="green", width=10)
        table.add_column("Stop", justify="right", style="red", width=10)
        table.add_column("Target", justify="right", style="blue", width=10)
        table.add_column("Conf", justify="right", width=8)
        table.add_column("R:R", justify="right", width=6)
        table.add_column("Align", justify="right", width=6)

        for signal in signals:
            # Color signal type
            signal_type_text = self._format_signal_type(signal.signal_type)

            # Color confidence
            conf_text = self._format_confidence(signal.confidence)

            # Color alignment
            align_text = self._format_alignment(signal.timeframe_alignment)

            table.add_row(
                signal.symbol,
                signal_type_text,
                f"${float(signal.entry_price):.2f}",
                f"${float(signal.stop_loss):.2f}",
                f"${float(signal.target_price):.2f}",
                conf_text,
                f"{signal.risk_reward_ratio:.2f}",
                align_text,
            )

        self.console.print(table)

    def _display_detailed_table(
        self,
        signals: list[GeneratedSignal],
        metadata: dict[str, Any],
    ) -> None:
        """Display signals with full details."""

        for i, signal in enumerate(signals, 1):
            # Create signal panel
            signal_type_color = "green" if signal.signal_type == SignalType.LONG else "red"

            title = (
                f"[{signal_type_color}]Signal {i}/{len(signals)}: "
                f"{signal.symbol} {signal.signal_type.value}[/{signal_type_color}]"
            )

            content = (
                f"[bold]Entry:[/bold] ${float(signal.entry_price):.2f}  "
                f"[bold]Stop:[/bold] ${float(signal.stop_loss):.2f}  "
                f"[bold]Target:[/bold] ${float(signal.target_price):.2f}\n"
                f"[bold]Confidence:[/bold] {self._format_confidence(signal.confidence)}  "
                f"[bold]Strength:[/bold] {signal.signal_strength:.1%}  "
                f"[bold]Alignment:[/bold] {self._format_alignment(signal.timeframe_alignment)}\n"
                f"[bold]HTF Trend:[/bold] {signal.htf_trend.value} ({signal.htf_timeframe})  "
                f"[bold]Trading TF:[/bold] {signal.trading_tf_state} ({signal.trading_timeframe})\n"
                f"[bold]R:R:[/bold] {signal.risk_reward_ratio:.2f}  "
                f"[bold]Confluence Zones:[/bold] {signal.confluence_zones_count}"
            )

            # Add pattern context if available
            if signal.pattern_context and "patterns" in signal.pattern_context:
                patterns = signal.pattern_context["patterns"]
                if patterns:
                    pattern_names = ", ".join([p["type"] for p in patterns[:3]])
                    content += f"\n[bold]Patterns:[/bold] {pattern_names}"

            panel = Panel(
                content,
                title=title,
                border_style=signal_type_color,
            )
            self.console.print(panel)

    def _format_signal_type(self, signal_type: SignalType) -> str:
        """Format signal type with color."""
        if signal_type == SignalType.LONG:
            return "[green]LONG[/green]"
        elif signal_type == SignalType.SHORT:
            return "[red]SHORT[/red]"
        elif signal_type == SignalType.EXIT_LONG:
            return "[yellow]EXIT_L[/yellow]"
        else:
            return "[yellow]EXIT_S[/yellow]"

    def _format_confidence(self, confidence: float) -> str:
        """Format confidence with color."""
        if confidence >= 0.8:
            return f"[bold green]{confidence:.1%}[/bold green]"
        elif confidence >= 0.6:
            return f"[yellow]{confidence:.1%}[/yellow]"
        else:
            return f"[dim]{confidence:.1%}[/dim]"

    def _format_alignment(self, alignment: float) -> str:
        """Format alignment with color."""
        if alignment >= 0.7:
            return f"[bold green]{alignment:.1%}[/bold green]"
        elif alignment >= 0.5:
            return f"[yellow]{alignment:.1%}[/yellow]"
        else:
            return f"[dim]{alignment:.1%}[/dim]"
```

---

### Task 4: Integration with Prediction Scheduler

**File**: `src/dgas/prediction/scheduler.py` (update)

Add notification delivery after signal generation:

```python
# In PredictionScheduler._execute_cycle() method:

def _execute_cycle(self) -> PredictionRunResult:
    """Execute full prediction cycle."""
    start_time = datetime.now(timezone.utc)

    try:
        # ... existing code for data refresh and signal generation ...

        # NEW: Send notifications
        if result.signals_generated > 0:
            notification_start = time.time()

            # Import notification components
            from .notifications.router import NotificationRouter, NotificationConfig
            from .notifications.adapters.discord import DiscordAdapter
            from .notifications.adapters.console import ConsoleAdapter

            # Create config from environment
            config = NotificationConfig.from_env()

            # Create adapters
            adapters = {}

            if "console" in config.enabled_channels:
                adapters["console"] = ConsoleAdapter(
                    max_signals=config.console_max_signals,
                    output_format=config.console_format,
                )

            if "discord" in config.enabled_channels and config.discord_bot_token:
                adapters["discord"] = DiscordAdapter(
                    bot_token=config.discord_bot_token,
                    channel_id=config.discord_channel_id,
                )

            # Send notifications
            router = NotificationRouter(config, adapters)
            delivery_results = router.send_notifications(
                signals=generated_signals,
                run_metadata={
                    "run_id": result.run_id,
                    "run_timestamp": start_time.isoformat(),
                    "symbols_processed": result.symbols_processed,
                },
            )

            notification_ms = int((time.time() - notification_start) * 1000)

            # Log delivery results
            for channel, success in delivery_results.items():
                if success:
                    logger.info(
                        "notifications_delivered",
                        channel=channel,
                        signal_count=result.signals_generated,
                    )
                else:
                    logger.error(
                        "notification_delivery_failed",
                        channel=channel,
                    )

        return result

    except Exception as e:
        logger.exception("cycle_execution_failed", error=str(e))
        raise
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/prediction/test_notifications.py`

```python
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

class TestNotificationConfig:
    def test_default_config(self):
        """Test default configuration."""
        config = NotificationConfig()
        assert "console" in config.enabled_channels
        assert "discord" in config.enabled_channels

    def test_from_env(self, monkeypatch):
        """Test config creation from environment."""
        monkeypatch.setenv("DGAS_DISCORD_BOT_TOKEN", "test_token_123")
        monkeypatch.setenv("DGAS_DISCORD_CHANNEL_ID", "1234567890")

        config = NotificationConfig.from_env()
        assert config.discord_bot_token == "test_token_123"
        assert config.discord_channel_id == "1234567890"

class TestNotificationRouter:
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

    def test_send_notifications_filters_by_confidence(self, sample_signal):
        """Test signals filtered by channel confidence threshold."""
        low_conf_signal = sample_signal
        low_conf_signal.confidence = 0.4  # Below discord threshold (0.5)

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

class TestDiscordAdapter:
    def test_create_embed_long_signal(self, sample_signal):
        """Test Discord embed creation for LONG signal."""
        adapter = DiscordAdapter(
            bot_token="test_token",
            channel_id="123456",
        )

        embed = adapter._create_embed(sample_signal, {})

        assert "AAPL" in embed["title"]
        assert "LONG" in embed["title"]
        assert embed["color"] == 0x00ff00  # Green
        assert len(embed["fields"]) >= 9  # All required fields

    def test_create_embed_short_signal(self, sample_signal):
        """Test Discord embed creation for SHORT signal."""
        sample_signal.signal_type = SignalType.SHORT

        adapter = DiscordAdapter(
            bot_token="test_token",
            channel_id="123456",
        )

        embed = adapter._create_embed(sample_signal, {})

        assert "SHORT" in embed["title"]
        assert embed["color"] == 0xff0000  # Red

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
        )

        result = adapter.send([sample_signal], {})

        assert result is True
        assert mock_post.call_count == 2  # Initial + retry

    def test_discord_adapter_requires_credentials(self):
        """Test Discord adapter validates credentials."""
        with pytest.raises(ValueError, match="bot token is required"):
            DiscordAdapter(bot_token="", channel_id="123")

        with pytest.raises(ValueError, match="channel ID is required"):
            DiscordAdapter(bot_token="token", channel_id="")

class TestConsoleAdapter:
    def test_console_output_summary(self, sample_signal, capsys):
        """Test console summary output."""
        adapter = ConsoleAdapter(output_format="summary")

        result = adapter.send([sample_signal], {"run_timestamp": "2025-11-06 14:30 UTC"})

        assert result is True
        # Rich output captured in capsys

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
```

---

## Implementation Checklist

### Day 1-2: Notification Infrastructure
- [x] Plan notification system architecture
- [ ] Implement `NotificationConfig` dataclass
- [ ] Implement `NotificationAdapter` abstract base
- [ ] Implement `NotificationRouter` class
- [ ] Write unit tests for router
- [ ] Test configuration from environment variables

### Day 3-4: Discord Adapter
- [ ] Implement `DiscordAdapter` class
- [ ] Implement embed creation logic
- [ ] Implement confidence bar formatting
- [ ] Implement rate limiting with retries
- [ ] Write unit tests for Discord adapter
- [ ] Test with mock Discord API
- [ ] Test rate limit handling

### Day 5: Console Adapter
- [ ] Implement `ConsoleAdapter` class
- [ ] Implement summary table formatting
- [ ] Implement detailed panel formatting
- [ ] Implement signal limit logic
- [ ] Write unit tests for console adapter
- [ ] Test Rich output rendering

### Day 6: Integration
- [ ] Update `PredictionScheduler` to call notification system
- [ ] Add notification timing to performance metrics
- [ ] Test end-to-end notification flow
- [ ] Update `prediction/__init__.py` exports
- [ ] Update `llms.txt` with Week 4 architecture

### Day 7: Testing & Documentation
- [ ] Write integration tests
- [ ] Test with real Discord bot (optional)
- [ ] Create Week 4 completion summary
- [ ] Update configuration documentation
- [ ] Add Discord setup instructions to README

---

## Environment Variables

Add to `.env`:

```bash
# Discord Configuration
DGAS_DISCORD_BOT_TOKEN=your_discord_bot_token_here
DGAS_DISCORD_CHANNEL_ID=your_channel_id_here
```

---

## Success Criteria

**Functional Requirements**:
- ✅ Notification router dispatches to configured channels
- ✅ Discord adapter sends rich embeds with proper formatting
- ✅ Discord embeds use correct colors (Green for LONG, Red for SHORT)
- ✅ Discord adapter handles rate limits with retries
- ✅ Console adapter displays signals in formatted tables
- ✅ Console adapter supports summary and detailed views
- ✅ Configuration loads from environment variables
- ✅ All unit tests pass (>90% coverage)

**Performance Requirements**:
- ✅ Notification delivery completes in <5 seconds for 10 signals
- ✅ Discord rate limiting prevents 429 errors
- ✅ Console output renders without blocking

**Quality Requirements**:
- ✅ Error handling for network failures
- ✅ Graceful degradation if channel unavailable
- ✅ Comprehensive logging with structlog
- ✅ Type hints for all functions
- ✅ Documentation for Discord setup

---

## Next Steps (Week 5)

After Week 4 completion, proceed to **Week 5: Monitoring & Calibration**:
- Performance tracker for latency metrics
- Calibration engine for signal outcome evaluation
- Calibration reports by confidence bucket
- SLA compliance monitoring

---

**Document Status**: Ready for Implementation
**Approved**: User confirmed Discord + Console channels
**Start Date**: November 6, 2025
