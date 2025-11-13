"""Real-time client for WebSocket connections.

Handles real-time updates in the Streamlit dashboard.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from pathlib import Path

import streamlit as st

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RealtimeClient:
    """WebSocket client for real-time dashboard updates."""

    def __init__(self, server_url: str = "ws://localhost:8765"):
        """
        Initialize real-time client.

        Args:
            server_url: WebSocket server URL
        """
        self.server_url = server_url
        self.connected = False
        self.last_message_time: Optional[datetime] = None
        self.message_count = 0
        self.subscribed_events: Set[str] = set()
        self.event_handlers: Dict[str, List[Callable]] = {}
        self._retry_count = 0
        self._max_retries = 5
        self._retry_delay = 2

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """
        Subscribe to an event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Handler function to call when event occurs
        """
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
        self.subscribed_events.add(event_type)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """
        Unsubscribe from an event type.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove
        """
        if event_type in self.event_handlers:
            if handler in self.event_handlers[event_type]:
                self.event_handlers[event_type].remove(handler)
            if not self.event_handlers[event_type]:
                self.event_handlers.pop(event_type)
                self.subscribed_events.discard(event_type)

    def connect(self) -> bool:
        """
        Connect to WebSocket server.

        Returns:
            True if connection successful
        """
        try:
            # In Streamlit, we use JavaScript for WebSocket
            # This is a placeholder for the actual connection logic
            # Real connection will be handled via st.session_state and JavaScript

            if "websocket_connected" not in st.session_state:
                st.session_state.websocket_connected = False
                st.session_state.websocket_messages = []

            self.connected = st.session_state.websocket_connected
            return self.connected
        except Exception as e:
            logger.error(f"Error connecting to WebSocket: {e}")
            self.connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect from WebSocket server."""
        self.connected = False

    def send_message(self, message: Dict[str, Any]) -> None:
        """
        Send a message to the server.

        Args:
            message: Message to send
        """
        if not self.connected:
            logger.warning("Not connected to WebSocket server")
            return

        try:
            # In Streamlit, messages are sent via session state
            # The JavaScript frontend would handle the actual WebSocket send
            if "websocket_messages" in st.session_state:
                st.session_state.websocket_messages.append(message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    def handle_message(self, message_data: Dict[str, Any]) -> None:
        """
        Handle incoming message.

        Args:
            message_data: Received message data
        """
        self.message_count += 1
        self.last_message_time = datetime.now()

        msg_type = message_data.get("type")
        data = message_data.get("data")

        if msg_type in self.event_handlers:
            for handler in self.event_handlers[msg_type]:
                try:
                    handler(data, message_data)
                except Exception as e:
                    logger.error(f"Error in event handler: {e}")

    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get connection status.

        Returns:
            Dictionary with connection status
        """
        return {
            "connected": self.connected,
            "server_url": self.server_url,
            "last_message": self.last_message_time.isoformat() if self.last_message_time else None,
            "message_count": self.message_count,
            "subscribed_events": list(self.subscribed_events),
        }


# Global client instance
_client_instance: Optional[RealtimeClient] = None


def get_client() -> RealtimeClient:
    """
    Get the global client instance.

    Returns:
        Client instance
    """
    global _client_instance

    if _client_instance is None:
        _client_instance = RealtimeClient()

    return _client_instance


# Streamlit integration helpers

def init_websocket_script() -> str:
    """
    Get JavaScript code for WebSocket integration.

    Returns:
        JavaScript code as string
    """
    js_code = """
    <script>
    // WebSocket connection
    const socket = new WebSocket('ws://localhost:8765');

    socket.onopen = function(event) {
        console.log('WebSocket connected');
        // Streamlit doesn't have direct access to Python session state
        // This is handled differently in the actual implementation
    };

    socket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        console.log('Received:', data);
        // Forward to Python (would use custom Streamlit components)
    };

    socket.onclose = function(event) {
        console.log('WebSocket disconnected');
    };

    socket.onerror = function(error) {
        console.error('WebSocket error:', error);
    };
    </script>
    """
    return js_code


def render_websocket_status() -> None:
    """
    Render WebSocket connection status in Streamlit.
    Shows status gracefully - real-time updates are optional.
    """
    client = get_client()
    status = client.get_connection_status()

    col1, col2, col3 = st.columns(3)

    with col1:
        if status["connected"]:
            st.success("🟢 Connected", icon="✅")
        else:
            # Show as info rather than error - real-time updates are optional
            st.info("⚪ Real-time updates unavailable", icon="ℹ️")
            st.caption("Using auto-refresh instead")

    with col2:
        st.metric(
            "Messages Received",
            status["message_count"],
            help="Total messages received via WebSocket"
        )

    with col3:
        if status["last_message"]:
            st.metric(
                "Last Update",
                status["last_message"][-8:],  # Show time only
                help="Last message timestamp"
            )
        else:
            st.metric(
                "Update Mode",
                "Polling",
                help="Dashboard uses polling for updates"
            )


# Event handlers for different update types

def create_prediction_handler() -> Callable[[Dict[str, Any], Dict[str, Any]], None]:
    """Create handler for prediction updates."""
    def handler(data: Dict[str, Any], message: Dict[str, Any]) -> None:
        st.session_state.last_prediction = {
            "data": data,
            "timestamp": message.get("timestamp"),
        }
        st.session_state.show_prediction_notification = True

    return handler


def create_signal_handler() -> Callable[[Dict[str, Any], Dict[str, Any]], None]:
    """Create handler for signal updates."""
    def handler(data: Dict[str, Any], message: Dict[str, Any]) -> None:
        st.session_state.last_signal = {
            "data": data,
            "timestamp": message.get("timestamp"),
        }
        st.session_state.show_signal_notification = True

    return handler


def create_backtest_handler() -> Callable[[Dict[str, Any], Dict[str, Any]], None]:
    """Create handler for backtest updates."""
    def handler(data: Dict[str, Any], message: Dict[str, Any]) -> None:
        st.session_state.last_backtest = {
            "data": data,
            "timestamp": message.get("timestamp"),
        }
        st.session_state.show_backtest_notification = True

    return handler


def create_system_status_handler() -> Callable[[Dict[str, Any], Dict[str, Any]], None]:
    """Create handler for system status updates."""
    def handler(data: Dict[str, Any], message: Dict[str, Any]) -> None:
        st.session_state.system_status = {
            "data": data,
            "timestamp": message.get("timestamp"),
        }
        st.session_state.system_status_updated = True

    return handler


# Polling-based fallback (if WebSocket not available)

def check_for_updates() -> None:
    """
    Check for updates using polling (fallback method).
    This simulates real-time updates by checking the database.
    """
    from dgas.dashboard.components.database import fetch_predictions, fetch_backtest_results

    # Check for new predictions
    if "last_prediction_check" not in st.session_state:
        st.session_state.last_prediction_check = datetime.now()

    # Get recent predictions (last 5 minutes)
    try:
        recent_predictions = fetch_predictions(days=1)
        if not recent_predictions.empty:
            latest = recent_predictions.iloc[0]
            if "last_seen_prediction_id" not in st.session_state:
                st.session_state.last_seen_prediction_id = latest.get("signal_id", 0)

            current_id = latest.get("signal_id", 0)
            if current_id != st.session_state.last_seen_prediction_id:
                st.session_state.last_seen_prediction_id = current_id
                st.session_state.new_prediction_available = True
    except Exception as e:
        logger.error(f"Error checking for predictions: {e}")


# Auto-setup function

def setup_realtime_client() -> RealtimeClient:
    """
    Set up the real-time client with default handlers.

    Returns:
        Configured client instance
    """
    client = get_client()

    # Subscribe to event types
    client.subscribe("prediction", create_prediction_handler())
    client.subscribe("signal", create_signal_handler())
    client.subscribe("backtest", create_backtest_handler())
    client.subscribe("system_status", create_system_status_handler())

    return client


if __name__ == "__main__":
    # Test the client
    client = RealtimeClient()
    print(client.get_connection_status())
