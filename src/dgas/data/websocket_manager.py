"""WebSocket manager for bridging async WebSocket client with sync collection service.

This module provides a synchronous interface to the async WebSocket client,
running the WebSocket in a background thread with its own event loop.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from queue import Queue
from typing import Callable, Dict, List, Optional

from ..db import get_connection
from ..settings import get_settings
from .repository import bulk_upsert_market_data, ensure_market_symbol
from .websocket_client import EODHDWebSocketClient

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Synchronous manager for async WebSocket client.

    Runs WebSocket client in a background thread and provides sync interface
    for data collection service.
    """

    def __init__(
        self,
        api_token: str,
        interval: str = "30m",
        on_bar_complete: Optional[Callable[[str, List], None]] = None,
    ):
        """
        Initialize WebSocket manager.

        Args:
            api_token: EODHD API token
            interval: Target interval for bars (e.g., "30m")
            on_bar_complete: Optional callback when bars are ready to store
        """
        self.api_token = api_token
        self.interval = interval
        self.on_bar_complete = on_bar_complete

        # WebSocket client (created in async thread)
        self._client: Optional[EODHDWebSocketClient] = None

        # Thread and event loop
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

        # Data buffers
        self._bar_buffer: Dict[str, List] = defaultdict(list)
        self._bar_buffer_lock = threading.Lock()

        # Statistics
        self._stats = {
            "bars_received": 0,
            "bars_stored": 0,
            "errors": [],
            "start_time": None,
        }

    def start(self, symbols: List[str]) -> None:
        """
        Start WebSocket connections for symbols.

        Args:
            symbols: List of symbols to subscribe to
        """
        if self._running:
            logger.warning("WebSocket manager already running")
            return

        logger.info(f"Starting WebSocket manager for {len(symbols)} symbols")
        self._running = True
        self._stats["start_time"] = datetime.now(timezone.utc)

        # Start background thread
        self._thread = threading.Thread(
            target=self._run_websocket_loop,
            args=(symbols,),
            daemon=True,
            name="WebSocketManager",
        )
        self._thread.start()

        # Wait a moment for connection to establish
        time.sleep(2)

        logger.info("WebSocket manager started")

    def stop(self, timeout: float = 10.0) -> None:
        """
        Stop WebSocket connections.

        Args:
            timeout: Maximum time to wait for shutdown (seconds)
        """
        if not self._running:
            return

        logger.info("Stopping WebSocket manager")
        self._running = False

        # Stop client via event loop
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._stop_client(), self._loop)

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        # Flush any remaining bars
        self._flush_all_bars()

        logger.info("WebSocket manager stopped")

    def _run_websocket_loop(self, symbols: List[str]) -> None:
        """Run WebSocket client in background thread."""
        # Create new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        flush_task = None
        try:
            # Create WebSocket client
            self._client = EODHDWebSocketClient(
                api_token=self.api_token,
                on_bar_complete=self._on_bar_complete_async,
                on_error=self._on_error_async,
                interval=self.interval,
            )

            # Connect with timeout
            logger.info(f"Connecting WebSocket client for {len(symbols)} symbols...")
            try:
                self._loop.run_until_complete(
                    asyncio.wait_for(self._client.connect(symbols), timeout=30.0)
                )
                logger.info("WebSocket client connected successfully")
            except asyncio.TimeoutError:
                logger.error("WebSocket connection timeout")
                raise
            except Exception as e:
                logger.error(f"WebSocket connection failed: {e}", exc_info=True)
                raise

            # Run periodic flush task
            flush_task = self._loop.create_task(self._periodic_flush())

            # Keep running until stopped
            while self._running:
                try:
                    self._loop.run_until_complete(asyncio.sleep(1))
                except Exception as e:
                    logger.error(f"Error in WebSocket loop: {e}", exc_info=True)
                    # Continue running unless it's a critical error
                    if not self._running:
                        break

        except Exception as e:
            logger.error(f"WebSocket loop error: {e}", exc_info=True)
            self._stats["errors"].append(str(e))
        finally:
            # Graceful shutdown
            logger.info("Shutting down WebSocket client...")
            
            # Cancel flush task
            if flush_task and not flush_task.done():
                flush_task.cancel()
                try:
                    self._loop.run_until_complete(flush_task)
                except asyncio.CancelledError:
                    pass

            # Flush any remaining bars before disconnect
            try:
                if self._client:
                    # Flush pending bars
                    pending_bars = self._client.flush_pending_bars()
                    if pending_bars:
                        logger.info(f"Flushing {len(pending_bars)} pending bars before disconnect")
                        for bar in pending_bars:
                            self._on_bar_complete_async(bar.symbol, bar)
            except Exception as e:
                logger.error(f"Error flushing bars on shutdown: {e}")

            # Disconnect
            if self._client:
                try:
                    self._loop.run_until_complete(
                        asyncio.wait_for(self._client.disconnect(), timeout=10.0)
                    )
                    logger.info("WebSocket client disconnected")
                except asyncio.TimeoutError:
                    logger.warning("WebSocket disconnect timeout")
                except Exception as e:
                    logger.error(f"Error disconnecting WebSocket: {e}")

            # Close event loop
            try:
                self._loop.close()
            except Exception as e:
                logger.error(f"Error closing event loop: {e}")
            
            logger.info("WebSocket loop stopped")

    async def _stop_client(self) -> None:
        """Stop WebSocket client."""
        if self._client:
            await self._client.disconnect()

    def _on_bar_complete_async(self, symbol: str, bar) -> None:
        """
        Async callback when bar is complete.

        This is called from async context, so we need to thread-safely
        add to buffer.
        """
        with self._bar_buffer_lock:
            self._bar_buffer[symbol].append(bar)
            self._stats["bars_received"] += 1

        # Call user callback if provided
        if self.on_bar_complete:
            try:
                self.on_bar_complete(symbol, [bar])
            except Exception as e:
                logger.error(f"Error in on_bar_complete callback: {e}")

    def _on_error_async(self, symbol: str, error: Exception) -> None:
        """Async callback when error occurs."""
        error_msg = f"{symbol}: {error}"
        logger.error(error_msg)
        self._stats["errors"].append(error_msg)

    async def _periodic_flush(self) -> None:
        """Periodically flush completed bars from aggregator."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Flush every minute

                if self._client:
                    # Flush pending bars from aggregator
                    completed_bars = self._client.flush_pending_bars()

                    # Add to buffer
                    for bar in completed_bars:
                        with self._bar_buffer_lock:
                            self._bar_buffer[bar.symbol].append(bar)
                            self._stats["bars_received"] += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")

    def get_bars(self, symbol: Optional[str] = None) -> Dict[str, List]:
        """
        Get buffered bars for symbol(s).

        Args:
            symbol: Specific symbol to get bars for, or None for all

        Returns:
            Dictionary mapping symbol to list of bars
        """
        with self._bar_buffer_lock:
            if symbol:
                return {symbol: self._bar_buffer.get(symbol, [])}
            else:
                return dict(self._bar_buffer)

    def flush_bars(self, symbol: Optional[str] = None) -> Dict[str, List]:
        """
        Flush and return buffered bars for symbol(s).

        Args:
            symbol: Specific symbol to flush, or None for all

        Returns:
            Dictionary mapping symbol to list of flushed bars
        """
        with self._bar_buffer_lock:
            if symbol:
                bars = self._bar_buffer.pop(symbol, [])
                return {symbol: bars} if bars else {}
            else:
                flushed = dict(self._bar_buffer)
                self._bar_buffer.clear()
                return flushed

    def _flush_all_bars(self) -> None:
        """Flush all bars to database before shutdown."""
        bars_to_store = self.flush_bars()

        for symbol, bars in bars_to_store.items():
            if bars:
                try:
                    self._store_bars(symbol, bars)
                except Exception as e:
                    logger.error(f"Error storing bars for {symbol}: {e}")

    def _store_bars(self, symbol: str, bars: List) -> None:
        """
        Store bars to database.

        Args:
            symbol: Stock symbol
            bars: List of IntervalData bars
        """
        if not bars:
            return

        try:
            with get_connection() as conn:
                symbol_id = ensure_market_symbol(conn, symbol, "US")
                stored = bulk_upsert_market_data(conn, symbol_id, self.interval, bars)
                self._stats["bars_stored"] += stored
                logger.debug(f"{symbol}: Stored {stored} bars from WebSocket")
        except Exception as e:
            logger.error(f"Error storing bars for {symbol}: {e}")
            raise

    def store_buffered_bars(self, batch_size: int = 100) -> int:
        """
        Store buffered bars to database in batches.

        Args:
            batch_size: Maximum bars to store per symbol per call

        Returns:
            Total number of bars stored
        """
        total_stored = 0
        bars_to_store = self.flush_bars()

        for symbol, bars in bars_to_store.items():
            if not bars:
                continue

            # Process in batches
            for i in range(0, len(bars), batch_size):
                batch = bars[i : i + batch_size]
                try:
                    self._store_bars(symbol, batch)
                    total_stored += len(batch)
                except Exception as e:
                    logger.error(f"Error storing batch for {symbol}: {e}")

        return total_stored

    def get_status(self) -> Dict:
        """
        Get WebSocket manager status.

        Returns:
            Dictionary with status information
        """
        status = {
            "running": self._running,
            "bars_buffered": sum(len(bars) for bars in self._bar_buffer.values()),
            "stats": self._stats.copy(),
            "client_initialized": self._client is not None,
            "loop_running": self._loop is not None and self._loop.is_running() if self._loop else False,
        }

        # Get client status if available
        if self._client and self._loop and self._loop.is_running():
            try:
                # Get status from client (run in event loop)
                import queue
                status_queue = queue.Queue()

                def get_status_sync():
                    try:
                        status_queue.put(self._client.get_status())
                    except Exception as e:
                        status_queue.put({"error": str(e)})

                # Schedule in event loop
                self._loop.call_soon_threadsafe(get_status_sync)
                try:
                    client_status = status_queue.get(timeout=2.0)
                    status["client_status"] = client_status
                    status["client_connected"] = client_status.get("connected", 0) > 0
                except queue.Empty:
                    status["client_connected"] = False
                    status["client_status"] = {"error": "timeout getting status"}
            except Exception as e:
                logger.debug(f"Could not get client status: {e}")
                status["client_connected"] = False
                status["client_status"] = {"error": str(e)}
        else:
            status["client_connected"] = False
            status["client_status"] = None

        return status

    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        if not self._running:
            return False
        if not self._client or not self._loop:
            return False
        if not self._loop.is_running():
            return False

        # Try to get actual connection status
        try:
            status = self.get_status()
            return status.get("client_connected", False)
        except Exception:
            # Fallback: if client exists and loop is running, assume connected
            return self._running and self._client is not None


__all__ = ["WebSocketManager"]
