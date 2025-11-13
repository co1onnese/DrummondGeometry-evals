"""Notification router for delivering trading signals through multiple channels."""

from __future__ import annotations

import os
import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..engine import GeneratedSignal

logger = structlog.get_logger(__name__)

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    # Try to load .env from project root
    env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.debug("Loaded .env file", path=str(env_path))
    else:
        # Fallback: try current directory
        load_dotenv()
except ImportError:
    # python-dotenv not installed, skip
    pass
except Exception as e:
    logger.warning("Failed to load .env file", error=str(e))


@dataclass
class NotificationConfig:
    """Configuration for notification delivery."""

    # Enabled channels (Discord is primary)
    enabled_channels: list[str] = field(default_factory=lambda: ["discord"])

    # Discord configuration
    discord_bot_token: str | None = None  # From env: DGAS_DISCORD_BOT_TOKEN
    discord_channel_id: str | None = None  # From env: DGAS_DISCORD_CHANNEL_ID
    discord_min_confidence: float = 0.65  # Match production config (65% minimum)

    # Console configuration
    console_max_signals: int = 10
    console_format: str = "summary"  # "summary" or "detailed"

    # Webhook configuration (optional, future implementation)
    webhook_urls: list[str] = field(default_factory=list)
    webhook_min_confidence: float = 0.6

    @classmethod
    def from_env(cls) -> NotificationConfig:
        """Create config from environment variables."""
        # Discord is the ONLY notification channel (no console, no email)
        enabled_channels = ["discord"]
        
        return cls(
            enabled_channels=enabled_channels,
            discord_bot_token=os.getenv("DGAS_DISCORD_BOT_TOKEN"),
            discord_channel_id=os.getenv("DGAS_DISCORD_CHANNEL_ID"),
        )


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
            min_conf = self.config.discord_min_confidence  # 0.65 (65%) from config
        elif channel == "console":
            min_conf = 0.0  # Console shows all signals (if enabled)
        elif channel == "webhook":
            min_conf = self.config.webhook_min_confidence
        else:
            min_conf = 0.5  # Default threshold

        filtered = [s for s in signals if s.confidence >= min_conf]
        
        # Log filtering results for debugging
        if channel == "discord" and len(signals) > 0:
            logger.debug(
                "discord_signal_filtering",
                total_signals=len(signals),
                filtered_signals=len(filtered),
                min_confidence=min_conf,
                signals_above_threshold=[s.symbol for s in filtered],
            )
        
        return filtered

    def get_notification_metadata(
        self,
        signals: list[GeneratedSignal],
        delivery_results: dict[str, bool],
    ) -> dict[str, dict[str, Any]]:
        """
        Get notification metadata for each signal after delivery.

        Args:
            signals: List of generated signals
            delivery_results: Dictionary of channel delivery results

        Returns:
            Dictionary mapping signal symbol to notification metadata
            with keys: notification_sent, notification_channels, notification_timestamp
        """
        from datetime import datetime, timezone

        successful_channels = [ch for ch, success in delivery_results.items() if success]
        notification_timestamp = datetime.now(timezone.utc)

        metadata = {}
        for signal in signals:
            # Check which channels this signal was sent to
            sent_channels = []
            for channel in successful_channels:
                filtered = self._filter_signals_for_channel([signal], channel)
                if filtered:  # Signal passed filter for this channel
                    sent_channels.append(channel)

            metadata[signal.symbol] = {
                "notification_sent": len(sent_channels) > 0,
                "notification_channels": sent_channels if sent_channels else None,
                "notification_timestamp": notification_timestamp if sent_channels else None,
            }

        return metadata
