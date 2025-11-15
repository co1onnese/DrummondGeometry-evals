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
        self._start_time: Optional[datetime] = None  # Track when scheduler started for stuck detection

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
        # Use a trigger that matches typical cycle duration (every 10 minutes)
        # This prevents skipped runs while still allowing dynamic interval switching
        # The _should_run_cycle() method enforces the actual collection interval
        # Note: Cycles take ~6-7 minutes, so 10-minute trigger prevents overlap
        trigger = CronTrigger(minute="*/10", timezone="America/New_York")
        
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
        logger.info("Attempting to acquire execution lock...")
        lock_acquired = False
        try:
            lock_acquired = self._execution_lock.acquire(blocking=False)
            if lock_acquired:
                logger.info("Execution lock acquired successfully")
            else:
                logger.warning("Execution lock already held, checking if cycle is stuck...")
        except Exception as e:
            logger.error(f"Error acquiring lock: {e}", exc_info=True)
        
        if not lock_acquired:
            # Check if lock has been held too long (stuck cycle detection)
            # If last run was more than 2 hours ago, or if we've never run and it's been >30 min since start, force release
            should_force_release = False
            if self._last_run_time:
                time_since_last_run = (datetime.now(timezone.utc) - self._last_run_time).total_seconds()
                max_stuck_duration = 2 * 60 * 60  # 2 hours
                if time_since_last_run > max_stuck_duration:
                    should_force_release = True
                    logger.warning(
                        f"Collection cycle appears stuck (last run {time_since_last_run/3600:.1f}h ago). "
                        f"Force releasing lock."
                    )
            else:
                # No last run time - check if service has been running for >30 minutes without completing
                # This handles the case where initial cycle hangs on startup
                if hasattr(self, '_start_time'):
                    time_since_start = (datetime.now(timezone.utc) - self._start_time).total_seconds()
                    if time_since_start > 30 * 60:  # 30 minutes
                        should_force_release = True
                        logger.warning(
                            f"Collection cycle appears stuck (no runs in {time_since_start/60:.1f} min since start). "
                            f"Force releasing lock."
                        )
                else:
                    # First time we see this - check if it's been too long
                    # If service started more than 30 minutes ago and no runs, force release
                    if hasattr(self, '_start_time') and self._start_time:
                        time_since_start = (datetime.now(timezone.utc) - self._start_time).total_seconds()
                        if time_since_start > 30 * 60:  # 30 minutes
                            should_force_release = True
                            logger.warning(
                                f"Collection cycle appears stuck (no runs in {time_since_start/60:.1f} min since start). "
                                f"Force releasing lock."
                            )
                        else:
                            logger.warning("Collection cycle already running, skipping this interval (first check)")
                            return
                    else:
                        # Set start time and wait
                        self._start_time = datetime.now(timezone.utc)
                        logger.warning("Collection cycle already running, skipping this interval (first check)")
                        return
            
            if should_force_release:
                try:
                    if self._execution_lock.locked():
                        self._execution_lock.release()
                    # Try to acquire again
                    if self._execution_lock.acquire(blocking=False):
                        logger.info("Successfully recovered from stuck cycle")
                    else:
                        logger.error("Failed to acquire lock after force release")
                        return
                except Exception as e:
                    logger.error(f"Error force-releasing stuck lock: {e}", exc_info=True)
                    return
            else:
                logger.warning("Collection cycle already running, skipping this interval")
                return

        # Add timeout protection: if cycle takes too long, release lock
        cycle_start_time = time.time()
        max_cycle_duration = 10 * 60  # 10 minutes maximum timeout
        
        try:
            interval = self._get_collection_interval()
            market_status = "market open" if market_open else "market closed"
            
            logger.info(
                f"Starting REST data collection cycle: {len(self.symbols)} symbols, "
                f"interval={interval}, {market_status}"
            )
            logger.info(f"Cycle timeout set to {max_cycle_duration/60:.1f} minutes")

            # Execute REST collection (for historical data or when WebSocket not available)
            # Use threading to add timeout protection during execution
            import threading
            result_container = {"result": None, "exception": None}
            
            def collect_with_timeout():
                try:
                    logger.info("Collection thread started, calling collect_all_symbols...")
                    result_container["result"] = self.service.collect_all_symbols(
                        self.symbols,
                        interval=interval,
                        exchange="US",
                    )
                    logger.info("Collection thread completed successfully")
                except Exception as e:
                    logger.error(f"Collection thread raised exception: {e}", exc_info=True)
                    result_container["exception"] = e
            
            logger.info("Starting collection thread with timeout protection...")
            collection_thread = threading.Thread(target=collect_with_timeout, daemon=True)
            collection_thread.start()
            logger.info(f"Collection thread started, waiting up to {max_cycle_duration/60:.1f} minutes...")
            
            # Wait with periodic status updates
            elapsed = 0
            check_interval = 30  # Check every 30 seconds
            while collection_thread.is_alive() and elapsed < max_cycle_duration:
                collection_thread.join(timeout=check_interval)
                elapsed += check_interval
                if collection_thread.is_alive():
                    logger.info(f"Collection cycle in progress: {elapsed/60:.1f} minutes elapsed, {len(self.symbols)} symbols")
            
            if collection_thread.is_alive():
                # Thread is still running - timeout occurred
                logger.error(
                    f"Collection cycle timed out after {max_cycle_duration/60:.1f} minutes. "
                    f"Force releasing lock. Thread is still alive."
                )
                raise TimeoutError(
                    f"Collection cycle exceeded maximum duration of {max_cycle_duration/60:.1f} minutes"
                )
            
            if result_container["exception"]:
                raise result_container["exception"]
            
            result = result_container["result"]
            if result is None:
                raise RuntimeError("Collection cycle returned None result")
            
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

        except TimeoutError as e:
            logger.error(f"Collection cycle timed out: {e}", exc_info=True)
            # Force release lock on timeout
            try:
                if self._execution_lock.locked():
                    self._execution_lock.release()
                    logger.info("Lock released after timeout")
                else:
                    logger.warning("Lock was not held when timeout occurred")
            except Exception as release_error:
                logger.error(f"Failed to release lock after timeout: {release_error}", exc_info=True)
        except Exception as e:
            logger.error(f"Error in collection cycle: {e}", exc_info=True)
            # Ensure lock is released even on error
        finally:
            # Always release lock, even if cycle failed or timed out
            logger.info("Entering finally block to release lock...")
            print("🔓 Entering finally block to release lock", flush=True)
            try:
                if lock_acquired:
                    logger.info(f"Lock was acquired, checking if still locked...")
                    is_locked = self._execution_lock.locked()
                    logger.info(f"Lock state: locked={is_locked}")
                    if is_locked:
                        self._execution_lock.release()
                        logger.info("✓ Lock released in finally block after cycle completion/error")
                        print("✓ Lock released successfully", flush=True)
                    else:
                        logger.warning("Lock was not held in finally block (may have been released earlier)")
                        print("⚠ Lock was not held (already released?)", flush=True)
                else:
                    logger.debug("Lock was not acquired, nothing to release")
                    print("⚠ Lock was not acquired, nothing to release", flush=True)
            except Exception as release_error:
                logger.error(f"Failed to release execution lock in finally block: {release_error}", exc_info=True)
                print(f"❌ Failed to release lock: {release_error}", flush=True)
                # Try one more time with force
                try:
                    # Force release if possible
                    import threading
                    if hasattr(self._execution_lock, '_is_owned'):
                        if self._execution_lock._is_owned():
                            self._execution_lock.release()
                            logger.info("Lock force-released after exception")
                            print("✓ Lock force-released", flush=True)
                except Exception as force_error:
                    logger.error(f"Force release also failed: {force_error}")
                    print(f"❌ Force release failed: {force_error}", flush=True)

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

        # Track start time for stuck cycle detection
        self._start_time = datetime.now(timezone.utc)

        # Add scheduled job
        self._add_scheduled_job()

        # Start APScheduler
        self.scheduler.start()
        self._is_running = True

        # Start WebSocket if market is open (non-blocking, no wait)
        if self.market_hours.is_market_open():
            try:
                logger.info("Market is open - starting WebSocket collection on startup")
                self.service.start_websocket_collection(self.symbols)
                
                # Check connection immediately (no wait)
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

        # Run initial REST collection cycle immediately (for historical data or if WebSocket failed)
        # Start immediately in background thread (non-blocking) but with no delay
        if not self._websocket_started:
            logger.info("Starting immediate initial collection cycle on startup (no delay)")
            print("🚀 Starting immediate initial collection cycle on startup (no delay)", flush=True)
            import threading
            def run_initial_cycle():
                try:
                    logger.info("Initial collection cycle executing now...")
                    print("⚡ Initial collection cycle executing now...", flush=True)
                    cycle_start = time.time()
                    self._execute_collection_cycle()
                    cycle_duration = time.time() - cycle_start
                    logger.info(f"Initial collection cycle completed on startup in {cycle_duration/60:.1f} minutes")
                    print(f"✅ Initial collection cycle completed on startup in {cycle_duration/60:.1f} minutes", flush=True)
                except TimeoutError as e:
                    logger.error(f"Initial collection cycle timed out: {e}", exc_info=True)
                    print(f"⏱️ Initial collection cycle timed out: {e}", flush=True)
                except Exception as e:
                    logger.error(f"Initial collection cycle failed on startup: {e}", exc_info=True)
                    print(f"❌ Initial collection cycle failed on startup: {e}", flush=True)
            
            # Start immediately with no delay
            initial_thread = threading.Thread(target=run_initial_cycle, daemon=True)
            initial_thread.start()
            logger.info("Initial collection cycle thread started immediately")
            print("✅ Initial collection cycle thread started immediately", flush=True)

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
