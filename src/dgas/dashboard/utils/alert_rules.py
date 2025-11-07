"""Alert rules engine for automatic notifications.

Defines and evaluates rules for generating alerts.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Callable

from dgas.dashboard.services.notification_service import (
    get_service,
    NotificationType,
    NotificationPriority,
)

logger = logging.getLogger(__name__)


class AlertRule:
    """Represents a single alert rule."""

    def __init__(
        self,
        name: str,
        description: str,
        condition: Callable[[Dict[str, Any]], bool],
        notification_type: NotificationType,
        priority: NotificationPriority,
        title_template: str,
        message_template: str,
    ):
        """
        Initialize alert rule.

        Args:
            name: Rule name
            description: Rule description
            condition: Function that returns True if rule should trigger
            notification_type: Type of notification
            priority: Priority level
            title_template: Template for notification title
            message_template: Template for notification message
        """
        self.name = name
        self.description = description
        self.condition = condition
        self.notification_type = notification_type
        self.priority = priority
        self.title_template = title_template
        self.message_template = message_template

    def evaluate(self, data: Dict[str, Any]) -> bool:
        """
        Evaluate if rule should trigger.

        Args:
            data: Data to evaluate

        Returns:
            True if rule should trigger
        """
        try:
            return self.condition(data)
        except Exception as e:
            logger.error(f"Error evaluating rule {self.name}: {e}")
            return False

    def create_notification(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create notification data from rule.

        Args:
            data: Data to format into notification

        Returns:
            Notification data
        """
        return {
            "title": self.title_template.format(**data),
            "message": self.message_template.format(**data),
            "data": data,
        }


class AlertRulesEngine:
    """Engine for managing and evaluating alert rules."""

    def __init__(self):
        """Initialize alert rules engine."""
        self.rules: List[AlertRule] = []
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Set up default alert rules."""
        # High confidence signal rule
        self.add_rule(
            AlertRule(
                name="high_confidence_signal",
                description="Triggered when a signal has high confidence",
                condition=lambda d: d.get("confidence", 0) > 0.9,
                notification_type=NotificationType.SIGNAL,
                priority=NotificationPriority.HIGH,
                title_template="High Confidence {signal_type} Signal",
                message_template="{signal_type} signal for {symbol} with {confidence:.0%} confidence",
            )
        )

        # Strong risk-reward signal rule
        self.add_rule(
            AlertRule(
                name="strong_rr_signal",
                description="Triggered when risk-reward ratio is high",
                condition=lambda d: d.get("risk_reward_ratio", 0) > 2.0,
                notification_type=NotificationType.SIGNAL,
                priority=NotificationPriority.MEDIUM,
                title_template="Strong Risk-Reward Signal",
                message_template="Signal for {symbol} with R:R ratio of {risk_reward_ratio:.2f}",
            )
        )

        # Excellent backtest result
        self.add_rule(
            AlertRule(
                name="excellent_backtest",
                description="Triggered for backtests with high returns",
                condition=lambda d: d.get("total_return", 0) > 15.0,
                notification_type=NotificationType.BACKTEST,
                priority=NotificationPriority.HIGH,
                title_template="Excellent Backtest Result",
                message_template="Backtest completed with {total_return:.2f}% return",
            )
        )

        # System error rule
        self.add_rule(
            AlertRule(
                name="system_error",
                description="Triggered for system errors",
                condition=lambda d: d.get("status") == "error",
                notification_type=NotificationType.SYSTEM,
                priority=NotificationPriority.URGENT,
                title_template="System Error Alert",
                message_template="System error: {message}",
            )
        )

    def add_rule(self, rule: AlertRule) -> None:
        """
        Add an alert rule.

        Args:
            rule: Rule to add
        """
        self.rules.append(rule)
        logger.info(f"Added alert rule: {rule.name}")

    def remove_rule(self, name: str) -> None:
        """
        Remove an alert rule by name.

        Args:
            name: Name of rule to remove
        """
        self.rules = [r for r in self.rules if r.name != name]
        logger.info(f"Removed alert rule: {name}")

    def evaluate_all(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Evaluate all rules against data.

        Args:
            data: Data to evaluate

        Returns:
            List of matching rule notifications
        """
        matching_notifications = []

        for rule in self.rules:
            if rule.evaluate(data):
                notification_data = rule.create_notification(data)
                matching_notifications.append({
                    "rule": rule,
                    "notification": notification_data,
                })

        return matching_notifications

    def evaluate_and_notify(self, data: Dict[str, Any]) -> None:
        """
        Evaluate rules and create notifications.

        Args:
            data: Data to evaluate
        """
        service = get_service()
        matches = self.evaluate_all(data)

        for match in matches:
            rule = match["rule"]
            notification_data = match["notification"]

            service.add_notification(
                type=rule.notification_type,
                title=notification_data["title"],
                message=notification_data["message"],
                priority=rule.priority,
                data=notification_data["data"],
            )

    def get_rules(self) -> List[Dict[str, Any]]:
        """
        Get all rules as dictionaries.

        Returns:
            List of rule dictionaries
        """
        return [
            {
                "name": rule.name,
                "description": rule.description,
                "notification_type": rule.notification_type.value,
                "priority": rule.priority.value,
            }
            for rule in self.rules
        ]


# Global engine instance
_engine_instance: Optional[AlertRulesEngine] = None


def get_engine() -> AlertRulesEngine:
    """
    Get the global alert rules engine.

    Returns:
        Engine instance
    """
    global _engine_instance

    if _engine_instance is None:
        _engine_instance = AlertRulesEngine()

    return _engine_instance


# Convenience functions

def check_prediction(data: Dict[str, Any]) -> None:
    """
    Check prediction against alert rules.

    Args:
        data: Prediction data
    """
    engine = get_engine()
    engine.evaluate_and_notify(data)


def check_signal(data: Dict[str, Any]) -> None:
    """
    Check signal against alert rules.

    Args:
        data: Signal data
    """
    engine = get_engine()
    engine.evaluate_and_notify(data)


def check_backtest(data: Dict[str, Any]) -> None:
    """
    Check backtest against alert rules.

    Args:
        data: Backtest data
    """
    engine = get_engine()
    engine.evaluate_and_notify(data)


def check_system_status(data: Dict[str, Any]) -> None:
    """
    Check system status against alert rules.

    Args:
        data: System status data
    """
    engine = get_engine()
    engine.evaluate_and_notify(data)


if __name__ == "__main__":
    # Test the engine
    engine = get_engine()

    # Test signal
    test_signal = {
        "symbol": "BTC/USD",
        "signal_type": "BUY",
        "confidence": 0.95,
        "risk_reward_ratio": 2.5,
    }

    matches = engine.evaluate_all(test_signal)
    print(f"Matching rules: {len(matches)}")
    for match in matches:
        print(f"  - {match['rule'].name}: {match['notification']['title']}")
