"""EODHD WebSocket client for real-time market data.

This module provides WebSocket-based real-time data collection from EODHD API.
Supports up to 50 symbols per WebSocket connection, with multiple connections
for larger symbol lists.

Based on: https://eodhd.com/financial-apis/new-real-time-data-api-websockets
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from ..db import get_connection
from ..settings import get_settings
from .errors import EODHDError, EODHDAuthError
from .models import IntervalData
from .repository import bulk_upsert_market_data, ensure_market_symbol
from .tick_aggregator import Tick, TickAggregator

logger = logging.getLogger(__name__)

# EODHD WebSocket endpoint
# Correct URL format: wss://ws.eodhistoricaldata.com/ws/{exchange}?api_token={token}
EODHD_WS_URL = "wss://ws.eodhistoricaldata.com/ws"

# Maximum symbols per WebSocket connection
MAX_SYMBOLS_PER_CONNECTION = 50


@dataclass
class WebSocketConnectionState:
    """State for a WebSocket connection."""

    symbols: List[str]
    connection: Optional[Any] = None  # WebSocketClientProtocol (type not imported to avoid deprecation warning)
    connected: bool = False
    last_message_time: Optional[datetime] = None
    reconnect_attempts: int = 0
    messages_received: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class EODHDWebSocketClient:
    """
    WebSocket client for EODHD real-time market data.

    Manages multiple WebSocket connections (up to 50 symbols per connection)
    for real-time price updates.
    """

    def __init__(
        self,
        api_token: str,
        on_bar_complete: Optional[Callable[[str, IntervalData], None]] = None,
        on_tick: Optional[Callable[[str, Tick], None]] = None,
        on_error: Optional[Callable[[str, Exception], None]] = None,
        interval: str = "30m",
    ):
        """
        Initialize WebSocket client.

        Args:
            api_token: EODHD API token
            on_bar_complete: Callback when a bar is completed (symbol, IntervalData)
            on_tick: Optional callback for raw ticks (symbol, Tick)
            on_error: Callback when error occurs (symbol, Exception)
            interval: Target interval for bar aggregation (e.g., "30m")
        """
        self.api_token = api_token
        self.on_bar_complete = on_bar_complete
        self.on_tick = on_tick
        self.on_error = on_error
        self.interval = interval

        # Tick aggregation
        self.aggregator = TickAggregator(interval=interval)

        # Connection management
        self.connections: Dict[int, WebSocketConnectionState] = {}
        self.running = False
        self._reconnect_task: Optional[asyncio.Task] = None

    async def connect(self, symbols: List[str]) -> None:
        """
        Connect to EODHD WebSocket and subscribe to symbols.

        Automatically creates multiple connections if needed (50 symbols per connection).

        Args:
            symbols: List of symbols to subscribe to (max 50 per connection)
        """
        if not symbols:
            raise ValueError("Symbols list cannot be empty")

        # Split symbols into chunks of 50
        symbol_chunks = [
            symbols[i : i + MAX_SYMBOLS_PER_CONNECTION]
            for i in range(0, len(symbols), MAX_SYMBOLS_PER_CONNECTION)
        ]

        logger.info(
            f"Connecting to EODHD WebSocket: {len(symbols)} symbols "
            f"across {len(symbol_chunks)} connections"
        )

        # Create connections for each chunk
        for idx, chunk in enumerate(symbol_chunks):
            await self._create_connection(idx, chunk)

        self.running = True

    async def _create_connection(self, connection_id: int, symbols: List[str]) -> None:
        """
        Create a single WebSocket connection for a group of symbols.

        Args:
            connection_id: Unique connection identifier
            symbols: Symbols for this connection (max 50)
        """
        if len(symbols) > MAX_SYMBOLS_PER_CONNECTION:
            raise ValueError(
                f"Too many symbols for one connection: {len(symbols)} > {MAX_SYMBOLS_PER_CONNECTION}"
            )

        state = WebSocketConnectionState(symbols=symbols)
        self.connections[connection_id] = state

        # Start connection task
        asyncio.create_task(self._connection_loop(connection_id, symbols))

    async def _connection_loop(self, connection_id: int, symbols: List[str]) -> None:
        """
        Main loop for a WebSocket connection.

        Handles connection, subscription, message processing, and reconnection
        with exponential backoff and jitter.

        Args:
            connection_id: Connection identifier
            symbols: Symbols for this connection
        """
        import random
        
        state = self.connections[connection_id]
        max_reconnect_attempts = 10  # Increased from 5
        base_reconnect_delay = 2.0  # Base delay in seconds
        max_reconnect_delay = 60.0  # Maximum delay (1 minute)

        while self.running:
            try:
                # Connect to WebSocket with timeout
                # URL format: wss://ws.eodhistoricaldata.com/ws/{exchange}?api_token={token}
                # For US stocks, use exchange="us"
                exchange = "us"  # Default to US exchange
                ws_url = f"{EODHD_WS_URL}/{exchange}?api_token={self.api_token}"
                logger.info(
                    f"Connection {connection_id}: Connecting to EODHD WebSocket "
                    f"for {len(symbols)} symbols (exchange: {exchange})"
                )

                # Connect with timeout
                try:
                    websocket = await asyncio.wait_for(
                        websockets.connect(ws_url),
                        timeout=10.0,  # 10 second connection timeout
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Connection {connection_id}: Connection timeout")
                    state.errors.append("Connection timeout")
                    raise

                async with websocket:
                    state.connection = websocket
                    state.connected = True
                    state.reconnect_attempts = 0  # Reset on successful connection
                    logger.info(f"Connection {connection_id}: Connected")

                    # Subscribe to symbols
                    # Official format: {"action": "subscribe", "symbols": "AAPL,TSLA"}
                    # Symbols must be comma-separated string, not array
                    symbols_str = ",".join(symbols)
                    subscribe_message = {
                        "action": "subscribe",
                        "symbols": symbols_str,
                    }
                    await websocket.send(json.dumps(subscribe_message))
                    logger.info(
                        f"Connection {connection_id}: Subscribed to {len(symbols)} symbols: {symbols_str[:50]}..."
                    )

                    # Process messages with heartbeat monitoring
                    last_heartbeat = datetime.now(timezone.utc)
                    heartbeat_timeout = 120.0  # 2 minutes without messages = dead connection

                    async for message in websocket:
                        try:
                            await self._process_message(connection_id, message)
                            state.last_message_time = datetime.now(timezone.utc)
                            state.messages_received += 1
                            last_heartbeat = state.last_message_time
                            
                            # Check for stale connection (no messages for too long)
                            if (datetime.now(timezone.utc) - last_heartbeat).total_seconds() > heartbeat_timeout:
                                logger.warning(
                                    f"Connection {connection_id}: No messages for {heartbeat_timeout}s, "
                                    "connection may be stale"
                                )
                                break  # Break to reconnect
                                
                        except Exception as e:
                            error_msg = f"Error processing message: {e}"
                            logger.error(f"Connection {connection_id}: {error_msg}")
                            state.errors.append(error_msg)
                            if self.on_error:
                                self.on_error("", e)

            except ConnectionClosed as e:
                logger.warning(
                    f"Connection {connection_id}: WebSocket closed "
                    f"(code: {e.code}, reason: {e.reason})"
                )
                state.connected = False
            except WebSocketException as e:
                logger.error(f"Connection {connection_id}: WebSocket error: {e}")
                state.connected = False
                state.errors.append(str(e))
            except asyncio.TimeoutError:
                logger.error(f"Connection {connection_id}: Connection timeout")
                state.connected = False
                state.errors.append("Connection timeout")
            except Exception as e:
                logger.error(
                    f"Connection {connection_id}: Unexpected error: {e}", exc_info=True
                )
                state.connected = False
                state.errors.append(str(e))

            # Reconnect logic with exponential backoff and jitter
            if self.running and state.reconnect_attempts < max_reconnect_attempts:
                state.reconnect_attempts += 1
                
                # Exponential backoff: base_delay * 2^(attempt-1)
                exponential_delay = base_reconnect_delay * (2 ** (state.reconnect_attempts - 1))
                
                # Cap at max delay
                delay = min(exponential_delay, max_reconnect_delay)
                
                # Add jitter (random 0-20% of delay) to prevent thundering herd
                jitter = delay * 0.2 * random.random()
                wait_time = delay + jitter
                
                logger.info(
                    f"Connection {connection_id}: Reconnecting in {wait_time:.1f}s "
                    f"(attempt {state.reconnect_attempts}/{max_reconnect_attempts}, "
                    f"exponential backoff: {delay:.1f}s + jitter: {jitter:.1f}s)"
                )
                await asyncio.sleep(wait_time)
            else:
                if state.reconnect_attempts >= max_reconnect_attempts:
                    logger.error(
                        f"Connection {connection_id}: Max reconnection attempts ({max_reconnect_attempts}) reached. "
                        "Connection will not be retried. Consider using REST API fallback."
                    )
                    if self.on_error:
                        self.on_error(
                            "",
                            RuntimeError(
                                f"Max reconnection attempts reached for connection {connection_id}"
                            ),
                        )
                break

    async def _process_message(
        self, connection_id: int, message: str
    ) -> None:
        """
        Process incoming WebSocket message.

        Args:
            connection_id: Connection identifier
            message: Raw message string
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            logger.warning(f"Connection {connection_id}: Invalid JSON: {message[:100]}")
            return

        # Handle different message types
        # EODHD messages: US trades have field "s" (symbol), "p" (price), "t" (timestamp)
        # Authorization: {"status_code": 200, "message": "Authorized"}
        # Subscription confirmations might have "action" or other fields
        
        # Check for authorization/status messages first
        if "status_code" in data:
            status_code = data.get("status_code")
            message = data.get("message", "")
            if status_code == 200:
                if "authorized" in message.lower():
                    logger.info(f"Connection {connection_id}: Authorized")
                elif "subscribed" in message.lower():
                    logger.info(f"Connection {connection_id}: Subscription confirmed")
                else:
                    logger.debug(f"Connection {connection_id}: Status message: {message}")
            else:
                error_msg = f"Status code {status_code}: {message}"
                logger.error(f"Connection {connection_id}: {error_msg}")
                self.connections[connection_id].errors.append(error_msg)
        # Check if this is a price update (has symbol field "s")
        elif "s" in data:
            # Price update message (US trades format)
            await self._handle_price_update(connection_id, data)
        elif "action" in data:
            # Subscription/unsubscription confirmation
            action = data.get("action")
            if action == "subscribed":
                logger.info(f"Connection {connection_id}: Subscription confirmed")
            elif action == "unsubscribed":
                logger.info(f"Connection {connection_id}: Unsubscription confirmed")
            elif action == "error":
                error_msg = data.get("message", "Unknown error")
                logger.error(f"Connection {connection_id}: API error: {error_msg}")
                self.connections[connection_id].errors.append(error_msg)
            else:
                logger.debug(f"Connection {connection_id}: Action message: {data}")
        else:
            # Unknown message format - log for debugging
            logger.debug(f"Connection {connection_id}: Unknown message format: {data}")

    async def _handle_price_update(
        self, connection_id: int, data: Dict[str, Any]
    ) -> None:
        """
        Handle price update message from WebSocket.

        Official EODHD format uses field "s" for symbol.

        Args:
            connection_id: Connection identifier
            data: Message data
        """
        # Extract symbol from message (field "s")
        symbol = data.get("s")
        if not symbol:
            logger.warning(f"Connection {connection_id}: No symbol (field 's') in price update: {data}")
            return

        # Normalize symbol (uppercase, no suffix)
        symbol = symbol.upper()
        if symbol.endswith(".US"):
            symbol = symbol[:-3]

        try:
            # Parse as tick (WebSocket provides tick-by-tick data)
            tick = self._parse_tick(symbol, data)

            if tick:
                # Call raw tick callback if provided
                if self.on_tick:
                    self.on_tick(symbol, tick)

                # Add to aggregator
                completed_bar = self.aggregator.add_tick(tick)

                # If bar is complete, call callback
                if completed_bar and self.on_bar_complete:
                    self.on_bar_complete(symbol, completed_bar)

        except Exception as e:
            logger.error(
                f"Connection {connection_id}: Error parsing price update for {symbol}: {e}"
            )
            if self.on_error:
                self.on_error(symbol, e)

    def _parse_tick(self, symbol: str, data: Dict[str, Any]) -> Optional[Tick]:
        """
        Parse price update message into Tick.

        Official EODHD US Trades format:
        {
            "s": "AAPL",        // ticker
            "p": 227.31,        // last trade price
            "v": 100,           // trade size (shares)
            "c": 12,            // trade condition code
            "dp": false,        // dark pool (true/false)
            "ms": "open",       // market status: open | closed | extended hours
            "t": 1725198451165  // epoch ms
        }

        Args:
            symbol: Stock symbol (from message or parameter)
            data: Message data from WebSocket

        Returns:
            Tick or None if parsing fails
        """
        try:
            # Extract symbol from message (field "s")
            msg_symbol = data.get("s")
            if msg_symbol:
                symbol = msg_symbol.upper()
            
            # Extract timestamp (field "t" - epoch milliseconds)
            timestamp_ms = data.get("t")
            if timestamp_ms:
                # Convert epoch milliseconds to datetime
                timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            # Extract price (field "p" - last trade price)
            price = data.get("p")
            if price is not None:
                price = Decimal(str(price))
            else:
                # Try bid/ask midpoint for quotes (if we're on quotes endpoint)
                bp = data.get("bp")  # bid price
                ap = data.get("ap")  # ask price
                if bp is not None and ap is not None:
                    price = (Decimal(str(bp)) + Decimal(str(ap))) / 2
                elif bp is not None:
                    price = Decimal(str(bp))
                elif ap is not None:
                    price = Decimal(str(ap))
                else:
                    logger.warning(f"No price found in message for {symbol}: {data}")
                    return None

            # Extract volume (field "v" - trade size in shares)
            volume = int(data.get("v", 0))

            # Extract trade condition code (field "c")
            condition_code = data.get("c")
            
            # Extract market status (field "ms")
            market_status = data.get("ms", "unknown")
            
            # Extract dark pool flag (field "dp")
            dark_pool = data.get("dp", False)

            # Build trade type string with metadata
            trade_type = "trade"
            if dark_pool:
                trade_type = "dark_pool"
            # Include condition code even if 0 (use is not None to handle 0 correctly)
            if condition_code is not None:
                trade_type = f"{trade_type}_c{condition_code}"

            return Tick(
                symbol=symbol,
                timestamp=timestamp,
                price=price,
                volume=volume,
                trade_type=trade_type,
            )
        except Exception as e:
            logger.error(f"Error parsing tick: {e}, data: {data}")
            return None

    def flush_pending_bars(self) -> List[IntervalData]:
        """
        Flush all pending bars that are complete.

        Returns:
            List of completed bars
        """
        return self.aggregator.flush_pending_bars()

    async def disconnect(self) -> None:
        """Disconnect all WebSocket connections."""
        logger.info("Disconnecting from EODHD WebSocket")
        self.running = False

        # Close all connections
        for connection_id, state in self.connections.items():
            if state.connection:
                try:
                    await state.connection.close()
                except Exception as e:
                    logger.error(f"Connection {connection_id}: Error closing: {e}")
            state.connected = False

        self.connections.clear()

    def get_status(self) -> Dict[str, Any]:
        """
        Get connection status.

        Returns:
            Dictionary with status information
        """
        total_symbols = sum(len(state.symbols) for state in self.connections.values())
        connected_count = sum(1 for state in self.connections.values() if state.connected)
        total_messages = sum(state.messages_received for state in self.connections.values())

        agg_stats = self.aggregator.get_stats()

        return {
            "connections": len(self.connections),
            "connected": connected_count,
            "total_symbols": total_symbols,
            "total_messages_received": total_messages,
            "aggregation": agg_stats,
            "connection_details": [
                {
                    "id": conn_id,
                    "symbols": len(state.symbols),
                    "connected": state.connected,
                    "messages_received": state.messages_received,
                    "reconnect_attempts": state.reconnect_attempts,
                    "errors": len(state.errors),
                }
                for conn_id, state in self.connections.items()
            ],
        }


__all__ = ["EODHDWebSocketClient", "MAX_SYMBOLS_PER_CONNECTION"]
