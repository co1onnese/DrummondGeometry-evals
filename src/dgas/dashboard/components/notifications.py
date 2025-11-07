"""Notification UI components for Streamlit.

Provides toast messages, notification panels, and settings.
"""

from __future__ import annotations

import streamlit as st
from datetime import datetime, timedelta

from dgas.dashboard.services.notification_service import (
    get_service,
    Notification,
    NotificationType,
    NotificationPriority,
)


def render_toast_notification(notification: Notification) -> None:
    """
    Render a toast notification.

    Args:
        notification: Notification to render
    """
    # Icon mapping
    icons = {
        NotificationType.INFO: "ℹ️",
        NotificationType.SUCCESS: "✅",
        NotificationType.WARNING: "⚠️",
        NotificationType.ERROR: "❌",
        NotificationType.PREDICTION: "🔮",
        NotificationType.SIGNAL: "📊",
        NotificationType.BACKTEST: "📈",
        NotificationType.SYSTEM: "🖥️",
    }

    icon = icons.get(notification.type, "📢")

    # Color mapping
    if notification.type == NotificationType.ERROR:
        st.error(f"{icon} {notification.title}: {notification.message}")
    elif notification.type == NotificationType.WARNING:
        st.warning(f"{icon} {notification.title}: {notification.message}")
    elif notification.type == NotificationType.SUCCESS:
        st.success(f"{icon} {notification.title}: {notification.message}")
    elif notification.type in [NotificationType.PREDICTION, NotificationType.SIGNAL]:
        st.info(f"{icon} {notification.title}: {notification.message}")
    else:
        st.info(f"{icon} {notification.title}: {notification.message}")


def render_notification_panel(
    max_height: int = 400,
    show_mark_read: bool = True,
    show_clear: bool = True,
) -> None:
    """
    Render notification panel with history.

    Args:
        max_height: Maximum height in pixels
        show_mark_read: Show mark as read buttons
        show_clear: Show clear all button
    """
    service = get_service()
    service.initialize()

    # Header
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        st.subheader("Notifications")

    with col2:
        unread_count = service.get_unread_count()
        st.metric("Unread", unread_count)

    with col3:
        if show_clear and st.button("Clear All", type="secondary"):
            service.clear_all()
            st.rerun()

    # Get notifications
    notifications = service.get_notifications(limit=50)

    if not notifications:
        st.info("No notifications yet")
        return

    # Display notifications
    for notification in notifications:
        with st.container():
            # Status indicator
            status_color = "🔴" if not notification.read else "⚪"
            priority_indicator = {
                NotificationPriority.URGENT: "🔴",
                NotificationPriority.HIGH: "🟠",
                NotificationPriority.MEDIUM: "🟡",
                NotificationPriority.LOW: "🟢",
            }.get(notification.priority, "⚪")

            col1, col2, col3, col4 = st.columns([1, 4, 1, 1])

            with col1:
                st.text(f"{status_color} {priority_indicator}")

            with col2:
                if not notification.read:
                    st.markdown(f"**{notification.title}**")
                else:
                    st.markdown(f"{notification.title}")

                st.caption(
                    f"{notification.message} • {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                )

            with col3:
                if show_mark_read and not notification.read:
                    if st.button("Mark Read", key=f"read_{notification.id}", type="secondary"):
                        service.mark_as_read(notification.id)
                        st.rerun()

            with col4:
                if st.button("✕", key=f"remove_{notification.id}", help="Remove"):
                    service.remove_notification(notification.id)
                    st.rerun()

            st.markdown("---")


def render_notification_settings() -> None:
    """Render notification settings panel."""
    service = get_service()
    service.initialize()

    st.subheader("Notification Settings")

    settings = service.get_settings()

    # Enable/disable types
    st.markdown("**Notification Types**")
    col1, col2 = st.columns(2)

    with col1:
        enable_predictions = st.checkbox(
            "Enable Predictions",
            value=settings.get("enable_predictions", True),
        )
        enable_signals = st.checkbox(
            "Enable Signals",
            value=settings.get("enable_signals", True),
        )

    with col2:
        enable_backtests = st.checkbox(
            "Enable Backtests",
            value=settings.get("enable_backtests", True),
        )
        enable_system = st.checkbox(
            "Enable System Alerts",
            value=settings.get("enable_system", True),
        )

    # Thresholds
    st.markdown("**Alert Thresholds**")
    col1, col2 = st.columns(2)

    with col1:
        min_confidence = st.slider(
            "Min Signal Confidence",
            min_value=0.0,
            max_value=1.0,
            value=settings.get("min_confidence", 0.8),
            step=0.05,
            help="Only show signals above this confidence level",
        )

    with col2:
        min_rr_ratio = st.slider(
            "Min Risk-Reward Ratio",
            min_value=0.0,
            max_value=5.0,
            value=settings.get("min_rr_ratio", 1.5),
            step=0.1,
            help="Only show signals with risk-reward ratio above this",
        )

    # Quiet hours
    st.markdown("**Quiet Hours**")
    st.caption("No notifications during quiet hours (except urgent)")

    col1, col2 = st.columns(2)

    with col1:
        quiet_start = st.time_input(
            "Start Time",
            value=datetime.strptime(settings.get("quiet_hours_start", "22:00"), "%H:%M").time()
            if settings.get("quiet_hours_start") else datetime.now().time(),
        )

    with col2:
        quiet_end = st.time_input(
            "End Time",
            value=datetime.strptime(settings.get("quiet_hours_end", "08:00"), "%H:%M").time()
            if settings.get("quiet_hours_end") else datetime.now().time(),
        )

    # Save button
    if st.button("Save Settings", type="primary"):
        service.update_settings({
            "enable_predictions": enable_predictions,
            "enable_signals": enable_signals,
            "enable_backtests": enable_backtests,
            "enable_system": enable_system,
            "min_confidence": min_confidence,
            "min_rr_ratio": min_rr_ratio,
            "quiet_hours_start": quiet_start.strftime("%H:%M"),
            "quiet_hours_end": quiet_end.strftime("%H:%M"),
        })
        st.success("Settings saved!")
        st.rerun()

    # Test notification
    st.markdown("---")
    st.markdown("**Test Notifications**")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Test Info", type="secondary"):
            service.create_system_notification(
                "This is a test info notification",
                NotificationType.INFO,
                NotificationPriority.LOW,
            )
            st.rerun()

    with col2:
        if st.button("Test Signal", type="secondary"):
            service.create_signal_notification({
                "symbol": "BTC/USD",
                "signal_type": "BUY",
                "confidence": 0.95,
                "risk_reward_ratio": 2.5,
            })
            st.rerun()

    with col3:
        if st.button("Test Urgent", type="secondary"):
            service.create_system_notification(
                "This is an urgent system alert!",
                NotificationType.ERROR,
                NotificationPriority.URGENT,
            )
            st.rerun()


def show_new_notifications() -> None:
    """Check and show new notifications from session state."""
    service = get_service()
    service.initialize()

    # Check for new prediction
    if st.session_state.get("new_prediction_available"):
        service.create_prediction_notification(
            st.session_state.get("last_prediction", {}).get("data", {})
        )
        st.session_state.new_prediction_available = False

    # Check for new signal
    if st.session_state.get("show_signal_notification"):
        signal_data = st.session_state.get("last_signal", {}).get("data", {})
        if signal_data:
            service.create_signal_notification(signal_data)
        st.session_state.show_signal_notification = False

    # Check for new backtest
    if st.session_state.get("show_backtest_notification"):
        backtest_data = st.session_state.get("last_backtest", {}).get("data", {})
        if backtest_data:
            service.create_backtest_notification(backtest_data)
        st.session_state.show_backtest_notification = False

    # Check for system status updates
    if st.session_state.get("system_status_updated"):
        status = st.session_state.get("system_status", {}).get("data", {})
        if status:
            service.create_system_notification(
                "System status updated",
                NotificationType.SYSTEM,
                NotificationPriority.LOW,
            )
        st.session_state.system_status_updated = False

    # Get unread notifications
    unread_notifications = service.get_notifications(unread_only=True, limit=5)

    # Show toast notifications
    for notification in unread_notifications:
        # Don't show auto-dismiss notifications if user is interacting
        if notification.auto_dismiss:
            render_toast_notification(notification)
            service.mark_as_read(notification.id)


def render_notification_summary() -> None:
    """Render a summary of recent notifications."""
    service = get_service()
    service.initialize()

    notifications = service.get_notifications(limit=10)
    unread_count = service.get_unread_count()

    if not notifications:
        st.info("No notifications")
        return

    # Summary stats
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total", len(notifications))

    with col2:
        st.metric("Unread", unread_count)

    with col3:
        recent = [n for n in notifications if n.timestamp > datetime.now() - timedelta(hours=1)]
        st.metric("Last Hour", len(recent))

    # Recent notifications list
    st.markdown("**Recent Notifications**")
    for notification in notifications[:5]:
        icon = {
            NotificationType.PREDICTION: "🔮",
            NotificationType.SIGNAL: "📊",
            NotificationType.BACKTEST: "📈",
            NotificationType.SYSTEM: "🖥️",
        }.get(notification.type, "📢")

        read_indicator = " " if notification.read else "●"
        st.text(f"{read_indicator} {icon} {notification.title} - {notification.timestamp.strftime('%H:%M:%S')}")


def export_notifications_ui() -> None:
    """UI for exporting notifications."""
    service = get_service()
    service.initialize()

    st.subheader("Export Notifications")

    notifications = service.get_notifications()
    st.info(f"Total notifications to export: {len(notifications)}")

    if st.button("Export to JSON"):
        export_path = f"notifications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        service.export_notifications(export_path)

        with open(export_path, "r") as f:
            st.download_button(
                label="Download Export",
                data=f.read(),
                file_name=export_path,
                mime="application/json",
            )


if __name__ == "__main__":
    # Test the UI components
    st.set_page_config(page_title="Notifications Test")
    st.title("Notification Components Test")

    # Show notifications
    show_new_notifications()

    # Sidebar
    st.sidebar.title("Notifications")
    render_notification_summary()
