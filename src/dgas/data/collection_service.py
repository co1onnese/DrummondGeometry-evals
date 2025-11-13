"""Data collection service for continuous market data updates."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..config.schema import DataCollectionConfig
from ..db import get_connection
from ..settings import get_settings
from .client import EODHDClient, EODHDConfig
from .errors import EODHDError, EODHDRateLimitError, EODHDRequestError
from .ingestion import IngestionSummary, incremental_update_intraday, backfill_intraday
from .repository import get_latest_timestamp
from .websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    """Result of a data collection cycle."""

    symbols_requested: int
    symbols_updated: int
    symbols_failed: int
    bars_fetched: int
    bars_stored: int
    execution_time_ms: int
    errors: List[str]
    summaries: List[IngestionSummary]
    timestamp: datetime


class DataCollectionService:
    """
    Service for continuous market data collection.
    
    Handles batch processing, rate limiting, error recovery, and progress tracking.
    """

    def __init__(
        self,
        config: DataCollectionConfig,
        client: Optional[EODHDClient] = None,
    ):
        """
        Initialize data collection service.

        Args:
            config: Data collection configuration
            client: Optional EODHD client (creates new if None)
        """
        self.config = config
        self._client = client
        self._effective_rate_limit = int(
            config.requests_per_minute * (1.0 - config.rate_limit_buffer)
        )

        # WebSocket manager for real-time data
        self._websocket_manager: Optional[WebSocketManager] = None
        if config.use_websocket:
            settings = get_settings()
            if settings.eodhd_api_token:
                # WebSocketManager callback signature: (symbol: str, bars: List[IntervalData])
                # This matches our _on_websocket_bar signature, so we can use it directly
                self._websocket_manager = WebSocketManager(
                    api_token=settings.eodhd_api_token,
                    interval=config.websocket_interval,
                    on_bar_complete=self._on_websocket_bar,
                )

    def _get_client(self) -> EODHDClient:
        """Get or create EODHD client."""
        if self._client is not None:
            return self._client
        eodhd_config = EODHDConfig.from_settings()
        return EODHDClient(eodhd_config)

    def collect_for_symbol(
        self,
        symbol: str,
        interval: str,
        exchange: str = "US",
    ) -> IngestionSummary:
        """
        Collect data for a single symbol with retry logic.

        Args:
            symbol: Stock symbol
            interval: Data interval (e.g., "5m", "30m")
            exchange: Exchange code (default: "US")

        Returns:
            IngestionSummary with collection results

        Raises:
            EODHDError: If collection fails after retries
        """
        retry_delays = [
            self.config.retry_delay_seconds * (2 ** i)
            for i in range(self.config.max_retries)
        ]

        last_error: Optional[Exception] = None
        for attempt, delay in enumerate(retry_delays):
            try:
                # Check if symbol has existing data
                from datetime import datetime, timedelta, timezone
                from .repository import get_latest_timestamp, ensure_market_symbol
                from ..db import get_connection
                
                with get_connection() as conn:
                    symbol_id = ensure_market_symbol(conn, symbol, exchange)
                    latest_ts = get_latest_timestamp(conn, symbol_id, interval)
                
                if latest_ts is None:
                    # No existing data - use backfill with default start
                    today = datetime.now(timezone.utc).date()
                    start_date = (today - timedelta(days=90)).isoformat()
                    end_date = today.isoformat()
                    return backfill_intraday(
                        symbol,
                        exchange=exchange,
                        start_date=start_date,
                        end_date=end_date,
                        interval=interval,
                        client=self._get_client(),
                        use_live_for_today=True,
                    )
                else:
                    # Has data - use incremental update
                    return incremental_update_intraday(
                        symbol,
                        exchange=exchange,
                        interval=interval,
                        buffer_days=2,
                        client=self._get_client(),
                        use_live_data=True,
                    )
            except EODHDRateLimitError as e:
                # Rate limit errors: wait longer and retry
                if attempt < len(retry_delays) - 1:
                    wait_time = delay * 2  # Longer wait for rate limits
                    logger.warning(
                        f"Rate limit hit for {symbol}, waiting {wait_time}s before retry {attempt + 1}/{self.config.max_retries}"
                    )
                    time.sleep(wait_time)
                    last_error = e
                    continue
                raise
            except EODHDError as e:
                # Other API errors: retry with normal backoff
                if attempt < len(retry_delays) - 1:
                    logger.warning(
                        f"Error collecting {symbol} (attempt {attempt + 1}/{self.config.max_retries}): {e}"
                    )
                    time.sleep(delay)
                    last_error = e
                    continue
                raise
            except Exception as e:
                # Unexpected errors: log and re-raise (don't retry)
                logger.error(f"Unexpected error collecting {symbol}: {e}", exc_info=True)
                raise

        # If we exhausted retries, raise the last error
        if last_error:
            raise last_error
        raise RuntimeError(f"Failed to collect {symbol} after {self.config.max_retries} attempts")

    def collect_batch(
        self,
        symbols: List[str],
        interval: str,
        exchange: str = "US",
    ) -> List[IngestionSummary]:
        """
        Collect data for a batch of symbols with rate limiting.

        Args:
            symbols: List of stock symbols
            interval: Data interval
            exchange: Exchange code

        Returns:
            List of IngestionSummary results (one per symbol)
        """
        summaries: List[IngestionSummary] = []
        client = self._get_client()

        for i, symbol in enumerate(symbols):
            try:
                # Check if symbol has existing data
                from datetime import datetime, timedelta, timezone
                from .repository import get_latest_timestamp, ensure_market_symbol
                from ..db import get_connection
                
                with get_connection() as conn:
                    symbol_id = ensure_market_symbol(conn, symbol, exchange)
                    latest_ts = get_latest_timestamp(conn, symbol_id, interval)
                
                if latest_ts is None:
                    # No existing data - use backfill
                    today = datetime.now(timezone.utc).date()
                    start_date = (today - timedelta(days=90)).isoformat()
                    end_date = today.isoformat()
                    summary = backfill_intraday(
                        symbol,
                        exchange=exchange,
                        start_date=start_date,
                        end_date=end_date,
                        interval=interval,
                        client=client,
                        use_live_for_today=True,
                    )
                else:
                    # Has data - use incremental update with live data
                    summary = incremental_update_intraday(
                        symbol,
                        exchange=exchange,
                        interval=interval,
                        buffer_days=2,
                        client=client,
                        use_live_data=True,  # Use live OHLCV for today's data
                    )
                summaries.append(summary)

                if self.config.log_collection_stats:
                    logger.debug(
                        f"Batch progress: {i+1}/{len(symbols)} - {symbol}: "
                        f"fetched={summary.fetched}, stored={summary.stored}"
                    )

            except EODHDRequestError as e:
                # Handle API errors - check for 404 (invalid symbol)
                error_msg = str(e)
                if "404" in error_msg or "Ticker Not Found" in error_msg:
                    # Invalid symbol - skip gracefully, don't count as failure
                    logger.warning(
                        f"{symbol}: Invalid ticker (404) - skipping. "
                        f"This symbol may not exist in EODHD API or may be an evaluation symbol."
                    )
                    # Don't add to summaries - skip invalid symbols entirely
                    continue
                else:
                    # Other API errors - log and track
                    logger.error(f"Failed to collect {symbol}: {e}", exc_info=True)
                    # Create a summary with zero results
                    from .quality import DataQualityReport
                    error_summary = IngestionSummary(
                        symbol=symbol,
                        interval=interval,
                        fetched=0,
                        stored=0,
                        quality=DataQualityReport(
                            symbol=symbol,
                            interval=interval,
                            total_bars=0,
                            duplicate_count=0,
                            gap_count=0,
                            is_chronological=True,
                            notes=[str(e)],
                        ),
                    )
                    summaries.append(error_summary)
            except ValueError as e:
                # Handle case where symbol has no existing data
                if "No existing data" in str(e):
                    logger.warning(f"{symbol}: No existing data, skipping incremental update (needs initial backfill)")
                    # Create a summary with zero results
                    from .quality import DataQualityReport
                    error_summary = IngestionSummary(
                        symbol=symbol,
                        interval=interval,
                        fetched=0,
                        stored=0,
                        quality=DataQualityReport(
                            symbol=symbol,
                            interval=interval,
                            total_bars=0,
                            duplicate_count=0,
                            gap_count=0,
                            is_chronological=True,
                            notes=["no existing data"],
                        ),
                    )
                    summaries.append(error_summary)
                else:
                    logger.error(f"Failed to collect {symbol}: {e}", exc_info=True)
                    # Create a summary with zero results
                    from .quality import DataQualityReport
                    error_summary = IngestionSummary(
                        symbol=symbol,
                        interval=interval,
                        fetched=0,
                        stored=0,
                        quality=DataQualityReport(
                            symbol=symbol,
                            interval=interval,
                            total_bars=0,
                            duplicate_count=0,
                            gap_count=0,
                            is_chronological=True,
                            notes=[str(e)],
                        ),
                    )
                    summaries.append(error_summary)
            except Exception as e:
                logger.error(f"Failed to collect {symbol}: {e}", exc_info=True)
                # Continue with other symbols even if one fails
                # Create a summary with zero results to track the failure
                from .quality import DataQualityReport
                error_summary = IngestionSummary(
                    symbol=symbol,
                    interval=interval,
                    fetched=0,
                    stored=0,
                    quality=DataQualityReport(
                        symbol=symbol,
                        interval=interval,
                        total_bars=0,
                        duplicate_count=0,
                        gap_count=0,
                        is_chronological=True,
                        notes=[str(e)],
                    ),
                )
                summaries.append(error_summary)

        return summaries

    def collect_all_symbols(
        self,
        symbols: List[str],
        interval: str,
        exchange: str = "US",
    ) -> CollectionResult:
        """
        Collect data for all symbols using batch processing.

        Args:
            symbols: List of all symbols to collect
            interval: Data interval
            exchange: Exchange code

        Returns:
            CollectionResult with overall statistics
        """
        # Filter out invalid symbols (evaluation symbols, etc.)
        # These typically end with _EVAL or are synthetic symbols
        valid_symbols = [
            s for s in symbols
            if not (s.endswith("_EVAL") or s.startswith("SP500_") or s.startswith("NASDAQ_"))
        ]
        skipped_count = len(symbols) - len(valid_symbols)
        if skipped_count > 0:
            skipped = [s for s in symbols if s not in valid_symbols]
            logger.info(
                f"Filtered out {skipped_count} invalid symbols: {', '.join(skipped[:5])}"
                + (f" and {len(skipped) - 5} more" if len(skipped) > 5 else "")
            )
        
        start_time = time.time()
        all_summaries: List[IngestionSummary] = []
        errors: List[str] = []

        # Split into batches
        batch_size = self.config.batch_size
        batches = [
            valid_symbols[i : i + batch_size] for i in range(0, len(valid_symbols), batch_size)
        ]

        logger.info(
            f"Starting data collection: {len(valid_symbols)} symbols "
            f"({len(symbols)} total, {skipped_count} filtered), "
            f"{len(batches)} batches (size={batch_size}), interval={interval}"
        )

        # Process batches sequentially (for now, concurrent batches can be added later)
        for batch_num, batch in enumerate(batches, 1):
            try:
                batch_summaries = self.collect_batch(batch, interval, exchange)
                all_summaries.extend(batch_summaries)

                # Log batch progress
                batch_updated = sum(1 for s in batch_summaries if s.stored > 0)
                batch_fetched = sum(s.fetched for s in batch_summaries)
                batch_stored = sum(s.stored for s in batch_summaries)

                logger.info(
                    f"Batch {batch_num}/{len(batches)} complete: "
                    f"{batch_updated}/{len(batch)} symbols updated, "
                    f"{batch_fetched} fetched, {batch_stored} stored"
                )

                # Delay between batches (except after last batch)
                if batch_num < len(batches) and self.config.delay_between_batches > 0:
                    time.sleep(self.config.delay_between_batches)

            except Exception as e:
                error_msg = f"Batch {batch_num} failed: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
                # Continue with next batch

        # Calculate statistics
        execution_time_ms = int((time.time() - start_time) * 1000)
        symbols_updated = sum(1 for s in all_summaries if s.stored > 0)
        symbols_failed = sum(1 for s in all_summaries if s.stored == 0 and s.fetched == 0)
        bars_fetched = sum(s.fetched for s in all_summaries)
        bars_stored = sum(s.stored for s in all_summaries)

        # Track errors from summaries
        for summary in all_summaries:
            if summary.stored == 0 and summary.fetched == 0:
                errors.append(f"{summary.symbol}: No data collected")

        logger.info(
            f"Collection complete: {symbols_updated}/{len(valid_symbols)} symbols updated, "
            f"{bars_fetched} bars fetched, {bars_stored} bars stored, "
            f"{execution_time_ms}ms elapsed, {len(errors)} errors"
        )

        return CollectionResult(
            symbols_requested=len(valid_symbols),
            symbols_updated=symbols_updated,
            symbols_failed=symbols_failed,
            bars_fetched=bars_fetched,
            bars_stored=bars_stored,
            execution_time_ms=execution_time_ms,
            errors=errors,
            summaries=all_summaries,
            timestamp=datetime.now(timezone.utc),
        )

    def get_collection_status(self) -> Dict:
        """
        Get current collection service status.

        Returns:
            Dictionary with status information
        """
        return {
            "enabled": self.config.enabled,
            "batch_size": self.config.batch_size,
            "rate_limit": self._effective_rate_limit,
            "max_retries": self.config.max_retries,
        }

    def get_freshness_report(
        self,
        symbols: List[str],
        interval: str,
    ) -> Dict:
        """
        Get data freshness report for symbols.

        Args:
            symbols: List of symbols to check
            interval: Data interval

        Returns:
            Dictionary with freshness statistics
        """
        now = datetime.now(timezone.utc)
        ages: List[float] = []
        stale_symbols: List[tuple[str, float]] = []

        with get_connection() as conn:
            for symbol in symbols:
                try:
                    from .repository import ensure_market_symbol
                    symbol_id = ensure_market_symbol(conn, symbol, "US")
                    latest_ts = get_latest_timestamp(conn, symbol_id, interval)

                    if latest_ts:
                        age_minutes = (now - latest_ts).total_seconds() / 60.0
                        ages.append(age_minutes)
                        if age_minutes > 60:  # Consider > 60 min stale
                            stale_symbols.append((symbol, age_minutes))
                    else:
                        # No data
                        ages.append(float("inf"))
                        stale_symbols.append((symbol, float("inf")))
                except Exception as e:
                    logger.warning(f"Error checking freshness for {symbol}: {e}")

        if not ages:
            return {
                "total_symbols": len(symbols),
                "symbols_with_data": 0,
                "average_age_minutes": None,
                "min_age_minutes": None,
                "max_age_minutes": None,
                "stale_count": len(stale_symbols),
                "stale_symbols": stale_symbols[:10],  # First 10
            }

        valid_ages = [a for a in ages if a != float("inf")]

        return {
            "total_symbols": len(symbols),
            "symbols_with_data": len(valid_ages),
            "average_age_minutes": sum(valid_ages) / len(valid_ages) if valid_ages else None,
            "min_age_minutes": min(valid_ages) if valid_ages else None,
            "max_age_minutes": max(valid_ages) if valid_ages else None,
            "stale_count": len(stale_symbols),
            "stale_symbols": stale_symbols[:10],  # First 10 stale symbols
        }

    def start_websocket_collection(self, symbols: List[str]) -> None:
        """
        Start WebSocket-based real-time data collection.

        Args:
            symbols: List of symbols to subscribe to
        """
        if not self.config.use_websocket:
            logger.info("WebSocket collection disabled in configuration")
            return

        if self._websocket_manager is None:
            logger.warning("WebSocket manager not initialized")
            return

        if self._websocket_manager.is_connected():
            logger.warning("WebSocket collection already running")
            return

        logger.info(f"Starting WebSocket collection for {len(symbols)} symbols")
        self._websocket_manager.start(symbols)

    def stop_websocket_collection(self) -> None:
        """Stop WebSocket-based real-time data collection."""
        if self._websocket_manager:
            logger.info("Stopping WebSocket collection")
            self._websocket_manager.stop()

    def _on_websocket_bar(self, symbol: str, bars: List) -> None:
        """
        Callback when WebSocket completes a bar.

        Args:
            symbol: Stock symbol
            bars: List of completed IntervalData bars
        """
        # Bars are automatically stored by WebSocketManager
        # This callback is for logging/monitoring
        if bars:
            logger.debug(f"{symbol}: WebSocket completed {len(bars)} bar(s)")

    def store_websocket_bars(self, batch_size: int = 100) -> int:
        """
        Store buffered WebSocket bars to database.

        Args:
            batch_size: Maximum bars to store per symbol per call

        Returns:
            Total number of bars stored
        """
        if not self._websocket_manager:
            return 0

        return self._websocket_manager.store_buffered_bars(batch_size=batch_size)

    def get_websocket_status(self) -> Optional[Dict]:
        """
        Get WebSocket collection status.

        Returns:
            Dictionary with status information or None if not enabled
        """
        if not self._websocket_manager:
            return None

        return self._websocket_manager.get_status()

    def close(self) -> None:
        """Close resources (client connection and WebSocket)."""
        # Stop WebSocket collection
        self.stop_websocket_collection()

        # Close REST client
        if self._client is not None:
            self._client.close()


__all__ = ["DataCollectionService", "CollectionResult"]
