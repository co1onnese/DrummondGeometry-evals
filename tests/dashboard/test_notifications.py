"""Tests for notification and alert system."""

import pytest
import json
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from dgas.dashboard.services.notification_service import (
    NotificationService,
    NotificationType,
    Priority,
    Notification,
)
from dgas.dashboard.utils.alert_rules import (
    AlertRule,
    AlertRuleManager,
    RuleCondition,
    RuleAction,
)


class TestNotification:
    """Test Notification data class."""

    def test_notification_creation(self):
        """Test creating a notification."""
        notification = Notification(
            id="test_123",
            type=NotificationType.PREDICTION,
            priority=Priority.HIGH,
            title="Test Notification",
            message="This is a test message",
            timestamp=datetime.now(),
            data={"key": "value"},
            read=False
        )

        assert notification.id == "test_123"
        assert notification.type == NotificationType.PREDICTION
        assert notification.priority == Priority.HIGH
        assert notification.title == "Test Notification"
        assert notification.message == "This is a test message"
        assert notification.data == {"key": "value"}
        assert not notification.read

    def test_notification_to_dict(self):
        """Test converting notification to dictionary."""
        timestamp = datetime.now()
        notification = Notification(
            id="test_456",
            type=NotificationType.SIGNAL,
            priority=Priority.MEDIUM,
            title="Signal Alert",
            message="New signal generated",
            timestamp=timestamp,
            data={},
            read=True
        )

        result = notification.to_dict()

        assert result["id"] == "test_456"
        assert result["type"] == "signal"
        assert result["priority"] == "medium"
        assert result["title"] == "Signal Alert"
        assert result["message"] == "New signal generated"
        assert result["timestamp"] == timestamp.isoformat()
        assert result["read"] is True


class TestNotificationService:
    """Test NotificationService functionality."""

    @pytest.fixture
    def notification_service(self):
        """Create a test notification service."""
        return NotificationService()

    def test_service_initialization(self, notification_service):
        """Test service initializes correctly."""
        assert notification_service.notifications == []
        assert notification_service.settings is not None
        assert len(notification_service.settings["notification_types"]) > 0

    def test_add_notification(self, notification_service):
        """Test adding a notification."""
        notification = Notification(
            id="test_1",
            type=NotificationType.PREDICTION,
            priority=Priority.HIGH,
            title="Test",
            message="Test message",
            timestamp=datetime.now(),
            data={},
            read=False
        )

        notification_service.add_notification(notification)

        assert len(notification_service.notifications) == 1
        assert notification_service.notifications[0] == notification

    def test_add_multiple_notifications(self, notification_service):
        """Test adding multiple notifications."""
        for i in range(5):
            notification = Notification(
                id=f"test_{i}",
                type=NotificationType.PREDICTION,
                priority=Priority.LOW,
                title=f"Test {i}",
                message=f"Message {i}",
                timestamp=datetime.now(),
                data={},
                read=False
            )
            notification_service.add_notification(notification)

        assert len(notification_service.notifications) == 5

    def test_mark_as_read(self, notification_service):
        """Test marking notification as read."""
        notification = Notification(
            id="test_2",
            type=NotificationType.SIGNAL,
            priority=Priority.MEDIUM,
            title="Test",
            message="Test message",
            timestamp=datetime.now(),
            data={},
            read=False
        )

        notification_service.add_notification(notification)
        notification_service.mark_as_read("test_2")

        assert notification_service.notifications[0].read is True

    def test_mark_all_as_read(self, notification_service):
        """Test marking all notifications as read."""
        for i in range(3):
            notification = Notification(
                id=f"test_{i}",
                type=NotificationType.PREDICTION,
                priority=Priority.LOW,
                title=f"Test {i}",
                message=f"Message {i}",
                timestamp=datetime.now(),
                data={},
                read=False
            )
            notification_service.add_notification(notification)

        notification_service.mark_all_as_read()

        assert all(n.read for n in notification_service.notifications)

    def test_remove_notification(self, notification_service):
        """Test removing a notification."""
        notification = Notification(
            id="test_3",
            type=NotificationType.BACKTEST,
            priority=Priority.HIGH,
            title="Test",
            message="Test message",
            timestamp=datetime.now(),
            data={},
            read=False
        )

        notification_service.add_notification(notification)
        assert len(notification_service.notifications) == 1

        notification_service.remove_notification("test_3")
        assert len(notification_service.notifications) == 0

    def test_get_unread_count(self, notification_service):
        """Test getting unread notification count."""
        # Add 2 read notifications
        for i in range(2):
            notification = Notification(
                id=f"read_{i}",
                type=NotificationType.PREDICTION,
                priority=Priority.LOW,
                title=f"Read {i}",
                message=f"Message {i}",
                timestamp=datetime.now(),
                data={},
                read=True
            )
            notification_service.add_notification(notification)

        # Add 3 unread notifications
        for i in range(3):
            notification = Notification(
                id=f"unread_{i}",
                type=NotificationType.SIGNAL,
                priority=Priority.MEDIUM,
                title=f"Unread {i}",
                message=f"Message {i}",
                timestamp=datetime.now(),
                data={},
                read=False
            )
            notification_service.add_notification(notification)

        assert notification_service.get_unread_count() == 3

    def test_filter_by_type(self, notification_service):
        """Test filtering notifications by type."""
        notification1 = Notification(
            id="test_1",
            type=NotificationType.PREDICTION,
            priority=Priority.LOW,
            title="Test 1",
            message="Message 1",
            timestamp=datetime.now(),
            data={},
            read=False
        )
        notification_service.add_notification(notification1)

        notification2 = Notification(
            id="test_2",
            type=NotificationType.SIGNAL,
            priority=Priority.MEDIUM,
            title="Test 2",
            message="Message 2",
            timestamp=datetime.now(),
            data={},
            read=False
        )
        notification_service.add_notification(notification2)

        predictions = notification_service.filter_by_type(NotificationType.PREDICTION)
        assert len(predictions) == 1
        assert predictions[0].type == NotificationType.PREDICTION

    def test_filter_by_priority(self, notification_service):
        """Test filtering notifications by priority."""
        for i in range(5):
            priority = Priority.HIGH if i % 2 == 0 else Priority.LOW
            notification = Notification(
                id=f"test_{i}",
                type=NotificationType.PREDICTION,
                priority=priority,
                title=f"Test {i}",
                message=f"Message {i}",
                timestamp=datetime.now(),
                data={},
                read=False
            )
            notification_service.add_notification(notification)

        high_priority = notification_service.filter_by_priority(Priority.HIGH)
        assert len(high_priority) == 3

    def test_export_to_json(self, notification_service):
        """Test exporting notifications to JSON."""
        notification = Notification(
            id="test_export",
            type=NotificationType.PREDICTION,
            priority=Priority.HIGH,
            title="Export Test",
            message="Export message",
            timestamp=datetime(2024, 11, 7, 12, 0, 0),
            data={"key": "value"},
            read=False
        )
        notification_service.add_notification(notification)

        json_data = notification_service.export_to_json()

        assert "notifications" in json_data
        assert len(json_data["notifications"]) == 1
        assert json_data["notifications"][0]["id"] == "test_export"

    def test_clear_all(self, notification_service):
        """Test clearing all notifications."""
        for i in range(5):
            notification = Notification(
                id=f"test_{i}",
                type=NotificationType.PREDICTION,
                priority=Priority.LOW,
                title=f"Test {i}",
                message=f"Message {i}",
                timestamp=datetime.now(),
                data={},
                read=False
            )
            notification_service.add_notification(notification)

        assert len(notification_service.notifications) == 5

        notification_service.clear_all()
        assert len(notification_service.notifications) == 0


class TestAlertRule:
    """Test AlertRule functionality."""

    def test_alert_rule_creation(self):
        """Test creating an alert rule."""
        rule = AlertRule(
            name="High Confidence Predictions",
            condition=RuleCondition.CONFIDENCE_GREATER,
            threshold=0.8,
            notification_type=NotificationType.PREDICTION,
            priority=Priority.HIGH,
            enabled=True
        )

        assert rule.name == "High Confidence Predictions"
        assert rule.condition == RuleCondition.CONFIDENCE_GREATER
        assert rule.threshold == 0.8
        assert rule.notification_type == NotificationType.PREDICTION
        assert rule.priority == Priority.HIGH
        assert rule.enabled is True

    def test_alert_rule_evaluation(self):
        """Test evaluating alert rule conditions."""
        rule = AlertRule(
            name="Test Rule",
            condition=RuleCondition.CONFIDENCE_GREATER,
            threshold=0.7,
            notification_type=NotificationType.PREDICTION,
            priority=Priority.MEDIUM,
            enabled=True
        )

        # Should trigger
        assert rule.should_trigger({"confidence": 0.8}) is True
        assert rule.should_trigger({"confidence": 0.9}) is True

        # Should not trigger
        assert rule.should_trigger({"confidence": 0.6}) is False
        assert rule.should_trigger({"confidence": 0.7}) is False

    def test_alert_rule_disabled(self):
        """Test disabled alert rule doesn't trigger."""
        rule = AlertRule(
            name="Disabled Rule",
            condition=RuleCondition.CONFIDENCE_GREATER,
            threshold=0.8,
            notification_type=NotificationType.PREDICTION,
            priority=Priority.HIGH,
            enabled=False
        )

        assert rule.should_trigger({"confidence": 0.9}) is False


class TestAlertRuleManager:
    """Test AlertRuleManager functionality."""

    @pytest.fixture
    def rule_manager(self):
        """Create a test alert rule manager."""
        return AlertRuleManager()

    def test_manager_initialization(self, rule_manager):
        """Test manager initializes with default rules."""
        assert len(rule_manager.rules) > 0

    def test_add_rule(self, rule_manager):
        """Test adding a new rule."""
        initial_count = len(rule_manager.rules)

        rule = AlertRule(
            name="Custom Rule",
            condition=RuleCondition.CONFIDENCE_GREATER,
            threshold=0.9,
            notification_type=NotificationType.SIGNAL,
            priority=Priority.HIGH,
            enabled=True
        )

        rule_manager.add_rule(rule)
        assert len(rule_manager.rules) == initial_count + 1

    def test_remove_rule(self, rule_manager):
        """Test removing a rule."""
        rule = AlertRule(
            name="Temp Rule",
            condition=RuleCondition.CONFIDENCE_GREATER,
            threshold=0.5,
            notification_type=NotificationType.PREDICTION,
            priority=Priority.LOW,
            enabled=True
        )

        rule_manager.add_rule(rule)
        rule_id = id(rule)
        assert len(rule_manager.rules) > 0

        rule_manager.remove_rule(rule_id)
        assert len(rule_manager.rules) > 0

    def test_enable_disable_rule(self, rule_manager):
        """Test enabling and disabling rules."""
        # Add a disabled rule
        rule = AlertRule(
            name="Toggle Rule",
            condition=RuleCondition.CONFIDENCE_GREATER,
            threshold=0.6,
            notification_type=NotificationType.PREDICTION,
            priority=Priority.MEDIUM,
            enabled=False
        )

        rule_manager.add_rule(rule)
        rule_id = id(rule)

        assert not rule_manager.rules[rule_id].enabled
        rule_manager.enable_rule(rule_id)
        assert rule_manager.rules[rule_id].enabled

        rule_manager.disable_rule(rule_id)
        assert not rule_manager.rules[rule_id].enabled

    def test_check_data_with_matching_rule(self, rule_manager):
        """Test checking data triggers matching rules."""
        # Add a rule for high confidence predictions
        rule = AlertRule(
            name="High Confidence",
            condition=RuleCondition.CONFIDENCE_GREATER,
            threshold=0.8,
            notification_type=NotificationType.PREDICTION,
            priority=Priority.HIGH,
            enabled=True
        )

        rule_manager.add_rule(rule)

        # Should trigger
        notifications = rule_manager.check_data({
            "type": "prediction",
            "confidence": 0.9
        })

        assert len(notifications) > 0
        assert notifications[0].priority == Priority.HIGH

    def test_check_data_no_match(self, rule_manager):
        """Test checking data with no matching rules."""
        # Add a rule for very high confidence
        rule = AlertRule(
            name="Very High Confidence",
            condition=RuleCondition.CONFIDENCE_GREATER,
            threshold=0.95,
            notification_type=NotificationType.PREDICTION,
            priority=Priority.HIGH,
            enabled=True
        )

        rule_manager.add_rule(rule)

        # Should not trigger
        notifications = rule_manager.check_data({
            "type": "prediction",
            "confidence": 0.8
        })

        assert len(notifications) == 0

    def test_check_data_multiple_rules(self, rule_manager):
        """Test checking data with multiple matching rules."""
        # Add multiple rules
        for threshold in [0.5, 0.7, 0.9]:
            rule = AlertRule(
                name=f"Rule {threshold}",
                condition=RuleCondition.CONFIDENCE_GREATER,
                threshold=threshold,
                notification_type=NotificationType.PREDICTION,
                priority=Priority.MEDIUM,
                enabled=True
            )
            rule_manager.add_rule(rule)

        # Should trigger all rules
        notifications = rule_manager.check_data({
            "type": "prediction",
            "confidence": 0.95
        })

        # All rules should trigger
        assert len(notifications) >= 3


class TestNotificationType:
    """Test NotificationType enum."""

    def test_all_types_defined(self):
        """Test all notification types are defined."""
        assert hasattr(NotificationType, 'PREDICTION')
        assert hasattr(NotificationType, 'SIGNAL')
        assert hasattr(NotificationType, 'BACKTEST')
        assert hasattr(NotificationType, 'SYSTEM_STATUS')
        assert hasattr(NotificationType, 'DATA_UPDATE')
        assert hasattr(NotificationType, 'ERROR')
        assert hasattr(NotificationType, 'WARNING')
        assert hasattr(NotificationType, 'INFO')


class TestPriority:
    """Test Priority enum."""

    def test_all_priorities_defined(self):
        """Test all priority levels are defined."""
        assert hasattr(Priority, 'LOW')
        assert hasattr(Priority, 'MEDIUM')
        assert hasattr(Priority, 'HIGH')
        assert hasattr(Priority, 'URGENT')

    def test_priority_ordering(self):
        """Test priority ordering."""
        assert Priority.LOW < Priority.MEDIUM
        assert Priority.MEDIUM < Priority.HIGH
        assert Priority.HIGH < Priority.URGENT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
