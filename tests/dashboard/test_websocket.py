"""Tests for WebSocket real-time streaming system."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from dgas.dashboard.websocket_server import (
    WebSocketServer,
    ClientConnection,
    EventType,
)


class TestWebSocketServer:
    """Test WebSocket server functionality."""

    @pytest.fixture
    def server(self):
        """Create a test server instance."""
        return WebSocketServer(host="127.0.0.1", port=8765)

    @pytest.mark.asyncio
    async def test_server_initialization(self, server):
        """Test server initializes correctly."""
        assert server.host == "127.0.0.1"
        assert server.port == 8765
        assert server.clients == {}
        assert not server._running

    @pytest.mark.asyncio
    async def test_start_stop_server(self, server):
        """Test server can start and stop."""
        with patch('asyncio.start_server') as mock_start_server:
            mock_server = AsyncMock()
            mock_start_server.return_value = mock_server

            await server.start()
            assert server._running
            mock_start_server.assert_called_once()

            await server.stop()
            assert not server._running
            mock_server.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_client(self, server):
        """Test adding a client connection."""
        websocket = Mock()
        client_id = "test_client_1"

        await server._add_client(client_id, websocket)
        assert client_id in server.clients
        assert isinstance(server.clients[client_id], ClientConnection)

    @pytest.mark.asyncio
    async def test_remove_client(self, server):
        """Test removing a client connection."""
        websocket = Mock()
        client_id = "test_client_2"

        await server._add_client(client_id, websocket)
        assert client_id in server.clients

        await server._remove_client(client_id)
        assert client_id not in server.clients

    @pytest.mark.asyncio
    async def test_broadcast_event(self, server):
        """Test broadcasting events to clients."""
        websocket1 = Mock()
        websocket2 = Mock()
        websocket1.send_json = AsyncMock()
        websocket2.send_json = AsyncMock()

        await server._add_client("client1", websocket1)
        await server._add_client("client2", websocket2)

        event = {
            "type": EventType.PREDICTION,
            "data": {"message": "test prediction"},
            "timestamp": "2024-11-07T00:00:00"
        }

        await server.broadcast_event(event)

        websocket1.send_json.assert_called_once_with(event)
        websocket2.send_json.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_broadcast_to_specific_clients(self, server):
        """Test broadcasting to specific client types."""
        websocket1 = Mock()
        websocket2 = Mock()
        websocket1.send_json = AsyncMock()
        websocket2.send_json = AsyncMock()

        await server._add_client("client1", websocket1)
        await server._add_client("client2", websocket2)

        event = {
            "type": EventType.SIGNAL,
            "data": {"message": "test signal"},
        }

        await server.broadcast_event(event, event_type=EventType.SIGNAL)

        websocket1.send_json.assert_called_once()
        websocket2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_client_count(self, server):
        """Test getting client count."""
        assert server.get_client_count() == 0

        websocket = Mock()
        await server._add_client("client1", websocket)
        assert server.get_client_count() == 1

        await server._add_client("client2", websocket)
        assert server.get_client_count() == 2

    @pytest.mark.asyncio
    async def test_handle_client_disconnect(self, server):
        """Test handling client disconnection."""
        websocket = Mock()
        client_id = "test_client"

        await server._add_client(client_id, websocket)
        assert client_id in server.clients

        await server._handle_client_disconnect(client_id)
        assert client_id not in server.clients


class TestClientConnection:
    """Test ClientConnection class."""

    @pytest.fixture
    def client_conn(self):
        """Create a test client connection."""
        websocket = Mock()
        return ClientConnection(
            client_id="test_client",
            websocket=websocket,
            client_type="dashboard",
            connected_at=asyncio.get_event_loop().time()
        )

    def test_client_initialization(self, client_conn):
        """Test client connection initializes correctly."""
        assert client_conn.client_id == "test_client"
        assert client_conn.websocket is not None
        assert client_conn.client_type == "dashboard"
        assert client_conn.connected_at is not None
        assert client_conn.is_alive

    def test_send_message(self, client_conn):
        """Test sending message to client."""
        message = {"type": "test", "data": "test_data"}
        client_conn.websocket.send_json = Mock()

        client_conn.send_message(message)
        client_conn.websocket.send_json.assert_called_once_with(message)

    def test_mark_inactive(self, client_conn):
        """Test marking client as inactive."""
        assert client_conn.is_alive
        client_conn.mark_inactive()
        assert not client_conn.is_alive


class TestEventTypes:
    """Test event type definitions."""

    def test_event_type_constants(self):
        """Test all event types are defined."""
        assert hasattr(EventType, 'PREDICTION')
        assert hasattr(EventType, 'SIGNAL')
        assert hasattr(EventType, 'BACKTEST')
        assert hasattr(EventType, 'SYSTEM_STATUS')
        assert hasattr(EventType, 'DATA_UPDATE')

    def test_event_type_values(self):
        """Test event type values are correct strings."""
        assert EventType.PREDICTION == "prediction"
        assert EventType.SIGNAL == "signal"
        assert EventType.BACKTEST == "backtest"
        assert EventType.SYSTEM_STATUS == "system_status"
        assert EventType.DATA_UPDATE == "data_update"


@pytest.mark.asyncio
async def test_server_stress_multiple_clients():
    """Test server with multiple concurrent clients."""
    server = WebSocketServer(host="127.0.0.1", port=8766)

    # Create 10 clients
    clients = []
    for i in range(10):
        websocket = Mock()
        websocket.send_json = AsyncMock()
        client_id = f"client_{i}"
        await server._add_client(client_id, websocket)
        clients.append((client_id, websocket))

    assert server.get_client_count() == 10

    # Broadcast event
    event = {
        "type": EventType.SYSTEM_STATUS,
        "data": {"status": "healthy"},
    }

    await server.broadcast_event(event)

    # Verify all clients received the event
    for _, websocket in clients:
        websocket.send_json.assert_called_once_with(event)

    # Cleanup
    for client_id, _ in clients:
        await server._remove_client(client_id)

    assert server.get_client_count() == 0


@pytest.mark.asyncio
async def test_server_heartbeat():
    """Test server heartbeat functionality."""
    server = WebSocketServer(host="127.0.0.1", port=8767)
    websocket = Mock()
    websocket.send_json = AsyncMock()

    await server._add_client("test_client", websocket)

    # Simulate heartbeat
    event = {
        "type": EventType.SYSTEM_STATUS,
        "data": {"heartbeat": True},
    }

    await server.broadcast_event(event)
    websocket.send_json.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
