"""WebSocket server for real-time dashboard updates.

Provides real-time data streaming to connected dashboard clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

import websockets
from websockets.server import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosed

from dgas.config import load_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DashboardWebSocketServer:
    """WebSocket server for real-time dashboard updates."""

    def __init__(self, host: str = "localhost", port: int = 8765):
        """
        Initialize WebSocket server.

        Args:
            host: Server host
            port: Server port
        """
        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.server = None
        self.running = False
        self._shutdown_event = asyncio.Event()

    async def register_client(self, websocket: WebSocketServerProtocol) -> None:
        """Register a new client connection."""
        self.clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.clients)}")

        # Send welcome message
        await self.send_to_client(websocket, {
            "type": "welcome",
            "timestamp": datetime.now().isoformat(),
            "message": "Connected to DGAS Dashboard WebSocket"
        })

    async def unregister_client(self, websocket: WebSocketServerProtocol) -> None:
        """Unregister a client connection."""
        self.clients.discard(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.clients)}")

    async def send_to_client(self, websocket: WebSocketServerProtocol, message: Dict[str, Any]) -> None:
        """Send a message to a specific client."""
        try:
            await websocket.send(json.dumps(message))
        except ConnectionClosed:
            self.clients.discard(websocket)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.clients.discard(websocket)

    async def broadcast(self, message: Dict[str, Any], exclude: Optional[WebSocketServerProtocol] = None) -> None:
        """
        Broadcast a message to all connected clients.

        Args:
            message: Message to broadcast
            exclude: Optional client to exclude from broadcast
        """
        if not self.clients:
            return

        message["timestamp"] = datetime.now().isoformat()
        dead_clients = set()

        for client in self.clients:
            if client == exclude:
                continue
            try:
                await client.send(json.dumps(message))
            except ConnectionClosed:
                dead_clients.add(client)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                dead_clients.add(client)

        # Clean up dead clients
        self.clients -= dead_clients

    async def handle_client(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """
        Handle a client connection.

        Args:
            websocket: WebSocket connection
            path: Request path
        """
        await self.register_client(websocket)
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.process_message(websocket, data)
                except json.JSONDecodeError:
                    await self.send_to_client(websocket, {
                        "type": "error",
                        "message": "Invalid JSON"
                    })
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await self.send_to_client(websocket, {
                        "type": "error",
                        "message": str(e)
                    })
        except ConnectionClosed:
            pass
        finally:
            await self.unregister_client(websocket)

    async def process_message(self, websocket: WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        Process incoming message from client.

        Args:
            websocket: WebSocket connection
            data: Message data
        """
        msg_type = data.get("type")

        if msg_type == "ping":
            await self.send_to_client(websocket, {
                "type": "pong",
                "timestamp": datetime.now().isoformat()
            })
        elif msg_type == "subscribe":
            # Client subscribing to specific events
            await self.send_to_client(websocket, {
                "type": "subscribed",
                "events": data.get("events", []),
                "timestamp": datetime.now().isoformat()
            })
        elif msg_type == "unsubscribe":
            # Client unsubscribing from events
            await self.send_to_client(websocket, {
                "type": "unsubscribed",
                "events": data.get("events", []),
                "timestamp": datetime.now().isoformat()
            })
        else:
            await self.send_to_client(websocket, {
                "type": "error",
                "message": f"Unknown message type: {msg_type}"
            })

    async def start(self) -> None:
        """Start the WebSocket server."""
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        self.running = True

        self.server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port
        )
        logger.info("WebSocket server started successfully")

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        logger.info("Stopping WebSocket server...")
        self.running = False
        self._shutdown_event.set()

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # Close all client connections
        for client in list(self.clients):
            await client.close()
        self.clients.clear()

        logger.info("WebSocket server stopped")

    async def wait_until_stopped(self) -> None:
        """Wait until server is stopped."""
        if self.server:
            await self.server.wait_closed()

    # Public methods for broadcasting events

    async def broadcast_prediction(self, prediction_data: Dict[str, Any]) -> None:
        """
        Broadcast new prediction.

        Args:
            prediction_data: Prediction data
        """
        await self.broadcast({
            "type": "prediction",
            "data": prediction_data
        })

    async def broadcast_signal(self, signal_data: Dict[str, Any]) -> None:
        """
        Broadcast new signal.

        Args:
            signal_data: Signal data
        """
        await self.broadcast({
            "type": "signal",
            "data": signal_data
        })

    async def broadcast_backtest(self, backtest_data: Dict[str, Any]) -> None:
        """
        Broadcast backtest completion.

        Args:
            backtest_data: Backtest data
        """
        await self.broadcast({
            "type": "backtest",
            "data": backtest_data
        })

    async def broadcast_data_update(self, update_data: Dict[str, Any]) -> None:
        """
        Broadcast data update.

        Args:
            update_data: Update data
        """
        await self.broadcast({
            "type": "data_update",
            "data": update_data
        })

    async def broadcast_system_status(self, status_data: Dict[str, Any]) -> None:
        """
        Broadcast system status update.

        Args:
            status_data: Status data
        """
        await self.broadcast({
            "type": "system_status",
            "data": status_data
        })


# Global server instance
_server_instance: Optional[DashboardWebSocketServer] = None


async def start_server(host: str = "localhost", port: int = 8765) -> DashboardWebSocketServer:
    """
    Start the global WebSocket server.

    Args:
        host: Server host
        port: Server port

    Returns:
        Server instance
    """
    global _server_instance

    if _server_instance and _server_instance.running:
        logger.warning("Server already running")
        return _server_instance

    _server_instance = DashboardWebSocketServer(host=host, port=port)
    await _server_instance.start()

    return _server_instance


async def stop_server() -> None:
    """Stop the global WebSocket server."""
    global _server_instance

    if _server_instance:
        await _server_instance.stop()
        _server_instance = None


def get_server() -> Optional[DashboardWebSocketServer]:
    """
    Get the global server instance.

    Returns:
        Server instance or None
    """
    return _server_instance


# Broadcast helper functions

async def broadcast_prediction(prediction_data: Dict[str, Any]) -> None:
    """Broadcast new prediction."""
    server = get_server()
    if server and server.running:
        await server.broadcast_prediction(prediction_data)


async def broadcast_signal(signal_data: Dict[str, Any]) -> None:
    """Broadcast new signal."""
    server = get_server()
    if server and server.running:
        await server.broadcast_signal(signal_data)


async def broadcast_backtest(backtest_data: Dict[str, Any]) -> None:
    """Broadcast backtest completion."""
    server = get_server()
    if server and server.running:
        await server.broadcast_backtest(backtest_data)


async def broadcast_data_update(update_data: Dict[str, Any]) -> None:
    """Broadcast data update."""
    server = get_server()
    if server and server.running:
        await server.broadcast_data_update(update_data)


async def broadcast_system_status(status_data: Dict[str, Any]) -> None:
    """Broadcast system status update."""
    server = get_server()
    if server and server.running:
        await server.broadcast_system_status(status_data)


# Integration with existing DGAS components

def setup_database_triggers() -> None:
    """
    Set up database triggers for automatic broadcasting.
    Note: This would require database trigger setup or a listener process.
    """
    logger.info("Database trigger setup would go here")
    logger.info("Alternatively, use periodic polling to check for new data")


if __name__ == "__main__":
    # Run standalone server
    async def main():
        server = await start_server()
        try:
            await server.wait_until_stopped()
        except KeyboardInterrupt:
            await stop_server()

    asyncio.run(main())
