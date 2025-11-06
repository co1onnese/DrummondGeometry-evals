"""Discord bot integration with rich embed formatting."""

from __future__ import annotations

import structlog
import requests
from time import sleep
from typing import Any

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
            color = 0x00FF00  # Green for LONG
            emoji = "📈"
        elif signal.signal_type == SignalType.SHORT:
            color = 0xFF0000  # Red for SHORT
            emoji = "📉"
        elif signal.signal_type == SignalType.EXIT_LONG:
            color = 0xFFA500  # Orange for exits
            emoji = "🚪"
        else:  # EXIT_SHORT
            color = 0xFFA500
            emoji = "🚪"

        # Format title
        title = f"{emoji} {signal.symbol} {signal.signal_type.value}"

        # Build field list
        fields = [
            {
                "name": "Entry Price",
                "value": f"${float(signal.entry_price):.2f}",
                "inline": True,
            },
            {
                "name": "Stop Loss",
                "value": f"${float(signal.stop_loss):.2f}",
                "inline": True,
            },
            {
                "name": "Target Price",
                "value": f"${float(signal.target_price):.2f}",
                "inline": True,
            },
            {
                "name": "Confidence",
                "value": self._format_confidence_bar(signal.confidence),
                "inline": True,
            },
            {
                "name": "Signal Strength",
                "value": f"{signal.signal_strength:.1%}",
                "inline": True,
            },
            {
                "name": "R:R Ratio",
                "value": f"{signal.risk_reward_ratio:.2f}",
                "inline": True,
            },
            {
                "name": "HTF Trend",
                "value": f"{signal.htf_trend.value} ({signal.htf_timeframe})",
                "inline": True,
            },
            {
                "name": "Trading TF State",
                "value": f"{signal.trading_tf_state} ({signal.trading_timeframe})",
                "inline": True,
            },
            {
                "name": "Timeframe Alignment",
                "value": f"{signal.timeframe_alignment:.1%}",
                "inline": True,
            },
        ]

        # Add confluence zones if present
        if signal.confluence_zones_count > 0:
            fields.append(
                {
                    "name": "Confluence Zones",
                    "value": f"{signal.confluence_zones_count} support/resistance zones",
                    "inline": False,
                }
            )

        # Add pattern context if present
        if signal.pattern_context and "patterns" in signal.pattern_context:
            patterns = signal.pattern_context["patterns"]
            if patterns:
                pattern_names = ", ".join([p["type"] for p in patterns[:3]])
                fields.append(
                    {"name": "Triggering Patterns", "value": pattern_names, "inline": False}
                )

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
        headers = {"Authorization": f"Bot {self.bot_token}", "Content-Type": "application/json"}

        payload = {"embeds": embeds}

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
