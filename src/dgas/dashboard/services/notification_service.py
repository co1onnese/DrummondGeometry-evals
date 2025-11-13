"""Notification service for alerts and real-time updates.

Manages notification display, rules, and delivery.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
import streamlit as st

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Load .env file from project root
    env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not available, rely on environment variables

# Configure logging
logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """Types of notifications."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    PREDICTION = "prediction"
    SIGNAL = "signal"
    BACKTEST = "backtest"
    SYSTEM = "system"


class NotificationPriority(IntEnum):
    """Notification priority levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Notification:
    """Notification data structure."""
    id: str
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority
    timestamp: datetime
    data: Optional[Dict[str, Any]] = None
    read: bool = False
    auto_dismiss: bool = True
    dismiss_after: int = 5  # seconds


class NotificationService:
    """Service for managing notifications."""

    def __init__(self, max_notifications: int = 100):
        """
        Initialize notification service.

        Args:
            max_notifications: Maximum notifications to keep
        """
        self.max_notifications = max_notifications
        self._notifications: List[Notification] = []
        self._settings: Dict[str, Any] = {}
        self._rules: List[Dict[str, Any]] = []
        self._quiet_hours: Optional[Dict[str, int]] = None

    def initialize(self) -> None:
        """Initialize notification service."""
        if "notification_service" not in st.session_state:
            st.session_state.notification_service = {
                "notifications": [],
                "settings": {
                    "enable_predictions": True,
                    "enable_signals": True,
                    "enable_backtests": True,
                    "enable_system": True,
                    "min_confidence": 0.8,
                    "min_rr_ratio": 1.5,
                    "quiet_hours_start": None,
                    "quiet_hours_end": None,
                },
                "show_notifications": True,
            }

        self._notifications = st.session_state.notification_service["notifications"]
        self._settings = st.session_state.notification_service["settings"]

    def add_notification(
        self,
        notification: Notification,
        check_rules: bool = True,
    ) -> None:
        """
        Add a new notification.

        Args:
            notification: Notification to add
            check_rules: Whether to check alert rules
        """
        self.initialize()

        # Check if should show based on settings
        if not self._should_show_notification(notification):
            return

        # Check alert rules
        if check_rules and not self._check_alert_rules(notification):
            return

        # Add to notifications
        self._notifications.insert(0, notification)

        # Limit total notifications
        if len(self._notifications) > self.max_notifications:
            self._notifications = self._notifications[:self.max_notifications]

        # Save to session state
        st.session_state.notification_service["notifications"] = self._notifications

        logger.info(f"Added notification: {notification.title}")

    def _should_show_notification(self, notification: Notification) -> bool:
        """
        Check if notification should be shown based on settings.

        Args:
            notification: Notification to check

        Returns:
            True if should show
        """
        # Check notification type settings
        if notification.type == NotificationType.PREDICTION and not self._settings.get("enable_predictions"):
            return False
        if notification.type == NotificationType.SIGNAL and not self._settings.get("enable_signals"):
            return False
        if notification.type == NotificationType.BACKTEST and not self._settings.get("enable_backtests"):
            return False
        if notification.type == NotificationType.SYSTEM and not self._settings.get("enable_system"):
            return False

        # Check quiet hours
        if self._is_quiet_hours():
            return notification.priority == NotificationPriority.URGENT

        return True

    def _is_quiet_hours(self) -> bool:
        """
        Check if currently in quiet hours.

        Returns:
            True if in quiet hours
        """
        if not self._settings.get("quiet_hours_start") or not self._settings.get("quiet_hours_end"):
            return False

        now = datetime.now().time()
        start = datetime.strptime(self._settings["quiet_hours_start"], "%H:%M").time()
        end = datetime.strptime(self._settings["quiet_hours_end"], "%H:%M").time()

        if start <= end:
            return start <= now <= end
        else:
            # Quiet hours cross midnight
            return now >= start or now <= end

    def _check_alert_rules(self, notification: Notification) -> bool:
        """
        Check notification against alert rules.

        Args:
            notification: Notification to check

        Returns:
            True if passes all rules
        """
        if notification.type == NotificationType.SIGNAL and notification.data:
            # Check confidence threshold
            confidence = notification.data.get("confidence", 0)
            min_conf = self._settings.get("min_confidence", 0.8)
            if confidence < min_conf:
                return False

            # Check risk-reward ratio
            rr_ratio = notification.data.get("risk_reward_ratio", 0)
            min_rr = self._settings.get("min_rr_ratio", 1.5)
            if rr_ratio < min_rr:
                return False

        return True

    def get_notifications(self, limit: int = 10, unread_only: bool = False) -> List[Notification]:
        """
        Get notifications.

        Args:
            limit: Maximum number to return
            unread_only: Only return unread notifications

        Returns:
            List of notifications
        """
        self.initialize()

        notifications = self._notifications

        if unread_only:
            notifications = [n for n in notifications if not n.read]

        return notifications[:limit]

    def mark_as_read(self, notification_id: str) -> None:
        """
        Mark notification as read.

        Args:
            notification_id: Notification ID
        """
        self.initialize()

        for notification in self._notifications:
            if notification.id == notification_id:
                notification.read = True
                break

        st.session_state.notification_service["notifications"] = self._notifications

    def mark_all_as_read(self) -> None:
        """Mark all notifications as read."""
        self.initialize()

        for notification in self._notifications:
            notification.read = True

        st.session_state.notification_service["notifications"] = self._notifications

    def remove_notification(self, notification_id: str) -> None:
        """
        Remove notification by ID.

        Args:
            notification_id: Notification ID
        """
        self.initialize()

        self._notifications = [n for n in self._notifications if n.id != notification_id]
        st.session_state.notification_service["notifications"] = self._notifications

    def clear_all(self) -> None:
        """Clear all notifications."""
        self.initialize()

        self._notifications = []
        st.session_state.notification_service["notifications"] = self._notifications

    def update_settings(self, settings: Dict[str, Any]) -> None:
        """
        Update notification settings.

        Args:
            settings: New settings
        """
        self.initialize()

        self._settings.update(settings)
        st.session_state.notification_service["settings"] = self._settings

    def get_settings(self) -> Dict[str, Any]:
        """
        Get notification settings.

        Returns:
            Current settings
        """
        self.initialize()
        return self._settings

    def get_unread_count(self) -> int:
        """
        Get count of unread notifications.

        Returns:
            Number of unread notifications
        """
        self.initialize()
        return len([n for n in self._notifications if not n.read])

    # Convenience methods for creating notifications

    def create_prediction_notification(self, prediction_data: Dict[str, Any]) -> None:
        """
        Create and add a prediction notification.

        Args:
            prediction_data: Prediction data
        """
        notification = Notification(
            id=f"pred_{datetime.now().timestamp()}",
            type=NotificationType.PREDICTION,
            title="New Prediction Available",
            message=f"Prediction for {prediction_data.get('symbol', 'Unknown')}",
            priority=NotificationPriority.MEDIUM,
            timestamp=datetime.now(),
            data=prediction_data,
            auto_dismiss=False,
        )
        self.add_notification(notification)

    def create_signal_notification(self, signal_data: Dict[str, Any]) -> None:
        """
        Create and add a signal notification.

        Args:
            signal_data: Signal data
        """
        signal_type = signal_data.get("signal_type", "Unknown")
        confidence = signal_data.get("confidence", 0)
        symbol = signal_data.get("symbol", "Unknown")

        priority = NotificationPriority.HIGH if confidence > 0.9 else NotificationPriority.MEDIUM

        notification = Notification(
            id=f"signal_{datetime.now().timestamp()}",
            type=NotificationType.SIGNAL,
            title=f"New {signal_type} Signal",
            message=f"{signal_type} signal for {symbol} (confidence: {confidence:.2f})",
            priority=priority,
            timestamp=datetime.now(),
            data=signal_data,
            auto_dismiss=priority < NotificationPriority.HIGH,
        )
        self.add_notification(notification)
        
        # Also send to Discord if configured
        self._send_to_discord(notification)

    def create_backtest_notification(self, backtest_data: Dict[str, Any]) -> None:
        """
        Create and add a backtest notification.

        Args:
            backtest_data: Backtest data
        """
        backtest_id = backtest_data.get("backtest_id", "Unknown")
        total_return = backtest_data.get("total_return", 0)

        priority = NotificationPriority.HIGH if total_return > 10 else NotificationPriority.MEDIUM

        notification = Notification(
            id=f"backtest_{datetime.now().timestamp()}",
            type=NotificationType.BACKTEST,
            title="Backtest Completed",
            message=f"Backtest {backtest_id} completed (Return: {total_return:.2f}%)",
            priority=priority,
            timestamp=datetime.now(),
            data=backtest_data,
            auto_dismiss=True,
        )
        self.add_notification(notification)

    def create_system_notification(
        self,
        message: str,
        notification_type: NotificationType = NotificationType.SYSTEM,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
    ) -> None:
        """
        Create and add a system notification.

        Args:
            message: Notification message
            notification_type: Type of notification
            priority: Priority level
        """
        notification = Notification(
            id=f"system_{datetime.now().timestamp()}",
            type=notification_type,
            title="System Alert",
            message=message,
            priority=priority,
            timestamp=datetime.now(),
            auto_dismiss=priority < NotificationPriority.HIGH,
        )
        self.add_notification(notification)
        
        # Also send to Discord if configured
        self._send_to_discord(notification)

    def _send_to_discord(self, notification: Notification) -> None:
        """
        Send notification to Discord if configured.
        
        Args:
            notification: Notification to send
        """
        # Try multiple ways to get Discord credentials
        bot_token = os.getenv("DGAS_DISCORD_BOT_TOKEN")
        channel_id = os.getenv("DGAS_DISCORD_CHANNEL_ID")
        
        # If not found, try loading from .env file directly
        if not bot_token or not channel_id:
            try:
                from dotenv import load_dotenv
                # Try to find .env file
                env_paths = [
                    Path("/opt/DrummondGeometry-evals/.env"),
                    Path(__file__).parent.parent.parent.parent.parent / ".env",
                    Path.cwd() / ".env",
                ]
                for env_path in env_paths:
                    if env_path.exists():
                        load_dotenv(env_path, override=False)
                        break
                
                # Try again after loading
                bot_token = os.getenv("DGAS_DISCORD_BOT_TOKEN") or bot_token
                channel_id = os.getenv("DGAS_DISCORD_CHANNEL_ID") or channel_id
            except ImportError:
                pass  # python-dotenv not available
        
        if not bot_token or not channel_id:
            logger.warning("Discord not configured - bot_token or channel_id missing. Skipping Discord notification.")
            return
        
        logger.info(f"Sending notification to Discord: {notification.title}")
        try:
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            headers = {
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json"
            }
            
            # Create a simple embed for the notification
            color_map = {
                NotificationType.INFO: 0x3498db,      # Blue
                NotificationType.SUCCESS: 0x2ecc71,   # Green
                NotificationType.WARNING: 0xf39c12,   # Orange
                NotificationType.ERROR: 0xe74c3c,     # Red
                NotificationType.SYSTEM: 0x95a5a6,    # Gray
                NotificationType.SIGNAL: 0x9b59b6,    # Purple
                NotificationType.PREDICTION: 0x1abc9c, # Teal
                NotificationType.BACKTEST: 0x34495e,   # Dark blue-gray
            }
            
            embed = {
                "title": notification.title,
                "description": notification.message,
                "color": color_map.get(notification.type, 0x95a5a6),
                "timestamp": notification.timestamp.isoformat(),
                "footer": {
                    "text": f"DGAS Dashboard - {notification.type.value.upper()}"
                }
            }
            
            # Add signal data if available
            if notification.data and notification.type == NotificationType.SIGNAL:
                fields = []
                if "symbol" in notification.data:
                    fields.append({"name": "Symbol", "value": notification.data["symbol"], "inline": True})
                if "confidence" in notification.data:
                    fields.append({"name": "Confidence", "value": f"{notification.data['confidence']:.1%}", "inline": True})
                if "risk_reward_ratio" in notification.data:
                    fields.append({"name": "R:R Ratio", "value": f"{notification.data['risk_reward_ratio']:.2f}", "inline": True})
                if fields:
                    embed["fields"] = fields
            
            payload = {"embeds": [embed]}
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Discord notification sent successfully: {notification.title} (Message ID: {result.get('id')})")
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"Discord API HTTP error: {e.response.status_code} - {e.response.text[:200]}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Discord notification (network error): {e}")
        except Exception as e:
            logger.error(f"Error sending to Discord: {e}", exc_info=True)

    def export_notifications(self, filepath: Path) -> None:
        """
        Export notifications to JSON file.

        Args:
            filepath: Path to save file
        """
        self.initialize()

        export_data = {
            "exported_at": datetime.now().isoformat(),
            "notifications": [
                {
                    **asdict(n),
                    "timestamp": n.timestamp.isoformat(),
                    "type": n.type.value,
                    "priority": n.priority.value,
                }
                for n in self._notifications
            ],
            "settings": self._settings,
        }

        with open(filepath, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported {len(self._notifications)} notifications to {filepath}")


# Global service instance
_service_instance: Optional[NotificationService] = None


def get_service() -> NotificationService:
    """
    Get the global notification service instance.

    Returns:
        Service instance
    """
    global _service_instance

    if _service_instance is None:
        _service_instance = NotificationService()

    return _service_instance


# Convenience functions

def add_notification(
    type: NotificationType,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.MEDIUM,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Add a notification.

    Args:
        type: Notification type
        title: Notification title
        message: Notification message
        priority: Priority level
        data: Additional data
    """
    service = get_service()

    notification = Notification(
        id=f"{type.value}_{datetime.now().timestamp()}",
        type=type,
        title=title,
        message=message,
        priority=priority,
        timestamp=datetime.now(),
        data=data,
    )

    service.add_notification(notification)


if __name__ == "__main__":
    # Test the service
    service = NotificationService()
    service.initialize()

    service.create_signal_notification({
        "symbol": "BTC/USD",
        "signal_type": "BUY",
        "confidence": 0.95,
        "risk_reward_ratio": 2.5,
    })

    notifications = service.get_notifications(limit=5)
    print(f"Total notifications: {len(notifications)}")
