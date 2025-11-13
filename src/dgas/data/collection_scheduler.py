"""Data collection scheduler for continuous market data updates."""

from __future__ import annotations

import logging
import signal
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from threading import Timer

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from ..config.schema import DataCollectionConfig
from ..settings import Settings, get_settings
from .collection_service import CollectionResult, DataCollectionService
from .client import EODHDClient, EODHDConfig

# Import market hours manager from prediction scheduler
from ..prediction.scheduler import MarketHoursManager, TradingSession

logger = logging.getLogger(__name__)


class DataCollectionScheduler:
    """
    Scheduler for continuous data collection service.
    
    Runs 24/7 with dynamic intervals based on market hours:
    - Market hours (9:30am-4pm ET, Mon-Fri): 5 minutes
    - After hours: 15 minutes
    - Weekends: 30 minutes
    """

    def __init__(
        self,
        config: DataCollectionConfig,
        symbols: List[str],
        service: Optional[DataCollectionService] = None,
        market_hours: Optional[MarketHoursManager] = None,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize data collection scheduler.

        Args:
            config: Data collection configuration
            symbols: List of symbols to collect data for
            service: Data collection service (creates new if None)
            market_hours: Market hours manager (creates new if None)
            settings: Settings instance (uses get_settings() if None)
        """
        self.config = config
        self.symbols = symbols
        self.settings = settings or get_settings()

        # Create service if not provided
        if service is None:
            client = EODHDClient(EODHDConfig.from_settings(self.settings))
            service = DataCollectionService(config, client=client)
        self.service = service

        # Market hours manager
        if market_hours is None:
            market_hours = MarketHoursManager(
                exchange_code="US",
                session=TradingSession(),
            )
        self.market_hours = market_hours

        # APScheduler instance
        self.scheduler = BackgroundScheduler(timezone="America/New_York")
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

        # State
        self._is_running = False
        self._shutdown_event = threading.Event()
        self._execution_lock = threading.Lock()
        self._last_result: Optional[CollectionResult] = None
        self._last_run_time: Optional[datetime] = None
        self._websocket_started = False
        self._last_websocket_store_time: Optional[datetime] = None

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()

    def _job_listener(self, event):
        """Handle scheduler job events."""
        if event.exception:
            logger.error(f"Job execution error: {event.exception}", exc_info=event.exception)
        else:
            logger.debug(f"Job executed successfully: {event.job_id}")

    def _get_collection_interval(self) -> str:
        """
        Determine collection interval based on market hours.

        Returns:
            Interval string (e.g., "5m", "15m", "30m")
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        if self.market_hours.is_market_open():
            return self.config.interval_market_hours
        
        # Check if weekend
        tz = ZoneInfo("America/New_York")
        now = datetime.now(tz)
        is_weekend = now.weekday() >= 5  # Saturday = 5, Sunday = 6
        
        if is_weekend:
            return self.config.interval_weekends
        else:
            return self.config.interval_after_hours

    def _parse_interval_minutes(self, interval: str) -> int:
        """Parse interval string to minutes."""
        if interval.endswith("m"):
            return int(interval[:-1])
        elif interval.endswith("h"):
            return int(interval[:-1]) * 60
        else:
            raise ValueError(f"Invalid interval format: {interval}")

    def _add_scheduled_job(self) -> None:
        """Add scheduled job to APScheduler with dynamic interval."""
        # Use a frequent trigger (every 2 minutes) and check market hours inside
        # This allows dynamic interval switching while reducing overlap risk
        # The _should_run_cycle() method enforces the actual collection interval
        trigger = CronTrigger(minute="*/2", timezone="America/New_York")
        
        self.scheduler.add_job(
            func=self._execute_collection_cycle,
            trigger=trigger,
            id="data_collection_cycle",
            name="Data Collection Cycle",
            max_instances=1,  # Prevent overlapping executions
            replace_existing=True,
            coalesce=True,  # Combine multiple pending executions into one
        )

        # Add periodic task to store WebSocket bars (every 5 minutes)
        store_trigger = CronTrigger(minute="*/5", timezone="America/New_York")
        self.scheduler.add_job(
            func=self._store_websocket_bars,
            trigger=store_trigger,
            id="websocket_bar_storage",
            name="WebSocket Bar Storage",
            max_instances=1,
            replace_existing=True,
        )

    def _should_run_cycle(self) -> bool:
        """
        Check if collection cycle should run based on current interval.

        Returns:
            True if cycle should run now
        """
        if self._last_run_time is None:
            return True  # First run

        interval = self._get_collection_interval()
        interval_minutes = self._parse_interval_minutes(interval)
        
        now = datetime.now(timezone.utc)
        elapsed_minutes = (now - self._last_run_time).total_seconds() / 60.0
        
        return elapsed_minutes >= interval_minutes

    def _execute_collection_cycle(self) -> None:
        """
        Execute data collection cycle.

        This runs every minute but only actually collects data when
        the appropriate interval has elapsed based on market hours.
        Also manages WebSocket lifecycle based on market hours.
        """
        if self._shutdown_event.is_set():
            logger.debug("Shutdown event set, skipping collection cycle")
            return

        # Manage WebSocket lifecycle based on market hours
        market_open = self.market_hours.is_market_open()

        if market_open and not self._websocket_started:
            # Market just opened - start WebSocket collection
            logger.info("Market is open - starting WebSocket collection")
            try:
                self.service.start_websocket_collection(self.symbols)
                self._websocket_started = True
            except Exception as e:
                logger.error(f"Failed to start WebSocket collection: {e}", exc_info=True)
                # Fall back to REST API
                self._websocket_started = False

        elif not market_open and self._websocket_started:
            # Market just closed - stop WebSocket collection
            logger.info("Market is closed - stopping WebSocket collection")
            try:
                self.service.stop_websocket_collection()
                # Store any remaining buffered bars
                stored = self.service.store_websocket_bars()
                if stored > 0:
                    logger.info(f"Stored {stored} remaining WebSocket bars after market close")
            except Exception as e:
                logger.error(f"Error stopping WebSocket collection: {e}", exc_info=True)
            finally:
                self._websocket_started = False

        # If WebSocket is running, skip REST collection (WebSocket handles real-time)
        if market_open and self._websocket_started:
            # WebSocket is handling real-time data, only do periodic REST for historical gaps
            # Check if we should run REST collection (less frequently during market hours)
            if not self._should_run_cycle():
                return

            # Run REST collection less frequently when WebSocket is active
            # Only collect historical data gaps, not real-time
            logger.debug("WebSocket active - skipping REST collection for real-time data")
            return

        # Check if we should run REST collection based on interval
        if not self._should_run_cycle():
            return

        # Acquire lock to prevent concurrent executions
        if not self._execution_lock.acquire(blocking=False):
            logger.warning("Collection cycle already running, skipping this interval")
            return

        # Add timeout protection: if cycle takes too long, release lock
        cycle_start_time = time.time()
        max_cycle_duration = 60 * 60  # 1 hour maximum (safety timeout)
        
        try:
            interval = self._get_collection_interval()
            market_status = "market open" if market_open else "market closed"
            
            logger.info(
                f"Starting REST data collection cycle: {len(self.symbols)} symbols, "
                f"interval={interval}, {market_status}"
            )

            # Execute REST collection (for historical data or when WebSocket not available)
            # Add timeout check before starting
            elapsed = time.time() - cycle_start_time
            if elapsed > max_cycle_duration:
                logger.error(f"Cycle timeout check failed before start: {elapsed:.1f}s elapsed")
                raise TimeoutError(f"Cycle timeout: {elapsed:.1f}s > {max_cycle_duration}s")
            
            result = self.service.collect_all_symbols(
                self.symbols,
                interval=interval,
                exchange="US",
            )
            
            # Check if cycle took too long
            cycle_duration = time.time() - cycle_start_time
            if cycle_duration > max_cycle_duration:
                logger.warning(
                    f"Collection cycle took {cycle_duration/60:.1f} minutes "
                    f"(exceeds safety timeout of {max_cycle_duration/60:.1f} minutes)"
                )

            self._last_result = result
            self._last_run_time = datetime.now(timezone.utc)

            # Log results
            success_rate = (
                (result.symbols_updated / result.symbols_requested * 100)
                if result.symbols_requested > 0
                else 0.0
            )

            logger.info(
                f"REST collection cycle complete: {result.symbols_updated}/{result.symbols_requested} "
                f"symbols updated ({success_rate:.1f}%), "
                f"{result.bars_fetched} fetched, {result.bars_stored} stored, "
                f"{result.execution_time_ms}ms elapsed"
            )

            # Persist collection run to database for tracking
            try:
                from ..db import get_connection
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO data_collection_runs (
                                run_timestamp, interval_type, symbols_requested,
                                symbols_updated, symbols_failed, bars_fetched,
                                bars_stored, execution_time_ms, status, error_count
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            ) RETURNING run_id
                        """, (
                            self._last_run_time,
                            interval,
                            result.symbols_requested,
                            result.symbols_updated,
                            result.symbols_failed,
                            result.bars_fetched,
                            result.bars_stored,
                            result.execution_time_ms,
                            "SUCCESS" if success_rate >= 90 else "PARTIAL" if success_rate >= 50 else "FAILED",
                            len(result.errors),
                        ))
                        run_id = cur.fetchone()[0]
                        conn.commit()
                        logger.debug(f"Saved collection run to database: run_id={run_id}")
            except Exception as e:
                logger.warning(f"Failed to persist collection run to database: {e}")

            # Alert if error rate is high
            error_rate = (
                (result.symbols_failed / result.symbols_requested * 100)
                if result.symbols_requested > 0
                else 0.0
            )
            if error_rate > self.config.error_threshold_pct:
                logger.warning(
                    f"High error rate detected: {error_rate:.1f}% "
                    f"(threshold: {self.config.error_threshold_pct}%)"
                )

        except Exception as e:
            logger.error(f"Error in collection cycle: {e}", exc_info=True)
            # Ensure lock is released even on error
        finally:
            # Always release lock, even if cycle failed or timed out
            try:
                if self._execution_lock.locked():
                    self._execution_lock.release()
                    logger.debug("Lock released after cycle completion/error")
            except Exception as release_error:
                logger.error(f"Failed to release execution lock: {release_error}", exc_info=True)

    def _store_websocket_bars(self) -> None:
        """
        Periodically store buffered WebSocket bars to database.

        This runs every 5 minutes to ensure bars are stored even if
        they haven't completed their interval yet.
        """
        if not self._websocket_started:
            return

        try:
            stored = self.service.store_websocket_bars(batch_size=100)
            if stored > 0:
                logger.debug(f"Stored {stored} WebSocket bars from buffer")
            self._last_websocket_store_time = datetime.now(timezone.utc)
        except Exception as e:
            logger.error(f"Error storing WebSocket bars: {e}", exc_info=True)

    def start(self) -> None:
        """Start data collection scheduler."""
        if self._is_running:
            logger.warning("Data collection scheduler already running")
            return

        if not self.config.enabled:
            logger.info("Data collection service is disabled in configuration")
            return

        logger.info("Starting data collection scheduler")

        # Add scheduled job
        self._add_scheduled_job()

        # Start APScheduler
        self.scheduler.start()
        self._is_running = True

        # Start WebSocket if market is open
        if self.market_hours.is_market_open():
            try:
                logger.info("Market is open - starting WebSocket collection on startup")
                self.service.start_websocket_collection(self.symbols)
                
                # Wait a moment for connection to establish
                import time
                time.sleep(3)
                
                # Verify connection
                ws_status = self.service.get_websocket_status()
                if ws_status and ws_status.get("client_connected", False):
                    self._websocket_started = True
                    logger.info("WebSocket collection started and connected")
                else:
                    logger.warning("WebSocket started but connection not confirmed, will retry")
                    self._websocket_started = False
            except Exception as e:
                logger.warning(f"Failed to start WebSocket on startup: {e}, will use REST API", exc_info=True)
                self._websocket_started = False

        # Run initial REST collection cycle (for historical data or if WebSocket failed)
        if not self._websocket_started:
            self._execute_collection_cycle()

        logger.info("Data collection scheduler started")

    def stop(self, wait: bool = True) -> None:
        """
        Stop data collection scheduler.

        Args:
            wait: If True, wait for current cycle to complete
        """
        if not self._is_running:
            logger.warning("Data collection scheduler not running")
            return

        logger.info("Stopping data collection scheduler")
        self._shutdown_event.set()

        # Stop WebSocket collection
        if self._websocket_started:
            try:
                self.service.stop_websocket_collection()
                # Store any remaining bars
                stored = self.service.store_websocket_bars()
                if stored > 0:
                    logger.info(f"Stored {stored} remaining WebSocket bars on shutdown")
            except Exception as e:
                logger.error(f"Error stopping WebSocket on shutdown: {e}")

        # Stop scheduler
        self.scheduler.shutdown(wait=wait)

        # Close service
        self.service.close()

        self._is_running = False
        logger.info("Data collection scheduler stopped")

    def run_once(self) -> CollectionResult:
        """
        Execute single collection cycle manually.

        Returns:
            Collection result

        Raises:
            RuntimeError: If a cycle is already executing
        """
        if not self._execution_lock.acquire(blocking=False):
            raise RuntimeError("Collection cycle already executing")

        try:
            interval = self._get_collection_interval()
            result = self.service.collect_all_symbols(
                self.symbols,
                interval=interval,
                exchange="US",
            )
            self._last_result = result
            self._last_run_time = datetime.now(timezone.utc)
            return result
        finally:
            self._execution_lock.release()

    def get_status(self) -> Dict:
        """
        Get scheduler status.

        Returns:
            Dictionary with status information
        """
        status = {
            "running": self._is_running,
            "enabled": self.config.enabled,
            "symbols": len(self.symbols),
            "current_interval": self._get_collection_interval(),
            "market_open": self.market_hours.is_market_open(),
            "last_run_time": self._last_run_time.isoformat() if self._last_run_time else None,
        }

        if self._last_result:
            status["last_result"] = {
                "symbols_updated": self._last_result.symbols_updated,
                "symbols_requested": self._last_result.symbols_requested,
                "bars_stored": self._last_result.bars_stored,
                "execution_time_ms": self._last_result.execution_time_ms,
                "errors": len(self._last_result.errors),
            }

        # Add WebSocket status
        status["websocket"] = {
            "started": self._websocket_started,
            "last_store_time": self._last_websocket_store_time.isoformat() if self._last_websocket_store_time else None,
        }
        ws_status = self.service.get_websocket_status()
        if ws_status:
            status["websocket"].update(ws_status)

        return status


__all__ = ["DataCollectionScheduler"]
